"""Derived attributes and units of measure.

Generality items #7 and #10, which turn out to be one mechanism.

The property worth pinning down for units is not convenience. Without them,

    合同金额（万元）> 客户额度（元）

compares 500万元 against 1,000,000元 as `500 > 1000000` -- false, when the truth is
that the limit is breached fivefold. That is a wrong verdict produced from correct
data, which is the failure mode ADR-0002 exists to prevent.

For derived attributes it is fail-closed: one that cannot be computed must be absent
from the context, not None, or `margin > 0.1` evaluates to False and looks
indistinguishable from a real breach.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.derived_attributes import (
    BUILTIN_UNITS,
    DerivedAttributeError,
    DerivedSpec,
    Quantity,
    Unit,
    UnitError,
    apply_units,
    compute_derived,
    convert,
    define_derived_attribute,
    derived_context,
    get_unit,
    known_units,
    list_derived_attributes,
    load_attribute_units,
    load_derived_specs,
    register_unit,
    set_attribute_unit,
)
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance, build_runtime

# -- Units --


def test_conversion_goes_through_the_canonical_unit() -> None:
    assert convert(1, "wan_yuan", "yuan") == 10_000
    assert convert(10_000, "yuan", "wan_yuan") == 1
    assert convert(1, "yi_yuan", "wan_yuan") == 10_000


def test_cross_dimension_conversion_is_refused_not_guessed() -> None:
    """Comparing a duration against a mass is a modelling error; quietly passing the
    raw number through would let the resulting verdict look valid."""
    with pytest.raises(UnitError, match="量纲"):
        convert(1, "day", "kilogram")


def test_unknown_unit_is_refused() -> None:
    with pytest.raises(UnitError, match="未知单位"):
        get_unit("furlong")


def test_every_builtin_dimension_has_a_canonical_unit() -> None:
    """Conversion routes through the canonical unit, so a dimension without one
    cannot convert at all."""
    dimensions = {unit.dimension for unit in BUILTIN_UNITS}
    for dimension in dimensions:
        canonical = [unit for unit in BUILTIN_UNITS if unit.dimension == dimension and unit.to_canonical == 1.0]
        assert len(canonical) == 1, dimension


def test_registering_a_unit_requires_explicit_replacement() -> None:
    """Silently redefining 吨 would change every stored value's meaning with no
    record of it having happened."""
    register_unit(Unit("jin", "斤", "mass", 500.0), replace=True)
    with pytest.raises(UnitError, match="已存在"):
        register_unit(Unit("jin", "市斤", "mass", 500.0))
    assert convert(2, "jin", "kilogram") == 1.0


def test_a_unit_needs_a_positive_factor() -> None:
    with pytest.raises(UnitError, match="正数"):
        register_unit(Unit("bad", "坏", "mass", 0))


def test_known_units_are_listed_for_a_caller() -> None:
    codes = {unit.code for unit in known_units()}
    assert {"yuan", "wan_yuan", "day"} <= codes


# -- Quantity comparison --


def test_comparing_different_units_converts_first() -> None:
    """The motivating failure: 500万元 vs 1,000,000元 compared as 500 > 1000000."""
    amount = Quantity(500, "wan_yuan")
    limit = Quantity(1_000_000, "yuan")
    assert amount > limit
    assert not amount <= limit


def test_equal_quantities_in_different_units_are_equal() -> None:
    assert Quantity(1, "wan_yuan") == Quantity(10_000, "yuan")
    assert Quantity(1, "wan_yuan") != Quantity(20_000, "yuan")


def test_hashing_keeps_equal_quantities_equal() -> None:
    """Hashing on the magnitude alone would make 1万元 and 1元 collide."""
    assert hash(Quantity(1, "wan_yuan")) == hash(Quantity(10_000, "yuan"))
    assert hash(Quantity(1, "wan_yuan")) != hash(Quantity(1, "yuan"))


def test_a_bare_number_is_compared_as_the_attributes_own_unit() -> None:
    """A literal in a rule has no unit to convert to, and refusing it would break
    every existing rule. `amount > 0` must keep working."""
    assert Quantity(500, "wan_yuan") > 0
    assert Quantity(500, "wan_yuan") == 500


def test_arithmetic_still_works_on_the_magnitude() -> None:
    """Quantity subclasses float so existing aggregates and serialisation keep
    working."""
    assert Quantity(500, "wan_yuan") + 1 == 501
    assert sum([Quantity(1, "yuan"), Quantity(2, "yuan")]) == 3


def test_cross_dimension_comparison_raises_rather_than_answering() -> None:
    with pytest.raises(UnitError):
        _ = Quantity(1, "day") > Quantity(1, "kilogram")


def test_applying_units_leaves_missing_values_alone() -> None:
    """A missing value has no magnitude; wrapping it as 0 of some unit would make a
    threshold rule pass."""
    context = apply_units({"amount": None, "status": "active", "total": 5}, {"amount": "yuan", "total": "yuan"})
    assert context["amount"] is None
    assert context["status"] == "active"
    assert isinstance(context["total"], Quantity)


def test_an_unknown_declared_unit_is_ignored_rather_than_fatal() -> None:
    context = apply_units({"amount": 5}, {"amount": "furlong"})
    assert context["amount"] == 5
    assert not isinstance(context["amount"], Quantity)


# -- Derived evaluation --


def test_a_derived_attribute_computes_from_the_context() -> None:
    specs = [DerivedSpec("margin", "毛利率", "(revenue - cost) / revenue").validate()]
    results = compute_derived(specs, {"revenue": 100, "cost": 60})
    assert results["margin"].value == pytest.approx(0.4)
    assert results["margin"].computed


def test_a_derived_attribute_may_build_on_another_in_any_order() -> None:
    """Declaration order in a UI is not something a business user should have to
    reason about."""
    specs = [
        DerivedSpec("margin_percent", "毛利率百分比", "margin * 100").validate(),
        DerivedSpec("margin", "毛利率", "(revenue - cost) / revenue").validate(),
    ]
    results = compute_derived(specs, {"revenue": 100, "cost": 60})
    assert results["margin_percent"].value == pytest.approx(40)


def test_a_cyclic_definition_terminates_and_reports() -> None:
    """An uncapped resolver on a cyclic definition would not terminate."""
    specs = [
        DerivedSpec("a", "A", "b + 1").validate(),
        DerivedSpec("b", "B", "a + 1").validate(),
    ]
    results = compute_derived(specs, {})
    assert not results["a"].computed
    assert results["a"].error


def test_only_computed_values_enter_the_context() -> None:
    """Injecting None would make `margin > 0.1` evaluate to False -- indistinguishable
    from a real breach."""
    specs = [
        DerivedSpec("ok", "可算", "1 + 1").validate(),
        DerivedSpec("bad", "算不出", "missing_column * 2").validate(),
    ]
    context = derived_context(compute_derived(specs, {}))
    assert context == {"ok": 2}


def test_one_bad_definition_does_not_take_out_the_others() -> None:
    specs = [
        DerivedSpec("bad", "算不出", "missing * 2").validate(),
        DerivedSpec("good", "可算", "2 * 3").validate(),
    ]
    results = compute_derived(specs, {})
    assert results["good"].value == 6


def test_a_derived_value_can_carry_a_unit() -> None:
    specs = [DerivedSpec("remaining", "剩余额度", "limit - used", unit="yuan").validate()]
    results = compute_derived(specs, {"limit": 1000, "used": 300})
    value = results["remaining"].value
    assert isinstance(value, Quantity)
    assert value.unit == "yuan"


# -- Definition validation --


def test_a_derived_expression_goes_through_the_rule_sandbox() -> None:
    """A separate validator would drift, and the looser of the two would become the
    way in."""
    with pytest.raises(DerivedAttributeError, match="不可执行"):
        DerivedSpec("bad", "坏", "__import__('os').system('ls')").validate()


@pytest.mark.parametrize("code", ["_private", "2bad", "has space", ""])
def test_a_derived_code_must_bind_in_the_sandbox(code) -> None:
    with pytest.raises(DerivedAttributeError):
        DerivedSpec(code, "名称", "1 + 1").validate()


def test_an_unknown_unit_is_refused_at_definition_time() -> None:
    with pytest.raises(UnitError):
        DerivedSpec("x", "X", "1 + 1", unit="furlong").validate()


# -- Persistence and end to end --


@pytest.fixture
def modelled(tmp_path: Path):
    """Contract amounts in 万元, a customer credit limit in 元.

    The mismatch is the point: it is what makes a naive numeric comparison wrong.
    """
    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
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
            amount numeric not null,
            cost numeric not null,
            status text not null
        );
        insert into customers values (1, '甲公司', 1000000);
        -- 500万元 against a 1,000,000元 limit: breached fivefold.
        insert into contracts values (1, 1, 500, 300, 'active');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "合同系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology = generate_ontology_draft(platform_db, data_source.id)
    ontology_id = ontology["ontology"]["id"]
    with connect(platform_db) as conn:
        codes = {
            row["table_name"]: row["code"]
            for row in conn.execute(
                """
                select bo.code, st.table_name from business_object bo
                join source_table st on st.id = bo.source_table_id
                where bo.ontology_id = ?
                """,
                (ontology_id,),
            ).fetchall()
        }
    return {"platform_db": platform_db, "ontology_id": ontology_id, "codes": codes}


def test_defining_and_listing_a_derived_attribute(modelled) -> None:
    define_derived_attribute(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        DerivedSpec("margin", "毛利率", "(amount - cost) / amount"),
        actor="tester",
    )
    items = list_derived_attributes(modelled["platform_db"], modelled["ontology_id"])
    assert [item["code"] for item in items] == ["margin"]


def test_a_derived_attribute_is_an_ordinary_attribute_to_consumers(modelled) -> None:
    """Explanations, the graph view, exports and the frontend must see it without
    changes; only the provenance differs."""
    from ontology_platform.ontology import summarize_ontology

    define_derived_attribute(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        DerivedSpec("margin", "毛利率", "(amount - cost) / amount"),
    )
    with connect(modelled["platform_db"]) as conn:
        detail = summarize_ontology(conn, modelled["ontology_id"])
    margin = next(item for item in detail["attributes"] if item["code"] == "margin")
    assert margin["derived"] is True
    assert margin["derivedExpression"] == "(amount - cost) / amount"
    # A mapped column is not marked derived.
    amount = next(item for item in detail["attributes"] if item["code"] == "amount")
    assert amount["derived"] is False


def test_overwriting_a_mapped_column_with_a_derived_value_is_refused(modelled) -> None:
    """It would silently change what every rule reading that name evaluates
    against."""
    with pytest.raises(DerivedAttributeError, match="已绑定来源列"):
        define_derived_attribute(
            modelled["platform_db"],
            modelled["ontology_id"],
            modelled["codes"]["contracts"],
            DerivedSpec("amount", "金额", "1 + 1"),
        )


def test_published_ontology_refuses_derived_changes(modelled) -> None:
    from ontology_platform.governance import list_semantic_mappings, publish_ontology, review_semantic_mapping

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)
    with pytest.raises(DerivedAttributeError, match="已发布"):
        define_derived_attribute(
            platform_db, ontology_id, modelled["codes"]["contracts"], DerivedSpec("x", "X", "1 + 1")
        )
    with pytest.raises(DerivedAttributeError, match="已发布"):
        set_attribute_unit(platform_db, ontology_id, modelled["codes"]["contracts"], "amount", "yuan")


def test_definitions_are_audited(modelled) -> None:
    define_derived_attribute(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        DerivedSpec("margin", "毛利率", "(amount - cost) / amount"),
        actor="tester",
    )
    set_attribute_unit(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        "amount",
        "wan_yuan",
        actor="tester",
    )
    with connect(modelled["platform_db"]) as conn:
        actions = {
            row["action"] for row in conn.execute("select action from audit_log where actor = 'tester'").fetchall()
        }
    assert {"define_derived_attribute", "set_attribute_unit"} <= actions


def test_a_stored_definition_that_stops_validating_is_skipped(modelled) -> None:
    """It will make its rule fail closed, which is the safe direction."""
    define_derived_attribute(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        DerivedSpec("margin", "毛利率", "(amount - cost) / amount"),
    )
    with connect(modelled["platform_db"]) as conn:
        conn.execute("update business_attribute set derived_expression = 'lambda: 1' where code = 'margin'")
    with connect(modelled["platform_db"]) as conn:
        assert load_derived_specs(conn, modelled["ontology_id"], modelled["codes"]["contracts"]) == []


def test_units_are_loaded_keyed_by_source_column(modelled) -> None:
    """Units are applied to the raw record read from the source, before attribute
    codes exist in the context."""
    set_attribute_unit(
        modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["contracts"], "amount", "wan_yuan"
    )
    with connect(modelled["platform_db"]) as conn:
        units = load_attribute_units(conn, modelled["ontology_id"], modelled["codes"]["contracts"])
    assert units == {"amount": "wan_yuan"}


def test_the_kernel_exposes_derived_values(modelled) -> None:
    define_derived_attribute(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["contracts"],
        DerivedSpec("margin", "毛利率", "(amount - cost) / amount"),
    )
    with connect(modelled["platform_db"]) as conn:
        runtime = build_runtime(conn, modelled["ontology_id"], modelled["codes"]["contracts"], "1")
    assert runtime.derived["margin"]["value"] == pytest.approx(0.4)
    # A verdict citing it must be able to state the expression, not only the number.
    assert runtime.derived["margin"]["expression"] == "(amount - cost) / amount"


def test_a_rule_can_reference_a_derived_attribute(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["codes"]["contracts"]
    define_derived_attribute(
        platform_db, ontology_id, object_code, DerivedSpec("margin", "毛利率", "(amount - cost) / amount")
    )
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="margin_floor",
        name="毛利率下限",
        rule_type="validation",
        scope_object_code=object_code,
        expression="margin >= 0.3",
        severity="blocking",
        natural_language="毛利率不得低于 30%。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, object_code, "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "margin_floor")
    assert rule["passed"] is True, rule


def test_an_uncomputable_derived_attribute_makes_its_rule_fail_closed(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["codes"]["contracts"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="undefined_derived",
        name="引用了未定义的派生属性",
        rule_type="validation",
        scope_object_code=object_code,
        expression="never_defined_margin >= 0.3",
        severity="blocking",
        natural_language="引用未定义派生属性的规则。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, object_code, "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "undefined_derived")
    assert rule["passed"] is False
    assert rule["skipped"] is True, rule


def test_units_make_a_cross_scale_comparison_correct(modelled) -> None:
    """Without units this rule passes: 500 > 1000000 is false, so a 500万元 contract
    looks like it respects a 1,000,000元 limit. That is a wrong verdict from correct
    data."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    contracts, customers = modelled["codes"]["contracts"], modelled["codes"]["customers"]
    set_attribute_unit(platform_db, ontology_id, contracts, "amount", "wan_yuan")
    set_attribute_unit(platform_db, ontology_id, customers, "credit_limit", "yuan")

    with connect(platform_db) as conn:
        runtime = build_runtime(conn, ontology_id, contracts, "1")
    amount = runtime.context["amount"]
    assert isinstance(amount, Quantity)
    # 500万元 = 5,000,000元, against a 1,000,000元 limit.
    assert amount > Quantity(1_000_000, "yuan")


def test_the_unit_declaration_can_be_cleared(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    contracts = modelled["codes"]["contracts"]
    set_attribute_unit(platform_db, ontology_id, contracts, "amount", "wan_yuan")
    set_attribute_unit(platform_db, ontology_id, contracts, "amount", "")
    with connect(platform_db) as conn:
        assert load_attribute_units(conn, ontology_id, contracts) == {}


def test_export_carries_units_and_expressions(modelled) -> None:
    """A consumer cannot interpret a number without its unit, nor reproduce a derived
    value without its expression."""
    from ontology_platform.ontology import export_ontology_asset

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    define_derived_attribute(
        platform_db, ontology_id, modelled["codes"]["contracts"], DerivedSpec("margin", "毛利率", "amount - cost")
    )
    set_attribute_unit(platform_db, ontology_id, modelled["codes"]["contracts"], "amount", "wan_yuan")
    jsonld = export_ontology_asset(platform_db, ontology_id, "jsonld")
    assert "wan_yuan" in jsonld["content"]
    assert "derivedExpression" in jsonld["content"]
    turtle = export_ontology_asset(platform_db, ontology_id, "turtle")
    assert "ont:unit" in turtle["content"]


def test_endpoints_have_sensible_capabilities() -> None:
    """A unit change silently rescales every threshold compared against that
    attribute, so it is a modelling write, not a read."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("PUT", "/ontologies/1/objects/contract/derived-attributes") == "platform:write"
    assert required_capability("PUT", "/ontologies/1/objects/contract/attributes/amount/unit") == "platform:write"
    assert required_capability("GET", "/units") == "platform:read"


def test_existing_attributes_keep_plain_numeric_comparison() -> None:
    """Empty means "a plain mapped column with no declared unit" -- the prior
    behaviour, so an upgrade changes no verdict."""
    from ontology_platform.database import COLUMN_MIGRATIONS

    defaults = {
        migration.column: migration.sqlite_type
        for migration in COLUMN_MIGRATIONS
        if migration.table == "business_attribute"
    }
    assert defaults["derived_expression"] == "text not null default ''"
    assert defaults["unit"] == "text not null default ''"
