"""Workbench: one aggregated view of what needs attention.

Operators previously had to visit six screens to answer "what should I do next":
data sources for connectivity, mappings for the review queue, ontologies for
release state, rules for coverage, decisions for recent verdicts, workflow for
pending approvals.

This module answers that question in one round trip. It is deliberately a
read-only projection over existing tables -- it introduces no new state, so it
cannot disagree with the screens it summarises.

Every number here is a count of something a user can navigate to; nothing is
estimated or inferred. `actionItems` is ordered by how much it blocks progress,
because a list of 40 undifferentiated items is not actionable.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .database import connect

logger = logging.getLogger(__name__)

# Severity ordering for action items. Blocking work first: an unreviewed mapping
# stops a release, an unreachable data source stops everything downstream.
SEVERITY_ORDER = {"blocker": 0, "warning": 1, "info": 2}


def _scalar(conn: Any, query: str, params: tuple[Any, ...] = ()) -> int:
    """Count query that tolerates a missing table.

    Workflow, auth and agent tables are created by their own init functions
    rather than by initialize_platform_db, so a platform database can legitimately
    lack them -- for example a fresh library-only install that never started the
    web app. The workbench summarises those areas but must not be the thing that
    crashes because of them.
    """
    try:
        row = conn.execute(query, params).fetchone()
    except Exception as error:
        logger.debug("工作台统计查询跳过（表可能尚未创建）: %s", error)
        return 0
    if row is None:
        return 0
    value = row[0] if not isinstance(row, dict) else next(iter(row.values()))
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _rows(conn: Any, query: str, params: tuple[Any, ...] = ()) -> list[Any]:
    """Row query with the same tolerance as `_scalar`."""
    try:
        return list(conn.execute(query, params).fetchall())
    except Exception as error:
        logger.debug("工作台查询跳过（表可能尚未创建）: %s", error)
        return []


def build_workbench(platform_db: Path | str, decision_limit: int = 8) -> dict[str, Any]:
    """Aggregate platform state for the workbench screen."""
    with connect(platform_db) as conn:
        data_sources = _data_source_health(conn)
        ontologies = _ontology_states(conn)
        governance = _governance_queue(conn)
        rules = _rule_summary(conn)
        decisions = _recent_decisions(conn, decision_limit)
        knowledge = _knowledge_summary(conn)
        feedback = _feedback_counts(conn)

    action_items = _action_items(data_sources, ontologies, governance, rules, feedback)
    return {
        "generatedAt": _now_iso(),
        "dataSources": data_sources,
        "ontologies": ontologies,
        "governance": governance,
        "rules": rules,
        "decisions": decisions,
        "knowledge": knowledge,
        "feedback": feedback,
        "actionItems": action_items,
        "summary": {
            "blockers": sum(1 for item in action_items if item["severity"] == "blocker"),
            "warnings": sum(1 for item in action_items if item["severity"] == "warning"),
            "totalActionItems": len(action_items),
        },
    }


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _data_source_health(conn: Any) -> dict[str, Any]:
    total = _scalar(conn, "select count(*) from data_source")
    scanned = _scalar(
        conn,
        "select count(distinct data_source_id) from source_table",
    )
    with_api = _scalar(conn, "select count(*) from data_source where api_base_url is not null and api_base_url != ''")
    tables = _scalar(conn, "select count(*) from source_table")
    columns = _scalar(conn, "select count(*) from source_column")
    return {
        "total": total,
        "scanned": scanned,
        "unscanned": max(total - scanned, 0),
        "withBusinessApi": with_api,
        "tables": tables,
        "columns": columns,
    }


def _ontology_states(conn: Any) -> dict[str, Any]:
    rows = _rows(conn, "select status, count(*) as count from ontology group by status")
    by_status = {row["status"]: int(row["count"]) for row in rows}
    objects = _scalar(conn, "select count(*) from business_object")
    attributes = _scalar(conn, "select count(*) from business_attribute")
    relations = _scalar(conn, "select count(*) from business_relation")
    # An object with no source table cannot be resolved to instances, so it is
    # worth surfacing rather than hiding inside the object count.
    unbound = _scalar(conn, "select count(*) from business_object where source_table_id is null")
    return {
        "total": sum(by_status.values()),
        "draft": by_status.get("draft", 0),
        "published": by_status.get("published", 0),
        "byStatus": by_status,
        "objects": objects,
        "attributes": attributes,
        "relations": relations,
        "unboundObjects": unbound,
    }


def _governance_queue(conn: Any) -> dict[str, Any]:
    rows = conn.execute("select status, count(*) as count from semantic_mapping group by status").fetchall()
    by_status = {row["status"]: int(row["count"]) for row in rows}
    pending_transitions = _scalar(
        conn,
        "select count(*) from instance_workflow iw join workflow_transition wt "
        "on wt.workflow_id = iw.workflow_id and wt.from_state = iw.current_state "
        "where wt.requires_review = 1",
    )
    audit_entries = _scalar(conn, "select count(*) from audit_log")
    return {
        "pendingMappings": by_status.get("pending", 0),
        "confirmedMappings": by_status.get("confirmed", 0),
        "rejectedMappings": by_status.get("rejected", 0),
        "mappingsByStatus": by_status,
        "reviewableTransitions": pending_transitions,
        "auditEntries": audit_entries,
    }


def _rule_summary(conn: Any) -> dict[str, Any]:
    by_severity = {
        row["severity"]: int(row["count"])
        for row in conn.execute("select severity, count(*) as count from business_rule group by severity").fetchall()
    }
    by_status = {
        row["status"]: int(row["count"])
        for row in conn.execute("select status, count(*) as count from business_rule group by status").fetchall()
    }
    # Objects that carry no rule produce no verdict, which is the single most
    # common reason a deployment "does not seem to do anything".
    objects_without_rules = _scalar(
        conn,
        "select count(*) from business_object bo where not exists ("
        "  select 1 from business_rule br"
        "  where br.ontology_id = bo.ontology_id and br.scope_object_code = bo.code"
        ")",
    )
    return {
        "total": sum(by_status.values()),
        "blocking": by_severity.get("blocking", 0),
        "warning": by_severity.get("warning", 0),
        "info": by_severity.get("info", 0),
        "bySeverity": by_severity,
        "byStatus": by_status,
        "objectsWithoutRules": objects_without_rules,
    }


def _recent_decisions(conn: Any, limit: int) -> dict[str, Any]:
    capped = max(1, min(int(limit), 50))
    by_status = {
        row["status"]: int(row["count"])
        for row in conn.execute("select status, count(*) as count from decision_record group by status").fetchall()
    }
    rows = _rows(
        conn,
        "select decision_id, decision_type, object_code, instance_id, status, actor, created_at "
        "from decision_record order by id desc limit ?",
        (capped,),
    )
    return {
        "total": sum(by_status.values()),
        "byStatus": by_status,
        "blocked": by_status.get("blocked", 0),
        "review": by_status.get("review", 0),
        "approved": by_status.get("approved", 0),
        "recent": [
            {
                "decisionId": row["decision_id"],
                "decisionType": row["decision_type"],
                "objectCode": row["object_code"],
                "instanceId": row["instance_id"],
                "status": row["status"],
                "actor": row["actor"],
                "createdAt": str(row["created_at"]),
            }
            for row in rows
        ],
    }


def _knowledge_summary(conn: Any) -> dict[str, Any]:
    """Value mappings, reported separately because they gate rule readability."""
    rows = conn.execute(
        "select status, count(*) as count from semantic_mapping where mapping_type = 'value_to_state' group by status"
    ).fetchall()
    by_status = {row["status"]: int(row["count"]) for row in rows}
    return {
        "valueMappings": sum(by_status.values()),
        "confirmedValueMappings": by_status.get("confirmed", 0),
        "pendingValueMappings": by_status.get("pending", 0),
    }


def _feedback_counts(conn: Any) -> dict[str, Any]:
    """Answer feedback and escalations.

    Raw counts, not an average score: an average does not tell you which answer to
    fix, and a report of "incorrect" is the single most actionable signal here.
    """
    by_rating = {
        row["rating"]: int(row["count"])
        for row in _rows(conn, "select rating, count(*) as count from answer_feedback group by rating")
    }
    return {
        "total": sum(by_rating.values()),
        "byRating": by_rating,
        "helpful": by_rating.get("helpful", 0),
        "unhelpful": by_rating.get("unhelpful", 0),
        "incorrect": by_rating.get("incorrect", 0),
        "openItems": _scalar(conn, "select count(*) from answer_feedback where status = 'open'"),
        "corrections": _scalar(conn, "select count(*) from answer_feedback where correction != ''"),
        "conversations": _scalar(conn, "select count(*) from conversation"),
        "escalated": _scalar(conn, "select count(*) from conversation where status = 'escalated'"),
    }


def _action_items(
    data_sources: dict[str, Any],
    ontologies: dict[str, Any],
    governance: dict[str, Any],
    rules: dict[str, Any],
    feedback: dict[str, Any],
) -> list[dict[str, Any]]:
    """Turn counts into things a person can act on.

    Each item names where to go and why it matters. Ordering is by severity, then
    by count, so the biggest blocker is first.
    """
    items: list[dict[str, Any]] = []

    if data_sources["total"] == 0:
        items.append(
            {
                "code": "no_data_source",
                "severity": "blocker",
                "title": "尚未接入任何数据源",
                "detail": "平台的全部能力都从元数据扫描开始，先接入一个业务库。",
                "count": 0,
                "route": "/datasource",
            }
        )
    elif data_sources["unscanned"]:
        items.append(
            {
                "code": "unscanned_data_source",
                "severity": "warning",
                "title": f"{data_sources['unscanned']} 个数据源尚未扫描元数据",
                "detail": "未扫描的数据源无法生成本体草案。",
                "count": data_sources["unscanned"],
                "route": "/datasource",
            }
        )

    if data_sources["total"] and ontologies["total"] == 0:
        items.append(
            {
                "code": "no_ontology",
                "severity": "blocker",
                "title": "已接入数据源但尚无本体",
                "detail": "生成本体草案后才能配置规则与输出判定。",
                "count": 0,
                "route": "/ontology",
            }
        )

    if governance["pendingMappings"]:
        items.append(
            {
                "code": "pending_mappings",
                "severity": "blocker",
                "title": f"{governance['pendingMappings']} 条语义映射待审核",
                "detail": "存在待审映射时发布门禁不会通过。",
                "count": governance["pendingMappings"],
                "route": "/mapping",
            }
        )

    if ontologies["unboundObjects"]:
        items.append(
            {
                "code": "unbound_objects",
                "severity": "warning",
                "title": f"{ontologies['unboundObjects']} 个业务对象未绑定来源表",
                "detail": "未绑定来源表的对象无法解析实例，也无法参与研判。",
                "count": ontologies["unboundObjects"],
                "route": "/ontology",
            }
        )

    if rules["total"] == 0 and ontologies["objects"]:
        items.append(
            {
                "code": "no_rules",
                "severity": "blocker",
                "title": "尚未配置任何业务规则",
                "detail": "没有规则就没有判定结论，平台只能做元数据浏览。",
                "count": 0,
                "route": "/rules",
            }
        )
    elif rules["objectsWithoutRules"]:
        items.append(
            {
                "code": "objects_without_rules",
                "severity": "warning",
                "title": f"{rules['objectsWithoutRules']} 个业务对象没有任何规则",
                "detail": "这些对象不会产出判定结论。",
                "count": rules["objectsWithoutRules"],
                "route": "/rules",
            }
        )

    if governance["reviewableTransitions"]:
        items.append(
            {
                "code": "reviewable_transitions",
                "severity": "info",
                "title": f"{governance['reviewableTransitions']} 个实例处于需复核的流转状态",
                "detail": "这些实例等待人工确认后才能继续流转。",
                "count": governance["reviewableTransitions"],
                "route": "/workflow",
            }
        )

    # An answer reported as incorrect is the strongest signal the platform gets:
    # a human looked at a verdict and said it was wrong.
    if feedback.get("incorrect"):
        items.append(
            {
                "code": "incorrect_answers_reported",
                "severity": "blocker",
                "title": f"{feedback['incorrect']} 条回答被标记为错误",
                "detail": "用户认为判定结论有误，应复核相关规则或知识条目。",
                "count": feedback["incorrect"],
                "route": "/feedback",
            }
        )
    if feedback.get("escalated"):
        items.append(
            {
                "code": "escalated_conversations",
                "severity": "warning",
                "title": f"{feedback['escalated']} 个会话已转人工",
                "detail": "这些会话等待人工接手处理。",
                "count": feedback["escalated"],
                "route": "/conversations",
            }
        )
    elif feedback.get("openItems"):
        items.append(
            {
                "code": "open_feedback",
                "severity": "info",
                "title": f"{feedback['openItems']} 条反馈待处理",
                "detail": "包含未处理的满意度反馈与纠正建议。",
                "count": feedback["openItems"],
                "route": "/feedback",
            }
        )

    items.sort(key=lambda item: (SEVERITY_ORDER.get(item["severity"], 9), -item["count"]))
    return items
