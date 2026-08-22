"""Instance resolvers: the conformance suite.

`business_object.source_table_id` is a single foreign key, so an object could only
mirror one table. That is generality item #1 -- the assumption that makes master/
detail objects, discriminator-partitioned tables, view-backed objects and
cross-source objects unmodellable.

This file serves two audiences. It verifies the built-in resolvers, and it is the
suite a third party runs against its own resolver. The contract:

1. `fetch()` returns one complete record or None.
2. `list_ids()` returns tokens `fetch()` accepts -- the round trip is what makes
   batch assessment work, and it is the property most easily got wrong.
3. `columns()` reports every name a rule may reference.
4. Identifiers from configuration are validated, never interpolated blindly.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.instance_resolver import (
    CUSTOM_SQL,
    DISCRIMINATED,
    JOINED_TABLES,
    SINGLE_TABLE,
    ResolverError,
    ResolverSpec,
    build_resolver,
    register_resolver,
    supported_resolver_kinds,
    validate_identifier,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance, list_instance_ids


@pytest.fixture
def source_db(tmp_path: Path) -> Path:
    """A schema exercising every resolver kind."""
    path = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        create table orders (
            id integer primary key,
            order_no text not null,
            total numeric not null,
            status text not null
        );
        create table order_line (
            id integer primary key,
            order_id integer not null,
            sku text not null,
            amount numeric not null
        );
        -- One physical table holding two business objects.
        create table party (
            id integer primary key,
            name text not null,
            party_type text not null,
            credit_limit numeric
        );
        insert into orders values (1, 'SO-1', 300, 'open');
        insert into orders values (2, 'SO-2', 0, 'open');
        insert into order_line values (1, 1, 'A', 100);
        insert into order_line values (2, 1, 'B', 200);
        insert into order_line values (3, 2, 'C', 0);
        insert into party values (1, '客户甲', 'customer', 5000);
        insert into party values (2, '供应商乙', 'supplier', null);
        insert into party values (3, '客户丙', 'customer', 100);
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


# -- Identifier validation: configuration reaches SQL text --


@pytest.mark.parametrize(
    "value",
    [
        "orders; drop table orders",
        "orders--",
        'orders"',
        "1orders",
        "",
        "has space",
        "a" * 65,
    ],
)
def test_unsafe_identifiers_are_rejected(value) -> None:
    with pytest.raises(ResolverError):
        validate_identifier(value)


def test_injection_in_a_table_name_is_refused_at_construction() -> None:
    """Fail when the spec is built, before it can produce a wrong verdict."""
    with pytest.raises(ResolverError):
        build_resolver(ResolverSpec(kind=SINGLE_TABLE, table="orders; drop table orders"))


@pytest.mark.parametrize(
    "spec",
    [
        ResolverSpec(kind=CUSTOM_SQL, query="delete from orders"),
        ResolverSpec(kind=CUSTOM_SQL, query="update orders set total = 0"),
        ResolverSpec(kind=CUSTOM_SQL, query="select 1; drop table orders"),
        ResolverSpec(kind=CUSTOM_SQL, query=""),
    ],
)
def test_custom_sql_only_accepts_read_queries(spec) -> None:
    with pytest.raises(ResolverError):
        build_resolver(spec)


def test_custom_sql_accepts_a_cte() -> None:
    """`with` is a legitimate way to express a resolver query."""
    resolver = build_resolver(
        ResolverSpec(
            kind=CUSTOM_SQL,
            query="with big as (select * from orders where total > 0) select * from big",
            id_column="id",
        )
    )
    assert resolver.kind == CUSTOM_SQL


@pytest.mark.parametrize(
    "spec",
    [
        ResolverSpec(kind=JOINED_TABLES, table="orders", joins=[]),
        ResolverSpec(kind=DISCRIMINATED, table="party", discriminator_column="party_type"),
    ],
)
def test_incomplete_configurations_are_rejected(spec) -> None:
    with pytest.raises(ResolverError):
        build_resolver(spec)


def test_unknown_resolver_kind_names_the_alternatives() -> None:
    with pytest.raises(ResolverError, match=SINGLE_TABLE):
        build_resolver(ResolverSpec(kind="telepathy", table="orders"))


# -- Spec serialization --


def test_spec_round_trips_through_json() -> None:
    spec = ResolverSpec(
        kind=JOINED_TABLES,
        table="orders",
        primary_key="id",
        joins=[{"table": "order_line", "foreignKey": "order_id"}],
    )
    restored = ResolverSpec.from_json(spec.to_json())
    assert restored.kind == JOINED_TABLES
    assert restored.joins == spec.joins


@pytest.mark.parametrize("raw", ["", None, "not json", "[]", '"text"'])
def test_malformed_spec_degrades_to_single_table(raw) -> None:
    """The object still has a table, so the conservative reading keeps it usable."""
    spec = ResolverSpec.from_json(raw, table="orders", primary_key="id")
    assert spec.kind == SINGLE_TABLE
    assert spec.table == "orders"


# -- single_table: the unchanged default --


def test_single_table_fetches_one_record(runtime) -> None:
    resolver = build_resolver(ResolverSpec(kind=SINGLE_TABLE, table="orders", primary_key="id"))
    record = resolver.fetch(runtime, "1")
    assert record is not None
    assert record["order_no"] == "SO-1"


def test_single_table_returns_none_for_a_missing_instance(runtime) -> None:
    resolver = build_resolver(ResolverSpec(kind=SINGLE_TABLE, table="orders", primary_key="id"))
    assert resolver.fetch(runtime, "999") is None


def test_single_table_ids_round_trip(runtime) -> None:
    """Contract point 2: every listed id must be fetchable."""
    resolver = build_resolver(ResolverSpec(kind=SINGLE_TABLE, table="orders", primary_key="id"))
    for instance_id in resolver.list_ids(runtime, 10):
        assert resolver.fetch(runtime, instance_id) is not None


def test_single_table_reports_its_columns(runtime) -> None:
    resolver = build_resolver(ResolverSpec(kind=SINGLE_TABLE, table="orders", primary_key="id"))
    assert {"id", "order_no", "total", "status"} <= set(resolver.columns(runtime))


# -- joined_tables: master/detail --


def _joined() -> ResolverSpec:
    return ResolverSpec(
        kind=JOINED_TABLES,
        table="orders",
        primary_key="id",
        joins=[{"table": "order_line", "foreignKey": "order_id"}],
    )


def test_joined_tables_attaches_child_rows(runtime) -> None:
    """The order + order_line case that a single foreign key could not express."""
    resolver = build_resolver(_joined())
    record = resolver.fetch(runtime, "1")
    assert record is not None
    assert record["order_no"] == "SO-1"
    assert len(record["order_line"]) == 2
    assert {line["sku"] for line in record["order_line"]} == {"A", "B"}


def test_joined_tables_child_list_is_empty_not_missing(runtime) -> None:
    """A rule saying sum(order_line.amount) must not fail on a childless parent."""
    conn = sqlite3.connect(runtime.conn.execute("pragma database_list").fetchone()["file"])
    conn.execute("insert into orders values (9, 'SO-9', 0, 'open')")
    conn.commit()
    conn.close()
    resolver = build_resolver(_joined())
    record = resolver.fetch(runtime, "9")
    assert record is not None
    assert record["order_line"] == []


def test_joined_tables_reports_all_its_tables() -> None:
    """Drift detection and lineage need every table the object reads."""
    assert build_resolver(_joined()).tables() == ("orders", "order_line")


def test_joined_tables_columns_include_child_names(runtime) -> None:
    """A rule addresses children by table name, so validation must know them."""
    columns = build_resolver(_joined()).columns(runtime)
    assert "order_line" in columns
    assert "order_no" in columns


def test_joined_tables_ids_round_trip(runtime) -> None:
    resolver = build_resolver(_joined())
    for instance_id in resolver.list_ids(runtime, 10):
        assert resolver.fetch(runtime, instance_id) is not None


# -- discriminated: one table, several objects --


def _customer() -> ResolverSpec:
    return ResolverSpec(
        kind=DISCRIMINATED,
        table="party",
        primary_key="id",
        discriminator_column="party_type",
        discriminator_value="customer",
    )


def _supplier() -> ResolverSpec:
    return ResolverSpec(
        kind=DISCRIMINATED,
        table="party",
        primary_key="id",
        discriminator_column="party_type",
        discriminator_value="supplier",
    )


def test_discriminated_lists_only_its_own_partition(runtime) -> None:
    """Without this, a customer rule would silently evaluate against suppliers."""
    customers = build_resolver(_customer()).list_ids(runtime, 10)
    suppliers = build_resolver(_supplier()).list_ids(runtime, 10)
    assert set(customers) == {"1", "3"}
    assert set(suppliers) == {"2"}


def test_discriminated_refuses_an_id_from_another_partition(runtime) -> None:
    """A wrong verdict, not a modelling inconvenience: id 2 is a supplier."""
    assert build_resolver(_customer()).fetch(runtime, "2") is None
    assert build_resolver(_supplier()).fetch(runtime, "2") is not None


def test_discriminated_ids_round_trip(runtime) -> None:
    resolver = build_resolver(_customer())
    for instance_id in resolver.list_ids(runtime, 10):
        assert resolver.fetch(runtime, instance_id) is not None


# -- custom_sql: the escape hatch --


def _custom() -> ResolverSpec:
    return ResolverSpec(
        kind=CUSTOM_SQL,
        query="select id, order_no, total from orders where total > 0",
        id_column="id",
    )


def test_custom_sql_fetches_from_the_query(runtime) -> None:
    record = build_resolver(_custom()).fetch(runtime, "1")
    assert record is not None
    assert record["order_no"] == "SO-1"


def test_custom_sql_excludes_rows_its_query_filters_out(runtime) -> None:
    """Order 2 has total 0, so the query does not include it."""
    assert build_resolver(_custom()).fetch(runtime, "2") is None


def test_custom_sql_ids_round_trip(runtime) -> None:
    resolver = build_resolver(_custom())
    ids = resolver.list_ids(runtime, 10)
    assert ids == ["1"]
    for instance_id in ids:
        assert resolver.fetch(runtime, instance_id) is not None


def test_custom_sql_reports_query_columns(runtime) -> None:
    assert set(build_resolver(_custom()).columns(runtime)) == {"id", "order_no", "total"}


def test_custom_sql_reports_no_tables_rather_than_guessing() -> None:
    """Determining tables would need SQL parsing; reported honestly as empty."""
    assert build_resolver(_custom()).tables() == ()


# -- Registry --


def test_builtin_kinds_are_registered() -> None:
    assert set(supported_resolver_kinds()) == {
        SINGLE_TABLE,
        JOINED_TABLES,
        DISCRIMINATED,
        CUSTOM_SQL,
    }


def test_a_third_party_resolver_can_be_registered() -> None:
    from ontology_platform.instance_resolver import RESOLVER_REGISTRY, InstanceResolver

    saved = RESOLVER_REGISTRY.snapshot()
    try:

        class StubResolver(InstanceResolver):
            kind = "stub"

            def validate(self) -> None:
                return None

            def fetch(self, runtime, instance_id):
                return {"id": instance_id}

            def list_ids(self, runtime, limit=50):
                return ["1"]

            def columns(self, runtime):
                return ["id"]

        register_resolver("stub", StubResolver)
        resolver = build_resolver(ResolverSpec(kind="stub"))
        assert resolver.fetch(None, "7") == {"id": "7"}
    finally:
        RESOLVER_REGISTRY.restore(saved)


# -- End to end through the kernel --


@pytest.fixture
def modelled(tmp_path: Path, source_db: Path):
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "订单系统", "sqlite", str(source_db), domain="订单管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    return {"platform_db": platform_db, "ontology_id": ontology["ontology"]["id"]}


def _set_resolver(platform_db: Path, ontology_id: int, object_code: str, spec: ResolverSpec) -> None:
    with connect(platform_db) as conn:
        conn.execute(
            "update business_object set resolver_spec = ? where ontology_id = ? and code = ?",
            (spec.to_json(), ontology_id, object_code),
        )


def test_existing_objects_default_to_single_table(modelled) -> None:
    """Backwards compatibility: an object with no resolver_spec behaves as before."""
    ids = list_instance_ids(modelled["platform_db"], modelled["ontology_id"], "orders", 10)
    assert {str(value) for value in ids} == {"1", "2"}


def test_kernel_uses_a_joined_resolver_for_assessment(modelled) -> None:
    """A rule over child rows -- previously impossible for a single-table object."""
    _set_resolver(modelled["platform_db"], modelled["ontology_id"], "orders", _joined())
    upsert_business_rule(
        modelled["platform_db"],
        modelled["ontology_id"],
        code="order_has_lines",
        name="订单必须包含明细金额",
        rule_type="validation",
        scope_object_code="orders",
        expression="sum(order_line.amount) > 0",
        severity="blocking",
        natural_language="订单明细金额合计必须大于 0。",
        actor="test",
    )

    passing = assess_instance(modelled["platform_db"], modelled["ontology_id"], "orders", "1")
    failing = assess_instance(modelled["platform_db"], modelled["ontology_id"], "orders", "2")
    assert passing["decision"]["status"] == "approved", passing
    # Order 2's only line has amount 0.
    assert failing["decision"]["status"] == "blocked", failing


def test_kernel_lists_only_the_partition_for_a_discriminated_object(modelled) -> None:
    """Batch assessment must not hand ids the object's own fetch() rejects."""
    _set_resolver(modelled["platform_db"], modelled["ontology_id"], "party", _customer())
    ids = list_instance_ids(modelled["platform_db"], modelled["ontology_id"], "party", 10)
    assert {str(value) for value in ids} == {"1", "3"}


def test_kernel_assessment_respects_the_discriminator(modelled) -> None:
    _set_resolver(modelled["platform_db"], modelled["ontology_id"], "party", _customer())
    with pytest.raises(ValueError, match="实例不存在"):
        assess_instance(modelled["platform_db"], modelled["ontology_id"], "party", "2")


def test_kernel_uses_a_custom_sql_resolver(modelled) -> None:
    _set_resolver(modelled["platform_db"], modelled["ontology_id"], "orders", _custom())
    ids = list_instance_ids(modelled["platform_db"], modelled["ontology_id"], "orders", 10)
    assert {str(value) for value in ids} == {"1"}


def test_resolver_child_rows_are_addressable_in_rules(runtime) -> None:
    """Regression: resolver output must match the shape rules expect.

    A resolver returns child rows as a plain list, but rules address them by
    attribute (`order_line.amount`). Unwrapped, the expression raised
    "'list' object has no attribute 'amount'", and because evaluation fails closed
    that surfaced as a *blocking violation* -- a wiring detail becoming a wrong
    verdict, which is exactly the failure mode ADR-0002 exists to prevent.
    """
    from ontology_platform.semantic_kernel import (
        _wrap_resolver_children,
        evaluate_rule_expression,
    )

    record = build_resolver(_joined()).fetch(runtime, "1")
    context = _wrap_resolver_children(record)

    passed, error = evaluate_rule_expression("sum(order_line.amount) > 0", context)
    assert error is None, error
    assert passed is True


def test_wrapping_leaves_scalar_columns_untouched() -> None:
    """A column holding a JSON string must stay a string, or comparisons break."""
    from ontology_platform.semantic_kernel import _wrap_resolver_children

    wrapped = _wrap_resolver_children({"id": 1, "note": '{"a": 1}', "amount": 5.5, "missing": None})
    assert wrapped["note"] == '{"a": 1}'
    assert wrapped["amount"] == 5.5
    assert wrapped["missing"] is None


def test_wrapping_handles_a_single_related_row() -> None:
    """Some resolvers attach one parent row rather than a collection."""
    from ontology_platform.semantic_kernel import (
        _wrap_resolver_children,
        evaluate_rule_expression,
    )

    context = _wrap_resolver_children({"id": 1, "customer": {"name": "甲", "level": 3}})
    passed, error = evaluate_rule_expression("customer.level > 2", context)
    assert error is None, error
    assert passed is True


def test_empty_child_collection_still_evaluates(runtime) -> None:
    """sum() over no children must yield 0, not an evaluation error."""
    from ontology_platform.semantic_kernel import (
        _wrap_resolver_children,
        evaluate_rule_expression,
    )

    context = _wrap_resolver_children({"id": 9, "order_line": []})
    passed, error = evaluate_rule_expression("sum(order_line.amount) > 0", context)
    assert error is None, error
    assert passed is False


# -- Configuration API --


def test_configuring_a_resolver_validates_before_storing(modelled) -> None:
    """An invalid spec must fail here, not later as a failed assessment."""
    from ontology_platform.instance_resolver import configure_object_resolver

    with pytest.raises(ResolverError):
        configure_object_resolver(
            modelled["platform_db"],
            modelled["ontology_id"],
            "orders",
            ResolverSpec(kind=SINGLE_TABLE, table="orders; drop table orders"),
        )


def test_configuring_and_reading_back_a_resolver(modelled) -> None:
    from ontology_platform.instance_resolver import (
        configure_object_resolver,
        get_object_resolver,
    )

    configure_object_resolver(modelled["platform_db"], modelled["ontology_id"], "orders", _joined(), actor="tester")
    reported = get_object_resolver(modelled["platform_db"], modelled["ontology_id"], "orders")
    assert reported["kind"] == JOINED_TABLES
    assert reported["configured"] is True
    assert set(reported["resolver"]["tables"]) == {"orders", "order_line"}


def test_an_unconfigured_object_reports_single_table(modelled) -> None:
    from ontology_platform.instance_resolver import get_object_resolver

    reported = get_object_resolver(modelled["platform_db"], modelled["ontology_id"], "orders")
    assert reported["kind"] == SINGLE_TABLE
    assert reported["configured"] is False


def test_configuring_an_unknown_object_is_refused(modelled) -> None:
    from ontology_platform.instance_resolver import configure_object_resolver

    with pytest.raises(ResolverError, match="业务对象不存在"):
        configure_object_resolver(modelled["platform_db"], modelled["ontology_id"], "not_an_object", _joined())


def test_published_ontology_refuses_resolver_changes(modelled) -> None:
    """Changing resolution changes what every rule evaluates against."""
    from ontology_platform.governance import (
        list_semantic_mappings,
        publish_ontology,
        review_semantic_mapping,
    )
    from ontology_platform.instance_resolver import configure_object_resolver

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)

    with pytest.raises(ResolverError, match="已发布"):
        configure_object_resolver(platform_db, ontology_id, "orders", _joined())


def test_resolver_change_is_audited(modelled) -> None:
    from ontology_platform.instance_resolver import configure_object_resolver

    configure_object_resolver(modelled["platform_db"], modelled["ontology_id"], "orders", _joined(), actor="tester")
    with connect(modelled["platform_db"]) as conn:
        rows = conn.execute("select actor from audit_log where action = 'configure_instance_resolver'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


def test_resolver_endpoints_have_sensible_capabilities() -> None:
    """Changing resolution alters every verdict for the object, so it is a write."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("PUT", "/ontologies/1/objects/orders/resolver") == "platform:write"
    assert required_capability("GET", "/resolvers") == "platform:read"
