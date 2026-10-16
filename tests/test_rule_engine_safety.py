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
    assess_instance,
    evaluate_rule_expression,
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
    passed, error = evaluate_rule_expression(expression, {"status": "active", "amount": 10})
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


@pytest.mark.parametrize(
    "expression",
    [
        # Comprehensions and lambdas are not call syntax, so a check that only inspects
        # `ast.Call` would miss them: they are the shape a sandbox escape takes when the
        # author cannot call anything.
        "[x for x in amount.__class__.__mro__]",
        "{x: 1 for x in amount.__class__.__mro__}",
        "(x for x in amount.__class__.__mro__)",
        "lambda: amount.__class__",
        "(lambda: 0)()",
        # Introspection builtins, which would hand back the module or the frame.
        "globals()",
        "locals()",
        "vars()",
        "dir()",
        "getattr(amount, '__class__')",
        "compile('1', '', 'eval')",
        "__import__('os')",
        # Names that look like free functions but reach an object's own machinery.
        "iter(amount)",
        "next(iter([1]))",
        "memoryview(b'')",
        "type(amount)",
        "print(amount)",
    ],
)
def test_the_sandbox_refuses_more_than_call_syntax(expression: str) -> None:
    """The escape surface is wider than "a function we did not allow".

    The allowlist is checked on every node, not only on `Call`, but the tests only exercised
    attribute access and disallowed calls -- the two shapes an author reaches for first. These
    are the rest: wrappers that contain an expression without being a call, the introspection
    builtins, and names that resolve to an object's own machinery.
    """
    assert validate_rule_expression(expression)["valid"] is False, expression
    passed, error = evaluate_rule_expression(expression, {"amount": 10, "status": "active"})
    assert passed is False, f"{expression} 竟然求值成功"
    assert error, f"{expression} 被拒绝但没有给出原因"


def test_a_mapping_reviewed_during_the_gate_assessment_cannot_be_published_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The publish path reads its preconditions outside the transaction that writes.

    Everything above the write happens in two other connections -- the mapping counts in one,
    the release-gate assessment outside any, because the gates read the live source databases
    for drift. A connection is a transaction boundary, so a review that lands in between is
    invisible to both, and the race goes the wrong way: an administrator publishes with every
    mapping confirmed, a second rejects them, and the first then publishes an ontology whose
    stated precondition -- 没有已确认的语义映射，不能发布本体 -- is false at the moment it is
    written. Silently, with an audit row recording the counts as they were when it started.

    Simulated by making the gate assessment itself perform the interfering edit, which is
    exactly where a real one would land: after the checks and before the write. That is
    deterministic, where a thread race would be a flake.
    """
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    bulk_review_semantic_mappings(platform_db, ontology_id, "confirmed", "业务专家", "批量确认")

    from ontology_platform import governance

    real_assess = governance._assess_release_gates

    def interfere(platform_db_arg, ontology_id_arg):
        # The concurrent actor, placed precisely: the gates are read first, the edit lands
        # after. Mutating before the assessment would test the gate instead of the window --
        # which is what the first version of this test did, and the gate blocked it, so the
        # window itself went untested.
        result = real_assess(platform_db_arg, ontology_id_arg)
        with connect(platform_db_arg) as conn:
            conn.execute(
                "update semantic_mapping set status = 'rejected' where ontology_id = ?",
                (ontology_id_arg,),
            )
        return result

    monkeypatch.setattr(governance, "_assess_release_gates", interfere)

    with pytest.raises(ValueError, match="语义映射已被改动"):
        publish_ontology(platform_db, ontology_id, "架构师")

    with connect(platform_db) as conn:
        status = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()["status"]
        ruled = conn.execute("select count(*) as count from audit_log where action = 'publish_ontology'").fetchone()[
            "count"
        ]
    assert status == "draft", "映射已被全部驳回，本体却发布了"
    assert ruled == 0, "发布被取消，却留下了「已发布」的审计记录"


def test_publishing_a_version_someone_else_published_is_not_an_error(tmp_path: Path, monkeypatch) -> None:
    """The other outcome of the same window, and the honest answer is the summary.

    Somebody else publishing this version while this call was assessing gates means the outcome
    the caller asked for is already true. Refusing would report a failure for a request that
    succeeded -- and re-publishing would write a second audit row for one publication.
    """
    platform_db, _, ontology_id = _bootstrap(tmp_path)
    bulk_review_semantic_mappings(platform_db, ontology_id, "confirmed", "业务专家", "批量确认")

    from ontology_platform import governance

    real_assess = governance._assess_release_gates

    def publish_behind_our_back(platform_db_arg, ontology_id_arg):
        result = real_assess(platform_db_arg, ontology_id_arg)
        with connect(platform_db_arg) as conn:
            conn.execute(
                "update ontology set status = 'published', published_at = current_timestamp where id = ?",
                (ontology_id_arg,),
            )
        return result

    monkeypatch.setattr(governance, "_assess_release_gates", publish_behind_our_back)

    summary = publish_ontology(platform_db, ontology_id, "架构师")
    assert summary["status"] == "published"

    with connect(platform_db) as conn:
        ruled = conn.execute("select count(*) as count from audit_log where action = 'publish_ontology'").fetchone()[
            "count"
        ]
    assert ruled == 0, "第二次调用不该再写一条发布审计——那次发布不是它做的"
