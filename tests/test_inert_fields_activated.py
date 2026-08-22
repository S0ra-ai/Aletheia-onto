"""Three fields that were stored but never evaluated.

`guard_expression`, `filter_expression` and `depends_on` all had storage, API
surface and UI, but no effect. That combination is worse than a missing feature:
an operator configures a gate, sees it saved, and believes it is active.

`filter_expression` was the most serious -- SECURITY.md had to warn that row-level
isolation did not exist despite the field being there. These tests pin down that
each field now changes behaviour, and that all three fail closed.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import (
    assess_instance,
    order_rules_by_dependency,
    parse_depends_on,
)
from ontology_platform.workflow_permission import (
    add_workflow_transition,
    check_permission,
    create_role,
    create_workflow,
    enter_workflow,
    init_workflow_and_permission_schema,
    transition_instance,
    upsert_permission_policy,
)


@pytest.fixture
def platform(tmp_path: Path):
    platform_db = tmp_path / "platform.sqlite3"
    business_db = tmp_path / "business.sqlite3"
    initialize_platform_db(platform_db)

    conn = sqlite3.connect(business_db)
    conn.executescript(
        """
        create table purchase (
            id integer primary key,
            amount numeric not null,
            approved integer not null default 0,
            owner text not null default ''
        );
        insert into purchase values (1, 5000, 1, 'alice');
        insert into purchase values (2, 20000, 0, 'bob');
        """
    )
    conn.commit()
    conn.close()

    source = register_data_source(platform_db, "采购系统", "sqlite", str(business_db), domain="采购管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    with connect(platform_db) as c:
        init_workflow_and_permission_schema(c)
    return {
        "platform_db": platform_db,
        "ontology_id": ontology["ontology"]["id"],
        "source_id": source.id,
    }


# -- guard_expression --


def _workflow_with_guard(platform, guard: str):
    workflow = create_workflow(
        platform["platform_db"],
        platform["ontology_id"],
        "purchase",
        "采购审批",
        initial_state="draft",
    )
    workflow_id = workflow["id"]
    add_workflow_transition(
        platform["platform_db"],
        workflow_id,
        "draft",
        "approved",
        "approve",
        "审批通过",
        guard_expression=guard,
    )
    return workflow_id


def test_guard_blocks_a_transition_when_its_condition_fails(platform) -> None:
    """Previously the guard was stored and ignored, so this transition succeeded."""
    workflow_id = _workflow_with_guard(platform, "approved == 1")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "2")

    # Purchase 2 has approved = 0.
    with pytest.raises(ValueError, match="流转守卫未通过"):
        transition_instance(platform["platform_db"], workflow_id, "2", "approve", actor="tester")


def test_guard_allows_a_transition_when_its_condition_holds(platform) -> None:
    workflow_id = _workflow_with_guard(platform, "approved == 1")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "1")

    state = transition_instance(platform["platform_db"], workflow_id, "1", "approve", actor="tester")
    assert state["current_state"] == "approved"


def test_transition_without_a_guard_is_unaffected(platform) -> None:
    """Behaviour must not change for the common ungated case."""
    workflow_id = _workflow_with_guard(platform, "")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "2")
    state = transition_instance(platform["platform_db"], workflow_id, "2", "approve", actor="tester")
    assert state["current_state"] == "approved"


def test_unevaluable_guard_blocks_rather_than_passes(platform) -> None:
    """Fail-closed, per ADR-0002: a broken guard must not wave the transition through."""
    workflow_id = _workflow_with_guard(platform, "no_such_column == 1")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "1")
    with pytest.raises(ValueError, match="流转守卫未通过"):
        transition_instance(platform["platform_db"], workflow_id, "1", "approve", actor="tester")


def test_guard_cannot_escape_the_rule_sandbox(platform) -> None:
    """Guards reuse the rule sandbox, so escapes are rejected the same way."""
    workflow_id = _workflow_with_guard(platform, "__import__('os').system('true') == 0")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "1")
    with pytest.raises(ValueError, match="流转守卫未通过"):
        transition_instance(platform["platform_db"], workflow_id, "1", "approve", actor="tester")


def test_guard_outcome_is_recorded_in_history(platform) -> None:
    """An auditor must be able to see the gate ran, not just that it passed."""
    from ontology_platform.workflow_permission import get_instance_history

    workflow_id = _workflow_with_guard(platform, "approved == 1")
    enter_workflow(platform["platform_db"], workflow_id, "purchase", "1")
    transition_instance(platform["platform_db"], workflow_id, "1", "approve", actor="tester")

    history = get_instance_history(platform["platform_db"], workflow_id, "1")
    entry = next(item for item in history if item.get("action_code") == "approve")
    assert "guard" in str(entry.get("metadata", "")), entry


# -- filter_expression --


def _role_with_filter(platform, expression: str, *, can_read: bool = True):
    role = create_role(platform["platform_db"], "auditor", "审计员")
    upsert_permission_policy(
        platform["platform_db"],
        role["id"],
        "purchase",
        can_read=can_read,
        filter_expression=expression,
    )
    return role


def test_row_filter_denies_an_instance_that_fails_it(platform) -> None:
    """This is the security-relevant one: the filter now actually applies."""
    _role_with_filter(platform, "amount <= 10000")
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read", instance_id="2")
    assert result["filterApplied"] is True
    assert result["allowed"] is False, result


def test_row_filter_allows_an_instance_that_satisfies_it(platform) -> None:
    _role_with_filter(platform, "amount <= 10000")
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read", instance_id="1")
    assert result["filterApplied"] is True
    assert result["allowed"] is True, result


def test_omitting_the_instance_reports_the_filter_as_unevaluated(platform) -> None:
    """ "I did not evaluate this" must be distinguishable from "nothing to evaluate"."""
    _role_with_filter(platform, "amount <= 10000")
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read")
    assert result["filterApplied"] is False
    assert result["filterExpression"] == "amount <= 10000"
    assert "未求值" in result["reason"]


def test_unevaluable_filter_denies_access(platform) -> None:
    """Fail-closed: a broken filter must not grant access to every row."""
    _role_with_filter(platform, "missing_column == 1")
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read", instance_id="1")
    assert result["allowed"] is False
    assert result["filterApplied"] is True


def test_capability_denial_short_circuits_the_filter(platform) -> None:
    """No point evaluating a row filter when the operation itself is denied."""
    _role_with_filter(platform, "amount <= 10000", can_read=False)
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read", instance_id="1")
    assert result["allowed"] is False
    assert result["filterApplied"] is False


def test_policy_without_a_filter_behaves_as_before(platform) -> None:
    _role_with_filter(platform, "")
    result = check_permission(platform["platform_db"], "auditor", "purchase", "read", instance_id="2")
    assert result["allowed"] is True
    assert result["filterExpression"] is None


# -- depends_on --


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('["a", "b"]', ["a", "b"]),
        ("[]", []),
        ("", []),
        (None, []),
        ("not json", []),
        ('{"a": 1}', []),
        ('["  spaced  "]', ["spaced"]),
    ],
)
def test_depends_on_parsing_tolerates_bad_values(raw, expected) -> None:
    """A malformed hint must not break assessment entirely."""
    assert parse_depends_on(raw) == expected


class _FakeRule(dict):
    """Stands in for a sqlite3.Row, which supports keys()."""

    def keys(self):
        return super().keys()


def test_rules_are_ordered_so_prerequisites_run_first() -> None:
    rules = [
        _FakeRule(code="b", depends_on='["a"]'),
        _FakeRule(code="a", depends_on="[]"),
    ]
    assert [rule["code"] for rule in order_rules_by_dependency(rules)] == ["a", "b"]


def test_ordering_is_stable_when_nothing_declares_dependencies() -> None:
    """The common case must keep the existing priority/severity ordering."""
    rules = [_FakeRule(code=code, depends_on="[]") for code in ("x", "y", "z")]
    assert [rule["code"] for rule in order_rules_by_dependency(rules)] == ["x", "y", "z"]


def test_dependency_cycles_are_broken_not_raised() -> None:
    """A cyclic declaration is a modelling error, not a reason to refuse assessment."""
    rules = [
        _FakeRule(code="a", depends_on='["b"]'),
        _FakeRule(code="b", depends_on='["a"]'),
    ]
    ordered = order_rules_by_dependency(rules)
    assert {rule["code"] for rule in ordered} == {"a", "b"}


def test_self_dependency_does_not_deadlock() -> None:
    rules = [_FakeRule(code="a", depends_on='["a"]')]
    assert [rule["code"] for rule in order_rules_by_dependency(rules)] == ["a"]


def test_a_rule_is_not_evaluated_when_its_prerequisite_failed(platform) -> None:
    """Previously depends_on was ignored, so the dependent rule ran regardless."""
    platform_db, ontology_id = platform["platform_db"], platform["ontology_id"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="must_be_approved",
        name="必须已审批",
        rule_type="validation",
        scope_object_code="purchase",
        expression="approved == 1",
        severity="blocking",
        natural_language="采购必须已审批。",
        actor="test",
    )
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="amount_within_limit",
        name="金额在限额内",
        rule_type="validation",
        scope_object_code="purchase",
        expression="amount <= 10000",
        severity="warning",
        natural_language="金额不得超过限额。",
        depends_on='["must_be_approved"]',
        actor="test",
    )

    # Purchase 2 is unapproved, so the prerequisite fails.
    result = assess_instance(platform_db, ontology_id, "purchase", "2")
    dependent = next(item for item in result["ruleResults"] if item["ruleCode"] == "amount_within_limit")
    assert dependent["passed"] is False
    assert "前置规则未通过" in dependent["evaluationError"], dependent


def test_a_dependent_rule_evaluates_normally_once_its_prerequisite_passes(platform) -> None:
    platform_db, ontology_id = platform["platform_db"], platform["ontology_id"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="must_be_approved",
        name="必须已审批",
        rule_type="validation",
        scope_object_code="purchase",
        expression="approved == 1",
        severity="blocking",
        natural_language="采购必须已审批。",
        actor="test",
    )
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="amount_within_limit",
        name="金额在限额内",
        rule_type="validation",
        scope_object_code="purchase",
        expression="amount <= 10000",
        severity="warning",
        natural_language="金额不得超过限额。",
        depends_on='["must_be_approved"]',
        actor="test",
    )

    # Purchase 1 is approved and within the limit.
    result = assess_instance(platform_db, ontology_id, "purchase", "1")
    dependent = next(item for item in result["ruleResults"] if item["ruleCode"] == "amount_within_limit")
    assert dependent["passed"] is True
    assert dependent["evaluationError"] == ""


# -- permission_policy ontology dimension --


def test_same_object_code_in_two_ontologies_no_longer_shares_a_policy(platform) -> None:
    """The defect recorded in architecture-debt: policies were keyed on a bare code."""
    role = create_role(platform["platform_db"], "reviewer2", "复核员")
    upsert_permission_policy(
        platform["platform_db"],
        role["id"],
        "purchase",
        can_read=True,
        ontology_id=platform["ontology_id"],
    )
    upsert_permission_policy(
        platform["platform_db"],
        role["id"],
        "purchase",
        can_read=False,
        ontology_id=platform["ontology_id"] + 999,
    )

    allowed = check_permission(
        platform["platform_db"],
        "reviewer2",
        "purchase",
        "read",
        ontology_id=platform["ontology_id"],
    )
    denied = check_permission(
        platform["platform_db"],
        "reviewer2",
        "purchase",
        "read",
        ontology_id=platform["ontology_id"] + 999,
    )
    assert allowed["allowed"] is True, allowed
    assert denied["allowed"] is False, denied


def test_wildcard_policy_still_applies_when_no_specific_one_exists(platform) -> None:
    """Existing single-ontology deployments must keep working unchanged."""
    role = create_role(platform["platform_db"], "legacy", "遗留角色")
    # ontology_id defaults to 0, meaning "any ontology".
    upsert_permission_policy(platform["platform_db"], role["id"], "purchase", can_read=True)
    result = check_permission(
        platform["platform_db"],
        "legacy",
        "purchase",
        "read",
        ontology_id=platform["ontology_id"],
    )
    assert result["allowed"] is True


def test_a_specific_policy_overrides_the_wildcard(platform) -> None:
    role = create_role(platform["platform_db"], "mixed", "混合角色")
    upsert_permission_policy(platform["platform_db"], role["id"], "purchase", can_read=True)
    upsert_permission_policy(
        platform["platform_db"],
        role["id"],
        "purchase",
        can_read=False,
        ontology_id=platform["ontology_id"],
    )
    result = check_permission(
        platform["platform_db"],
        "mixed",
        "purchase",
        "read",
        ontology_id=platform["ontology_id"],
    )
    assert result["allowed"] is False, result
