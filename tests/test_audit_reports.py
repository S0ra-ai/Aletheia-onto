"""Audit reports: the questions an auditor arrives with, not "what happened recently".

ROADMAP stage G's last open item. Every row needed was already recorded -- `audit_log`,
`decision_record`, `inference_result`, `model_invocation` -- and exposed as three
endpoints returning the most recent 50 rows each. The gap was never data. It was that the
aggregation lived in the auditor's head.

What these tests pin down:

- **a published rule that never fired is reported as a finding**, because it is either
  dead weight in the control set or silently matching nothing -- and the second case means
  a control the organisation believes it has. An anti-join is the only way to see it: the
  rule looks perfectly healthy in any list of rules.
- **a forced publication is surfaced, never searched for**. It is legitimate, and it is
  the one action that deliberately overrides a control.
- **a verdict without an explanation trace bounds what is auditable at all**, so the
  coverage ratio is a finding rather than a statistic.
- **the period is required and half-open**, because a finding attached to the wrong period
  is a wrong finding.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.audit_reports import (
    AuditPeriodError,
    build_audit_report,
    describe_report_sections,
)
from ontology_platform.database import connect, initialize_platform_db

PERIOD = {"start": "2026-08-01", "end": "2026-09-01"}


@pytest.fixture
def platform_db(tmp_path: Path) -> Path:
    database = tmp_path / "platform.sqlite3"
    initialize_platform_db(database)
    with connect(database) as conn:
        conn.execute(
            "insert into ontology (id, name, domain, version, status) values (1, '合同管理本体', '合同管理', '1.0.0', 'published')"
        )
    return database


def _rule(conn, code: str, *, status: str = "published", rule_id: int | None = None) -> int:
    conn.execute(
        "insert into business_rule (id, ontology_id, code, name, rule_type, scope_object_code,"
        " expression, severity, natural_language, status)"
        " values (?, 1, ?, ?, 'validation', 'contract', '1 == 1', 'blocker', '', ?)",
        (rule_id, code, code, status),
    )
    return int(conn.execute("select id from business_rule where code = ?", (code,)).fetchone()["id"])


def _result(conn, rule_id: int, *, passed: int = 1, created_at: str = "2026-08-15 10:00:00") -> int:
    conn.execute(
        "insert into inference_result (rule_id, object_code, instance_id, result_type, severity,"
        " passed, explanation, evidence, created_at) values (?, 'contract', '1', 'validation',"
        " 'blocker', ?, '', '{}', ?)",
        (rule_id, passed, created_at),
    )
    return int(conn.execute("select max(id) as id from inference_result").fetchone()["id"])


# -- Scope --


def test_a_missing_period_is_refused(platform_db) -> None:
    """A report over "everything" invites the reader to treat it as a statement about a
    period it does not describe."""
    with pytest.raises(AuditPeriodError, match="必须给出起止时间"):
        build_audit_report(platform_db, start="", end="2026-09-01")


def test_a_backwards_period_is_refused(platform_db) -> None:
    with pytest.raises(AuditPeriodError, match="区间无效"):
        build_audit_report(platform_db, start="2026-09-01", end="2026-08-01")


def test_the_period_is_half_open_so_consecutive_reports_neither_overlap_nor_gap(platform_db) -> None:
    """A decision at exactly midnight belongs to one day, not two or none."""
    with connect(platform_db) as conn:
        rule_id = _rule(conn, "r_boundary")
        _result(conn, rule_id, created_at="2026-09-01 00:00:00")

    august = build_audit_report(platform_db, start="2026-08-01", end="2026-09-01")
    september = build_audit_report(platform_db, start="2026-09-01", end="2026-10-01")

    assert august["coverage"]["decisions"] == 0, "区间上界应为开区间"
    assert september["coverage"]["decisions"] == 1, "区间下界应为闭区间"


def test_every_section_states_the_question_it_answers() -> None:
    """Named by the audit question, not by the table it reads: an auditor arrives with
    "who changed a published rule", not with "show me audit_log"."""
    sections = describe_report_sections()
    assert len(sections) >= 6
    for section in sections:
        assert section["name"], section
        assert len(section["answers"]) > 10, section


# -- Rules that never fired --


def test_a_published_rule_that_never_fired_is_reported(platform_db) -> None:
    """The most useful line in a compliance report is usually the one nobody asked for."""
    with connect(platform_db) as conn:
        fired = _rule(conn, "r_fired")
        _rule(conn, "r_silent")
        _result(conn, fired)

    report = build_audit_report(platform_db, **PERIOD)

    assert [item["code"] for item in report["rules"]["triggered"]] == ["r_fired"]
    assert [item["code"] for item in report["rules"]["neverTriggered"]] == ["r_silent"]

    findings = {item["finding"] for item in report["findings"]}
    assert any("从未参与判定" in item for item in findings), report["findings"]


def test_a_draft_rule_is_not_reported_as_never_fired(platform_db) -> None:
    """An unpublished rule is not expected to fire, so listing it would be noise -- and
    noise is how a report stops being read."""
    with connect(platform_db) as conn:
        _rule(conn, "r_draft", status="draft")

    report = build_audit_report(platform_db, **PERIOD)
    assert report["rules"]["neverTriggered"] == []
    assert report["rules"]["triggered"] == []


def test_a_rule_that_fired_outside_the_period_counts_as_never_fired(platform_db) -> None:
    """The report is about a period. A control that last operated a year ago is not
    operating now, and reporting it as healthy would hide exactly that."""
    with connect(platform_db) as conn:
        rule_id = _rule(conn, "r_stale")
        _result(conn, rule_id, created_at="2025-01-01 00:00:00")

    report = build_audit_report(platform_db, **PERIOD)
    assert [item["code"] for item in report["rules"]["neverTriggered"]] == ["r_stale"]


# -- Forced publications --


def test_a_forced_publication_is_surfaced_as_a_blocker(platform_db) -> None:
    """Legitimate -- a business exception exists -- but never something an audit should
    have to search for."""
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail, created_at)"
            " values ('admin', 'publish_ontology', 'ontology', '1', ?, '2026-08-10 09:00:00')",
            (json.dumps({"force": True, "failedGates": 2}),),
        )

    report = build_audit_report(platform_db, **PERIOD)
    assert len(report["governance"]["forcedPublications"]) == 1

    blockers = [item for item in report["findings"] if item["severity"] == "blocker"]
    assert any("覆盖发布门禁" in item["finding"] for item in blockers), report["findings"]


def test_a_normal_publication_is_recorded_but_not_a_finding(platform_db) -> None:
    """Otherwise every routine publication would raise a finding, and findings that are
    always present get ignored."""
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail, created_at)"
            " values ('admin', 'publish_ontology', 'ontology', '1', ?, '2026-08-10 09:00:00')",
            (json.dumps({"force": False}),),
        )

    report = build_audit_report(platform_db, **PERIOD)
    assert len(report["governance"]["events"]) == 1
    assert report["governance"]["forcedPublications"] == []
    assert not [item for item in report["findings"] if "覆盖发布门禁" in item["finding"]]


# -- Trace coverage bounds what is auditable --


def test_a_verdict_without_a_trace_is_reported_as_unauditable(platform_db) -> None:
    """A decision without an explanation trace cannot be reviewed: the reviewer sees the
    conclusion and not what produced it."""
    with connect(platform_db) as conn:
        rule_id = _rule(conn, "r_traced")
        traced = _result(conn, rule_id)
        _result(conn, rule_id)  # no trace
        conn.execute(
            "insert into explanation_trace (inference_result_id, ontology_version, mapping_refs,"
            " source_refs, rule_refs) values (?, '1.0.0', '[]', '[]', '[]')",
            (traced,),
        )

    report = build_audit_report(platform_db, **PERIOD)
    assert report["coverage"]["decisions"] == 2
    assert report["coverage"]["withTrace"] == 1
    assert report["coverage"]["ratio"] == 0.5

    blockers = [item for item in report["findings"] if item["severity"] == "blocker"]
    assert any("解释链" in item["finding"] for item in blockers), report["findings"]


def test_an_empty_period_reports_no_ratio_rather_than_full_coverage(platform_db) -> None:
    """A ratio over zero rows is not "complete coverage", and reporting 100% would be a
    claim about nothing."""
    report = build_audit_report(platform_db, **PERIOD)
    assert report["coverage"]["decisions"] == 0
    assert report["coverage"]["ratio"] is None
    assert not [item for item in report["findings"] if "解释链" in item["finding"]]


# -- Decisions and actors --


def test_blocked_decisions_are_listed_individually_not_only_counted(platform_db) -> None:
    """A count of 40 blocked contracts answers nothing about whether any was blocked
    wrongly, and that is the question an auditor follows up."""
    with connect(platform_db) as conn:
        for index, status in enumerate(("approved", "blocked", "blocked"), start=1):
            conn.execute(
                "insert into decision_record (decision_id, decision_type, ontology_id, object_code,"
                " instance_id, status, actor, created_at) values (?, 'assessment', 1, 'contract',"
                " ?, ?, 'tester', '2026-08-12 10:00:00')",
                (f"d{index}", str(index), status),
            )

    report = build_audit_report(platform_db, **PERIOD)
    assert report["decisions"]["byStatus"] == {"approved": 1, "blocked": 2}
    assert len(report["decisions"]["blocked"]) == 2
    assert {item["decision_id"] for item in report["decisions"]["blocked"]} == {"d2", "d3"}


def test_actor_activity_is_grouped_by_actor_and_action(platform_db) -> None:
    """ "Who changed a published rule" needs the actor, not a timestamp-ordered stream."""
    with connect(platform_db) as conn:
        for actor, action in (("alice", "review_mapping"), ("alice", "review_mapping"), ("bob", "publish_ontology")):
            conn.execute(
                "insert into audit_log (actor, action, target_type, target_id, detail, created_at)"
                " values (?, ?, 'ontology', '1', '{}', '2026-08-05 09:00:00')",
                (actor, action),
            )

    report = build_audit_report(platform_db, **PERIOD)
    assert report["actors"]["byActor"]["alice"]["review_mapping"] == 2
    assert report["actors"]["byActor"]["bob"]["publish_ontology"] == 1


def test_scoping_to_one_ontology_excludes_the_others(platform_db) -> None:
    with connect(platform_db) as conn:
        conn.execute(
            "insert into ontology (id, name, domain, version, status)"
            " values (2, '设备管理本体', '设备管理', '1.0.0', 'published')"
        )
        for ontology_id, decision_id in ((1, "d1"), (2, "d2")):
            conn.execute(
                "insert into decision_record (decision_id, decision_type, ontology_id, object_code,"
                " instance_id, status, actor, created_at) values (?, 'assessment', ?, 'contract',"
                " '1', 'blocked', 'tester', '2026-08-12 10:00:00')",
                (decision_id, ontology_id),
            )

    report = build_audit_report(platform_db, ontology_id=1, **PERIOD)
    assert [item["decision_id"] for item in report["decisions"]["blocked"]] == ["d1"]


# -- Model invocations --


def test_failed_model_calls_are_reported_because_the_platform_degrades_silently(platform_db) -> None:
    """An answer produced during a model outage came from the local heuristic, and a
    reviewer comparing two answers needs to know that."""
    with connect(platform_db) as conn:
        for status in ("success", "error"):
            conn.execute(
                "insert into model_invocation (provider, model, purpose, status, created_at)"
                " values ('openrouter', 'm', 'answer', ?, '2026-08-20 12:00:00')",
                (status,),
            )

    report = build_audit_report(platform_db, **PERIOD)
    assert report["model"]["total"] == 2
    assert report["model"]["failed"] == 1
    assert any("模型调用失败" in item["finding"] for item in report["findings"])


# -- The CLI gate --


def test_the_cli_exits_non_zero_when_a_blocker_finding_exists(platform_db, capsys) -> None:
    """A report nobody reads is the normal outcome, so the exit code carries the verdict
    and the report can be a periodic check rather than only a document."""
    from ontology_platform.cli import main

    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail, created_at)"
            " values ('admin', 'publish_ontology', 'ontology', '1', ?, '2026-08-10 09:00:00')",
            (json.dumps({"force": True}),),
        )

    exit_code = main(["--platform-db", str(platform_db), "audit", "--start", PERIOD["start"], "--end", PERIOD["end"]])
    output = capsys.readouterr().out
    assert exit_code == 1
    assert "覆盖发布门禁" in output
    assert "Traceback" not in output


def test_the_cli_exits_zero_for_a_clean_period(platform_db, capsys) -> None:
    """A gate nothing can pass gets bypassed rather than fixed."""
    from ontology_platform.cli import main

    exit_code = main(["--platform-db", str(platform_db), "audit", "--start", PERIOD["start"], "--end", PERIOD["end"]])
    capsys.readouterr()
    assert exit_code == 0


def test_the_cli_reports_a_bad_period_without_a_traceback(platform_db, capsys) -> None:
    from ontology_platform.cli import main

    exit_code = main(["--platform-db", str(platform_db), "audit", "--start", "2026-09-01", "--end", "2026-08-01"])
    captured = capsys.readouterr()
    assert exit_code != 0
    assert "Traceback" not in captured.out + captured.err
