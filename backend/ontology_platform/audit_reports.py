"""Audit reports: the questions an auditor asks, answered from the ledgers.

ROADMAP stage G's last open item. The platform already recorded everything needed --
`audit_log`, `decision_record`, `inference_result`, `model_invocation` -- and exposed it
as three endpoints returning the most recent 50 rows each.

That is not an audit. An auditor does not ask "what happened recently"; they arrive with
a period and a specific question:

| 审计问题 | 需要的聚合 |
|---|---|
| 这段时间有多少判定被阻断，依据哪些规则 | 按结论与规则聚合判定 |
| 哪些规则从未拦下任何东西 | 规则与判定的**反连接** |
| 谁改过发布态的规则 | 按操作者聚合审计事件 |
| 哪些结论involved了模型 | 判定与模型调用按时间关联 |
| 有没有绕过发布门禁 | `--force` 发布的审计条目 |

Every one of those is a query over rows the platform already has, and none of them is
answerable by scrolling a list. The gap was never data; it was that the aggregation lived
in the auditor's head.

## Rules that never fired are the finding, not the footnote

The most useful line in a compliance report is usually the one nobody asked for: a
published rule that has never produced a single verdict. Either it is dead code in the
control set, or it is silently failing to match anything -- and the second case means a
control the organisation believes it has. An anti-join is the only way to see it, because
the rule appears perfectly healthy in every list of rules.

## Counts are computed at read time, never stored

Same reasoning as `quotas.py`: a stored aggregate drifts from the rows it summarises, and
a drifted audit report is worse than none -- it is a number someone will act on.

## The period is required, and half-open

No default window. A report over "everything" invites the reader to treat it as a
statement about a period it does not describe, and an audit finding attached to the wrong
period is a wrong finding. `[start, end)` so consecutive periods neither overlap nor gap:
a decision at exactly midnight belongs to one day, not two or none.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .context import PlatformDb
from .database import connect
from .schema import table_exists

logger = logging.getLogger(__name__)

__all__ = [
    "AuditPeriodError",
    "build_audit_report",
    "describe_report_sections",
]

# What the report answers, in the order an auditor works through it: scope first, then
# findings, then the trail that supports them.
REPORT_SECTIONS = (
    ("decisions", "判定统计", "按结论与严重级聚合，回答「这段时间阻断了多少、为什么」"),
    ("rules", "规则触发情况", "含**从未触发**的已发布规则——那是控制失效还是死规则"),
    ("actors", "操作者活动", "谁在这段时间改了什么，按操作者与动作聚合"),
    ("governance", "治理事件", "发布、派生、覆盖门禁、配额调整"),
    ("model", "模型调用", "哪些结论涉及模型，以及调用是否失败"),
    ("coverage", "留痕完整性", "判定是否都带解释链——缺失意味着结论无法复核"),
)


class AuditPeriodError(ValueError):
    """Raised when the reporting period is missing or backwards."""


def describe_report_sections() -> list[dict[str, str]]:
    return [{"section": key, "name": name, "answers": answers} for key, name, answers in REPORT_SECTIONS]


def build_audit_report(
    platform_db: PlatformDb,
    *,
    start: str,
    end: str,
    ontology_id: Optional[int] = None,
) -> dict[str, Any]:
    """One report over one period.

    `start` and `end` are required rather than defaulted. A report over "everything"
    invites the reader to treat it as a statement about a period it does not describe, and
    a finding attached to the wrong period is a wrong finding.
    """
    if not start.strip() or not end.strip():
        raise AuditPeriodError("审计报表必须给出起止时间：覆盖范围不明的报表无法作为审计依据。")
    if start >= end:
        # Compared as strings, which is correct for the ISO forms this platform stores.
        raise AuditPeriodError(f"审计区间无效：{start} 不早于 {end}。")

    with connect(platform_db) as conn:
        report: dict[str, Any] = {
            "period": {"start": start, "end": end, "boundary": "半开区间 [start, end)"},
            "ontologyId": ontology_id,
            "decisions": _decisions(conn, start, end, ontology_id),
            "rules": _rules(conn, start, end, ontology_id),
            "actors": _actors(conn, start, end),
            "governance": _governance(conn, start, end),
            "model": _model_invocations(conn, start, end),
            "coverage": _trace_coverage(conn, start, end, ontology_id),
        }

    report["findings"] = _findings(report)
    return report


def _scoped(sql: str, ontology_id: Optional[int], column: str = "ontology_id") -> str:
    return sql if ontology_id is None else f"{sql} and {column} = ?"


def _params(base: tuple[Any, ...], ontology_id: Optional[int]) -> tuple[Any, ...]:
    return base if ontology_id is None else (*base, ontology_id)


def _decisions(conn: Any, start: str, end: str, ontology_id: Optional[int]) -> dict[str, Any]:
    """Verdict counts by status, and the blocked ones in full.

    Blocked verdicts are listed rather than counted because they are the ones an auditor
    follows up individually -- a count of 40 blocked contracts answers nothing about
    whether any of them was blocked wrongly.
    """
    if not table_exists(conn, "decision_record"):
        return {"total": 0, "byStatus": {}, "blocked": []}

    rows = conn.execute(
        _scoped(
            "select status, count(*) as total from decision_record where created_at >= ? and created_at < ?",
            ontology_id,
        )
        + " group by status",
        _params((start, end), ontology_id),
    ).fetchall()
    by_status = {row["status"]: int(row["total"]) for row in rows}

    blocked = conn.execute(
        _scoped(
            "select decision_id, decision_type, object_code, instance_id, status, actor, created_at"
            " from decision_record where created_at >= ? and created_at < ? and status = 'blocked'",
            ontology_id,
        )
        + " order by created_at desc",
        _params((start, end), ontology_id),
    ).fetchall()

    return {
        "total": sum(by_status.values()),
        "byStatus": by_status,
        "blocked": [dict(row) for row in blocked],
    }


def _rules(conn: Any, start: str, end: str, ontology_id: Optional[int]) -> dict[str, Any]:
    """Which published rules fired, and which never did.

    The anti-join is the point. A published rule with zero results is either dead weight
    in the control set or silently matching nothing -- and the second case means the
    organisation believes it has a control that is not operating. Neither is visible in a
    list of rules, because the rule looks healthy there.
    """
    if not table_exists(conn, "business_rule"):
        return {"triggered": [], "neverTriggered": [], "note": ""}

    has_results = table_exists(conn, "inference_result")
    scope = "" if ontology_id is None else " and br.ontology_id = ?"
    params: tuple[Any, ...] = () if ontology_id is None else (ontology_id,)

    published = conn.execute(
        f"select br.id, br.code, br.name, br.severity, br.ontology_id"
        f" from business_rule br where br.status = 'published'{scope} order by br.code",
        params,
    ).fetchall()

    counts: dict[int, int] = {}
    if has_results:
        for row in conn.execute(
            "select rule_id, count(*) as total, sum(case when passed = 0 then 1 else 0 end) as failed"
            " from inference_result where created_at >= ? and created_at < ?"
            " group by rule_id",
            (start, end),
        ).fetchall():
            if row["rule_id"] is not None:
                counts[int(row["rule_id"])] = int(row["total"])

    triggered: list[dict[str, Any]] = []
    never: list[dict[str, Any]] = []
    for rule in published:
        entry = {
            "code": rule["code"],
            "name": rule["name"],
            "severity": rule["severity"],
            "ontologyId": rule["ontology_id"],
            "evaluations": counts.get(int(rule["id"]), 0),
        }
        (triggered if entry["evaluations"] else never).append(entry)

    return {
        "triggered": triggered,
        "neverTriggered": never,
        "note": (
            "从未触发的已发布规则要么是死规则，要么在静默地匹配不到任何实例——后者意味着组织以为存在的控制并未运行。"
        ),
    }


def _actors(conn: Any, start: str, end: str) -> dict[str, Any]:
    if not table_exists(conn, "audit_log"):
        return {"byActor": {}}
    rows = conn.execute(
        "select actor, action, count(*) as total from audit_log"
        " where created_at >= ? and created_at < ? group by actor, action order by actor, action",
        (start, end),
    ).fetchall()
    by_actor: dict[str, dict[str, int]] = {}
    for row in rows:
        by_actor.setdefault(row["actor"], {})[row["action"]] = int(row["total"])
    return {"byActor": by_actor}


# Actions that change what the platform will decide, or who may make it decide. These are
# listed individually rather than counted: each one is a question an auditor may ask about.
GOVERNANCE_ACTIONS = (
    "publish_ontology",
    "derive_ontology",
    "force_publish",
    "provision_tenant",
    "set_tenant_quota",
    "review_mapping",
    "review_knowledge_entry",
)


def _governance(conn: Any, start: str, end: str) -> dict[str, Any]:
    """Events that changed the model, the gates, or who may bypass them.

    A forced publication is called out separately because it is the one action that
    deliberately overrides a control. It is legitimate -- a business exception exists --
    but it is never something an audit should have to search for.
    """
    if not table_exists(conn, "audit_log"):
        return {"events": [], "forcedPublications": []}

    placeholders = ", ".join("?" for _ in GOVERNANCE_ACTIONS)
    rows = conn.execute(
        f"select actor, action, target_type, target_id, detail, created_at from audit_log"
        f" where created_at >= ? and created_at < ? and action in ({placeholders})"
        f" order by created_at desc",
        (start, end, *GOVERNANCE_ACTIONS),
    ).fetchall()

    events = [dict(row) for row in rows]
    forced = [
        event
        for event in events
        # `publish_ontology` records the gate outcome in its detail, so a forced publish is
        # identifiable without a separate action name.
        if event["action"] in ("force_publish", "publish_ontology") and '"force": true' in (event["detail"] or "")
    ]
    return {"events": events, "forcedPublications": forced}


def _model_invocations(conn: Any, start: str, end: str) -> dict[str, Any]:
    """Which model calls happened, and how many failed.

    Failures matter to an audit specifically because the platform degrades rather than
    erroring when a model is unavailable: an answer produced during an outage came from
    the local heuristic, and a reviewer comparing two answers needs to know that.
    """
    if not table_exists(conn, "model_invocation"):
        return {"total": 0, "byPurpose": {}, "failed": 0}

    rows = conn.execute(
        "select purpose, status, count(*) as total from model_invocation"
        " where created_at >= ? and created_at < ? group by purpose, status",
        (start, end),
    ).fetchall()

    by_purpose: dict[str, dict[str, int]] = {}
    failed = 0
    total = 0
    for row in rows:
        count = int(row["total"])
        total += count
        by_purpose.setdefault(row["purpose"], {})[row["status"]] = count
        if row["status"] != "success":
            failed += count

    return {"total": total, "byPurpose": by_purpose, "failed": failed}


def _trace_coverage(conn: Any, start: str, end: str, ontology_id: Optional[int]) -> dict[str, Any]:
    """Whether every verdict in the period can be re-examined.

    A decision without an explanation trace cannot be reviewed: the reviewer can see the
    conclusion and not what produced it. That makes it the one coverage number an audit
    genuinely needs, because it bounds how much of the period is auditable at all.
    """
    if not (table_exists(conn, "inference_result") and table_exists(conn, "explanation_trace")):
        return {"decisions": 0, "withTrace": 0, "ratio": None}

    total = int(
        conn.execute(
            "select count(*) as total from inference_result where created_at >= ? and created_at < ?",
            (start, end),
        ).fetchone()["total"]
    )
    with_trace = int(
        conn.execute(
            "select count(distinct ir.id) as total from inference_result ir"
            " join explanation_trace et on et.inference_result_id = ir.id"
            " where ir.created_at >= ? and ir.created_at < ?",
            (start, end),
        ).fetchone()["total"]
    )
    return {
        "decisions": total,
        "withTrace": with_trace,
        # None rather than 1.0 for an empty period: a ratio over zero rows is not "complete
        # coverage", and reporting it as 100% would be a claim about nothing.
        "ratio": None if total == 0 else round(with_trace / total, 4),
    }


def _findings(report: dict[str, Any]) -> list[dict[str, str]]:
    """The things an auditor should look at, stated rather than left to be noticed.

    A report that only presents numbers relies on the reader knowing which number is
    alarming. These are the three that are always worth surfacing: controls that never
    ran, gates that were overridden, and verdicts that cannot be re-examined.
    """
    findings: list[dict[str, str]] = []

    never = report["rules"]["neverTriggered"]
    if never:
        findings.append(
            {
                "severity": "warning",
                "finding": f"{len(never)} 条已发布规则在本期内从未参与判定",
                "action": "确认是死规则（应下线）还是匹配失效（是控制缺口）。",
            }
        )

    forced = report["governance"]["forcedPublications"]
    if forced:
        findings.append(
            {
                "severity": "blocker",
                "finding": f"本期存在 {len(forced)} 次覆盖发布门禁的发布",
                "action": "逐条复核覆盖理由与当时未通过的门禁项。",
            }
        )

    ratio = report["coverage"]["ratio"]
    if ratio is not None and ratio < 1:
        findings.append(
            {
                "severity": "blocker",
                "finding": f"仅 {ratio:.1%} 的判定带有解释链",
                "action": "无解释链的判定无法复核，等同于本期该部分不可审计。",
            }
        )

    if report["model"]["failed"]:
        findings.append(
            {
                "severity": "warning",
                "finding": f"本期有 {report['model']['failed']} 次模型调用失败",
                "action": "模型不可用时平台回退本地启发式，相关答案的产生路径与其他期不同。",
            }
        )

    return findings
