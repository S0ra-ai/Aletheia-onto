"""Rule engine safety and release gate tests.

The semantic kernel drives automation decisions, so an expression that cannot
be evaluated must never be reported as a pass. These tests pin the fail-closed
behaviour, the expression sandbox, and the publish gate.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import (
    bulk_review_semantic_mappings,
    publish_ontology,
    upsert_business_rule,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.sample_data import create_contract_sample_db
from ontology_platform.semantic_kernel import (
    _evaluate_rule,
    assess_instance,
    validate_rule_expression,
)


def _bootstrap(tmp_path: Path) -> tuple[Path, int, int]:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"
    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    return platform_db, source.id, ontology["id"]


# -- Expression sandbox --


@pytest.mark.parametrize(
    "expression",
    [
        "status.__class__",
        "len(status.__class__.__mro__) > 0",
        "amount.__class__.__base__.__subclasses__()",
        "status.__dict__",
    ],
)
def test_rule_expressions_cannot_reach_internal_attributes(expression: str) -> None:
    validation = validate_rule_expression(expression)
    assert validation["valid"] is False
    passed, error = _evaluate_rule(expression, {"status": "active", "amount": 10})
    assert passed is False
    assert error


@pytest.mark.parametrize(
    "expression",
    [
        "open_process(1)",
        "eval('1')",
        "status.upper() == 'ACTIVE'",
        "len(str(amount)) > 1",
    ],
)
def test_rule_expressions_only_allow_whitelisted_functions(expression: str) -> None:
    assert validate_rule_expression(expression)["valid"] is False


def test_valid_expressions_are_accepted_and_report_referenced_names() -> None:
    validation = validate_rule_expression("sum(payment_plan.planned_amount) == amount and title != null")
    assert validation["valid"] is True
    assert set(validation["referencedNames"]) == {"payment_plan", "amount", "title"}


def test_expression_validation_flags_unknown_source_fields() -> None:
    validation = validate_rule_expression("amount > 0 and missing_column < 3", available_names=["amount", "title"])
    assert validation["valid"] is True
    assert validation["unknownNames"] == ["missing_column"]
    assert "missing_column" in validation["warning"]


# -- Write-time validation --


def test_unparseable_rule_is_rejected_at_write_time(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    with pytest.raises(ValueError) as error:
        upsert_business_rule(
            platform_db,
            ontology_id,
            "broken_rule",
            "语法错误规则",
            "validation",
            "contract",
            "amount >",
            "blocking",
            "这条规则语法错误。",
            "规则管理员",
        )
    assert "不可执行" in str(error.value)


def test_sandbox_escaping_rule_is_rejected_at_write_time(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    with pytest.raises(ValueError):
        upsert_business_rule(
            platform_db,
            ontology_id,
            "escape_rule",
            "越权规则",
            "validation",
            "contract",
            "amount.__class__.__base__ != null",
            "blocking",
            "这条规则尝试访问内部属性。",
            "规则管理员",
        )


# -- Fail-closed evaluation --


def test_unevaluable_rule_does_not_silently_pass(tmp_path: Path) -> None:
    """A rule referencing a missing column must block, not approve.

    This is the structural-drift scenario: a blocking rule whose column was
    renamed used to be treated as passed.
    """
    platform_db, _, ontology_id = _bootstrap(tmp_path)

    baseline = assess_instance(platform_db, ontology_id, "contract", "1")
    assert baseline["decision"]["status"] == "approved"

    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into business_rule (
                ontology_id, code, name, rule_type, scope_object_code,
                expression, severity, natural_language, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, 'published')
            """,
            (
                ontology_id,
                "renamed_column_rule",
                "字段更名后的规则",
                "validation",
                "contract",
                "renamed_amount_column > 0",
                "blocking",
                "合同金额必须大于零。",
            ),
        )

    assessment = assess_instance(platform_db, ontology_id, "contract", "1")
    drifted = next(item for item in assessment["ruleResults"] if item["ruleCode"] == "renamed_column_rule")

    assert drifted["skipped"] is True
    assert drifted["passed"] is False, "无法求值的规则不能被当作通过"
    assert drifted["evaluationError"]
    assert assessment["decision"]["status"] == "blocked"
    assert "无法求值" in assessment["decision"]["recommendation"]


def test_unevaluable_warning_rule_routes_to_review(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into business_rule (
                ontology_id, code, name, rule_type, scope_object_code,
                expression, severity, natural_language, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, 'published')
            """,
            (
                ontology_id,
                "drifted_warning",
                "漂移的提示规则",
                "risk",
                "contract",
                "missing_column > 0",
                "warning",
                "提示级规则。",
            ),
        )
    assessment = assess_instance(platform_db, ontology_id, "contract", "1")
    assert assessment["decision"]["status"] == "review"


# -- Publish gate --


def test_publish_is_blocked_when_release_gates_fail(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    bulk_review_semantic_mappings(platform_db, ontology_id, "confirmed", "业务专家", "批量确认")

    with connect(platform_db) as conn:
        conn.execute("delete from business_rule where ontology_id = ?", (ontology_id,))

    with pytest.raises(ValueError) as error:
        publish_ontology(platform_db, ontology_id, "架构师")
    assert "发布门禁未通过" in str(error.value)

    with connect(platform_db) as conn:
        status = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()["status"]
    assert status == "draft"


def test_publish_can_be_forced_and_records_the_override(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    bulk_review_semantic_mappings(platform_db, ontology_id, "confirmed", "业务专家", "批量确认")
    with connect(platform_db) as conn:
        conn.execute("delete from business_rule where ontology_id = ?", (ontology_id,))

    published = publish_ontology(platform_db, ontology_id, "架构师", force=True)
    assert published["status"] == "published"
    assert published["releaseReadiness"]["forced"] is True
    assert published["releaseReadiness"]["blockers"] > 0

    with connect(platform_db) as conn:
        detail = conn.execute(
            "select detail from audit_log where action = 'publish_ontology' order by id desc limit 1"
        ).fetchone()["detail"]
    assert '"forced": true' in detail


def test_publish_succeeds_and_reports_readiness_when_gates_pass(tmp_path: Path) -> None:
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    bulk_review_semantic_mappings(platform_db, ontology_id, "confirmed", "业务专家", "批量确认")

    published = publish_ontology(platform_db, ontology_id, "架构师")
    assert published["status"] == "published"
    assert published["releaseReadiness"]["blockers"] == 0
    assert published["releaseReadiness"]["forced"] is False
    assert published["releaseReadiness"]["passedGates"] > 0
