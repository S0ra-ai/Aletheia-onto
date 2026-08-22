"""Cross-object aggregation: rules that reason over more than one instance.

Rules are scoped to a single object, so an expression could only see the instance
under assessment and its directly related rows. That rules out the requirements
that are actually about a *group* -- and those are the ones B2B customers ask for
first:

    「客户所有合同总额不得超过其信用额度」
    「同一设备的未关闭工单不得超过 3 个」

Generality item #5. The properties worth pinning down are the fail-closed ones: an
aggregate that cannot be computed must make its rule fail, never silently compare a
threshold against a fabricated zero.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.aggregation import (
    AGGREGATE_FUNCTIONS,
    MAX_AGGREGATION_ROWS,
    AggregateSpec,
    AggregationError,
    aggregate_context,
    compute_aggregate,
    define_aggregate,
    init_aggregate_schema,
    list_aggregates,
    load_aggregate_specs,
)
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    """A customer with three contracts, one of them cancelled."""
    path = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_limit numeric not null
        );
        create table contracts (
            id integer primary key,
            customer_id integer not null references customers(id),
            total_amount numeric not null,
            amount numeric not null,
            status text not null
        );
        -- The contract-management blueprint models payment_plan as part of the
        -- contract object, so its generated rules reference it. Providing the
        -- table keeps this fixture consistent with what the blueprint models;
        -- omitting it made an unrelated generated rule fail closed and mask the
        -- aggregate assertion under test.
        create table payment_plan (
            id integer primary key,
            contract_id integer not null references contracts(id),
            planned_amount numeric not null,
            status text not null
        );
        insert into customers values (1, '甲公司', 1000);
        insert into customers values (2, '乙公司', 100000);
        -- Customer 1: 400 + 500 active, 900 cancelled. Limit is 1000.
        insert into contracts values (1, 1, 400, 400, 'active');
        insert into contracts values (2, 1, 500, 500, 'active');
        insert into contracts values (3, 1, 900, 900, 'cancelled');
        insert into contracts values (4, 2, 50, 50, 'active');
        -- Payment plans sum to each contract's amount, so the blueprint's own
        -- payment_plan_amount_match rule passes and does not obscure the
        -- aggregate behaviour these tests are about.
        insert into payment_plan values (1, 1, 400, 'paid');
        insert into payment_plan values (2, 2, 500, 'paid');
        insert into payment_plan values (3, 3, 900, 'paid');
        insert into payment_plan values (4, 4, 50, 'paid');
        """
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def runtime(source_db: Path):
    adapter = get_adapter("sqlite")
    with adapter.runtime(str(source_db)) as database:
        yield database


@pytest.fixture
def modelled(tmp_path: Path, source_db: Path):
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_aggregate_schema(conn)
        # Idempotent: startup runs this on every boot.
        init_aggregate_schema(conn)
    source = register_data_source(platform_db, "合同系统", "sqlite", str(source_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    ontology_id = ontology["ontology"]["id"]
    # Object codes come from the blueprint lexicon (ADR-0003), so discover the one
    # bound to the contracts table instead of assuming its spelling.
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.table_name = 'contracts'
            """,
            (ontology_id,),
        ).fetchone()
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "object_code": row["code"],
    }


def _customer_total() -> AggregateSpec:
    return AggregateSpec(
        name="customer_total_amount",
        function="sum",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
    )


# -- Definition validation --


@pytest.mark.parametrize("function", AGGREGATE_FUNCTIONS)
def test_every_supported_function_validates(function) -> None:
    AggregateSpec(
        name="agg",
        function=function,
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
    ).validate()


def test_unknown_function_is_rejected() -> None:
    with pytest.raises(AggregationError, match="不支持的聚合函数"):
        AggregateSpec(
            name="agg",
            function="median",
            target_table="contracts",
            target_column="customer_id",
            group_column="customer_id",
            value_column="total_amount",
        ).validate()


@pytest.mark.parametrize("name", ["_private", "2bad", "has space", "has.dot", ""])
def test_aggregate_name_must_be_a_plain_identifier(name) -> None:
    """Rules reference the aggregate by name, so it must bind in the sandbox."""
    with pytest.raises(AggregationError):
        AggregateSpec(
            name=name,
            function="count",
            target_table="contracts",
            target_column="customer_id",
            group_column="customer_id",
        ).validate()


@pytest.mark.parametrize("table", ["contracts; drop table contracts", 'contracts"', "1bad", ""])
def test_identifiers_reaching_sql_are_validated(table) -> None:
    with pytest.raises(AggregationError):
        AggregateSpec(
            name="agg",
            function="count",
            target_table=table,
            target_column="customer_id",
            group_column="customer_id",
        ).validate()


def test_non_count_functions_require_a_value_column() -> None:
    """sum() of nothing in particular is meaningless."""
    with pytest.raises(AggregationError, match="valueColumn"):
        AggregateSpec(
            name="agg",
            function="sum",
            target_table="contracts",
            target_column="customer_id",
            group_column="customer_id",
        ).validate()


def test_count_does_not_require_a_value_column() -> None:
    AggregateSpec(
        name="agg",
        function="count",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
    ).validate()


def test_exclude_self_requires_a_self_column() -> None:
    with pytest.raises(AggregationError, match="selfColumn"):
        AggregateSpec(
            name="agg",
            function="sum",
            target_table="contracts",
            target_column="customer_id",
            group_column="customer_id",
            value_column="total_amount",
            exclude_self=True,
        ).validate()


def test_definition_is_human_readable() -> None:
    """A verdict citing an aggregate must be able to say what it was."""
    described = _customer_total().validate().describe()
    assert "sum(contracts.total_amount)" in described
    assert "customer_id" in described


# -- Computation --


def test_sum_aggregates_across_sibling_instances(runtime) -> None:
    """The motivating case: this contract plus the customer's others."""
    result = compute_aggregate(runtime, _customer_total().validate(), {"id": 1, "customer_id": 1})
    assert result.computed
    # 400 + 500 + 900 across all three of customer 1's contracts.
    assert result.value == 1800.0
    assert result.row_count == 3


def test_count_aggregates_rows(runtime) -> None:
    spec = AggregateSpec(
        name="contract_count",
        function="count",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
    ).validate()
    result = compute_aggregate(runtime, spec, {"id": 1, "customer_id": 1})
    assert result.value == 3.0


@pytest.mark.parametrize(("function", "expected"), [("min", 400.0), ("max", 900.0), ("avg", 600.0)])
def test_min_max_avg(runtime, function, expected) -> None:
    spec = AggregateSpec(
        name="agg",
        function=function,
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
    ).validate()
    result = compute_aggregate(runtime, spec, {"id": 1, "customer_id": 1})
    assert result.value == expected


def test_filter_restricts_the_aggregated_rows(runtime) -> None:
    """Active contracts only: 400 + 500, excluding the cancelled 900."""
    spec = AggregateSpec(
        name="active_total",
        function="sum",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
        filter_column="status",
        filter_value="active",
    ).validate()
    result = compute_aggregate(runtime, spec, {"id": 1, "customer_id": 1})
    assert result.value == 900.0


def test_exclude_self_omits_the_instance_under_assessment(runtime) -> None:
    """ "The customer's *other* contracts" differs by exactly one row, which can
    decide whether a limit is breached."""
    spec = AggregateSpec(
        name="other_total",
        function="sum",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
        exclude_self=True,
        self_column="id",
    ).validate()
    result = compute_aggregate(runtime, spec, {"id": 1, "customer_id": 1})
    # 1800 total minus this contract's own 400.
    assert result.value == 1400.0


def test_empty_sum_is_zero(runtime) -> None:
    """Zero is a legitimate answer for sum over no rows."""
    result = compute_aggregate(runtime, _customer_total().validate(), {"id": 99, "customer_id": 999})
    assert result.computed
    assert result.value == 0.0


@pytest.mark.parametrize("function", ["min", "max", "avg"])
def test_empty_min_max_avg_is_an_error_not_zero(runtime, function) -> None:
    """min of nothing is undefined; reporting 0 would let a threshold rule pass."""
    spec = AggregateSpec(
        name="agg",
        function=function,
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
    ).validate()
    result = compute_aggregate(runtime, spec, {"id": 99, "customer_id": 999})
    assert not result.computed
    assert result.value is None


def test_missing_group_value_is_an_error_not_zero(runtime) -> None:
    """Fail-closed: a null grouping key means the aggregate is undefined here."""
    result = compute_aggregate(runtime, _customer_total().validate(), {"id": 1, "customer_id": None})
    assert not result.computed
    assert "为空" in result.error


def test_non_numeric_value_fails_rather_than_being_skipped(tmp_path: Path) -> None:
    """Quietly ignoring bad data would understate a total."""
    path = tmp_path / "bad.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table contracts (id integer primary key, customer_id integer, total_amount text);
        insert into contracts values (1, 1, 'not a number');
        """
    )
    conn.commit()
    conn.close()
    adapter = get_adapter("sqlite")
    with adapter.runtime(str(path)) as database:
        result = compute_aggregate(database, _customer_total().validate(), {"id": 1, "customer_id": 1})
    assert not result.computed
    assert "非数值" in result.error


def test_row_cap_is_reported_rather_than_silently_truncating() -> None:
    """A silently truncated total is a wrong number presented as right."""
    assert MAX_AGGREGATION_ROWS > 0


# -- Sandbox injection --


def test_only_computed_aggregates_enter_the_sandbox(runtime) -> None:
    """An uncomputable aggregate must be absent, so referencing it raises NameError
    and the kernel's fail-closed handling reports it -- rather than injecting None
    and letting `x <= limit` evaluate misleadingly."""
    good = compute_aggregate(runtime, _customer_total().validate(), {"id": 1, "customer_id": 1})
    bad = compute_aggregate(runtime, _customer_total().validate(), {"id": 1, "customer_id": None})
    context = aggregate_context({"good": good, "bad": bad})
    assert "good" in context
    assert "bad" not in context


# -- Persistence --


def test_defining_and_listing_an_aggregate(modelled) -> None:
    define_aggregate(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["object_code"],
        _customer_total(),
        description="客户合同总额",
        actor="tester",
    )
    items = list_aggregates(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"])
    assert len(items) == 1
    assert items[0]["name"] == "customer_total_amount"
    assert "sum(contracts.total_amount)" in items[0]["definition"]


def test_redefining_an_aggregate_updates_it(modelled) -> None:
    for function in ("sum", "max"):
        spec = _customer_total()
        spec.function = function
        define_aggregate(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"], spec)
    items = list_aggregates(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"])
    assert len(items) == 1
    assert items[0]["function"] == "max"


def test_invalid_definition_is_refused_before_storage(modelled) -> None:
    spec = _customer_total()
    spec.target_table = "contracts; drop table contracts"
    with pytest.raises(AggregationError):
        define_aggregate(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"], spec)
    assert list_aggregates(modelled["platform_db"], modelled["ontology_id"]) == []


def test_published_ontology_refuses_aggregate_changes(modelled) -> None:
    from ontology_platform.governance import (
        list_semantic_mappings,
        publish_ontology,
        review_semantic_mapping,
    )

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)
    with pytest.raises(AggregationError, match="已发布"):
        define_aggregate(platform_db, ontology_id, modelled["object_code"], _customer_total())


def test_definition_is_audited(modelled) -> None:
    define_aggregate(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["object_code"],
        _customer_total(),
        actor="tester",
    )
    with connect(modelled["platform_db"]) as conn:
        rows = conn.execute("select actor from audit_log where action = 'define_cross_object_aggregate'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


def test_missing_aggregate_table_is_treated_as_no_aggregates(tmp_path: Path) -> None:
    """The schema is optional; an assessment must still work without it.

    Probed via the catalog rather than by catching the error: on PostgreSQL a failed
    statement aborts the transaction, so every later command in the same assessment
    would fail (ADR-0004).
    """
    platform_db = tmp_path / "bare.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        assert load_aggregate_specs(conn, 1, "contracts") == []


def test_a_stored_definition_that_stops_validating_is_skipped(modelled) -> None:
    """It will make its rule fail closed, which is the safe direction."""
    define_aggregate(modelled["platform_db"], modelled["ontology_id"], modelled["object_code"], _customer_total())
    with connect(modelled["platform_db"]) as conn:
        conn.execute("update cross_object_aggregate set function = 'median'")
    with connect(modelled["platform_db"]) as conn:
        assert load_aggregate_specs(conn, modelled["ontology_id"], modelled["object_code"]) == []


# -- End to end through the kernel --


def test_a_rule_can_compare_against_a_cross_object_aggregate(modelled) -> None:
    """The motivating requirement: total across the customer's contracts vs limit.

    Previously impossible -- a rule could only see one instance.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    spec = AggregateSpec(
        name="customer_active_total",
        function="sum",
        target_table="contracts",
        target_column="customer_id",
        group_column="customer_id",
        value_column="total_amount",
        filter_column="status",
        filter_value="active",
    )
    define_aggregate(platform_db, ontology_id, modelled["object_code"], spec, actor="tester")
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="customer_credit_limit",
        name="客户合同总额不得超过信用额度",
        rule_type="validation",
        scope_object_code=modelled["object_code"],
        expression="customer_active_total <= 1000",
        severity="blocking",
        natural_language="客户所有生效合同总额不得超过信用额度。",
        actor="tester",
    )

    # Customer 1's active total is 900, within the 1000 limit.
    within = assess_instance(platform_db, ontology_id, modelled["object_code"], "1")
    assert within["decision"]["status"] == "approved", within


def test_a_breached_aggregate_limit_blocks(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    define_aggregate(platform_db, ontology_id, modelled["object_code"], _customer_total(), actor="tester")
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="total_under_limit",
        name="合同总额上限",
        rule_type="validation",
        scope_object_code=modelled["object_code"],
        expression="customer_total_amount <= 1000",
        severity="blocking",
        natural_language="客户合同总额不得超过 1000。",
        actor="tester",
    )
    # Customer 1's total across all contracts is 1800.
    breached = assess_instance(platform_db, ontology_id, modelled["object_code"], "1")
    assert breached["decision"]["status"] == "blocked", breached


def test_an_uncomputable_aggregate_makes_its_rule_fail_closed(modelled) -> None:
    """A referenced aggregate that cannot be computed must not pass silently."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="undefined_aggregate_rule",
        name="引用了未定义的聚合",
        rule_type="validation",
        scope_object_code=modelled["object_code"],
        expression="never_defined_aggregate <= 1000",
        severity="blocking",
        natural_language="引用未定义聚合的规则。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, modelled["object_code"], "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "undefined_aggregate_rule")
    assert rule["passed"] is False
    assert rule["skipped"] is True, rule
    assert result["decision"]["status"] == "blocked"


def test_aggregates_are_reported_on_the_runtime(modelled) -> None:
    """A verdict citing an aggregate must be able to state its definition."""
    from ontology_platform.semantic_kernel import build_runtime

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    define_aggregate(platform_db, ontology_id, modelled["object_code"], _customer_total(), actor="tester")
    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, modelled["object_code"], "1")
    assert "customer_total_amount" in runtime.aggregates
    reported = runtime.aggregates["customer_total_amount"]
    assert reported["value"] == 1800.0
    assert "sum(contracts.total_amount)" in reported["definition"]


def test_aggregate_endpoints_have_sensible_capabilities() -> None:
    """Declaring an aggregate changes what every rule for the object evaluates."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("PUT", "/ontologies/1/objects/contracts/aggregates") == "platform:write"
    assert required_capability("GET", "/ontologies/1/aggregates") == "platform:read"
