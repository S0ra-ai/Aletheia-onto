"""Value domain mapping: legacy codes to semantic states.

Generality item #3. Legacy systems encode meaning as short codes (status='A'),
which forces business rules to be written against codes nobody can review without
the code table, and makes answers quote raw codes back at the user.

The important property under test is that mapping a value does not change the
meaning of rules already written against the raw code: both forms must evaluate
identically, or introducing a mapping would silently alter existing verdicts.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import initialize_platform_db
from ontology_platform.governance import publish_ontology, review_semantic_mapping, upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.semantic_kernel import MappedValue, assess_instance
from ontology_platform.value_mapping import (
    load_value_mappings,
    register_value_mapping,
    state_for,
    suggest_value_mappings_from_enums,
)


@pytest.fixture
def order_source(tmp_path: Path):
    """An orders table whose status column holds single-letter codes."""
    business_db = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(business_db)
    conn.executescript(
        """
        create table sales_order (
            id integer primary key,
            order_no text not null,
            status text not null,
            amount numeric not null
        );
        insert into sales_order values (1, 'SO-1', 'A', 1200);
        insert into sales_order values (2, 'SO-2', 'C', 800);
        insert into sales_order values (3, 'SO-3', 'A', 300);
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "订单系统", "sqlite", str(business_db), domain="订单管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    return {
        "platform_db": platform_db,
        "source_id": source.id,
        "ontology_id": ontology["ontology"]["id"],
    }


# -- MappedValue semantics --


def test_mapped_value_equals_both_the_code_and_the_state() -> None:
    """This dual equality is what keeps existing rules working."""
    value = MappedValue("A", "生效中")
    assert value == "A"
    assert value == "生效中"
    assert value != "C"
    assert value != "已取消"


def test_mapped_value_behaves_as_a_string() -> None:
    value = MappedValue("A", "生效中")
    assert str(value) == "A"
    assert value.lower() == "a"
    assert value in {"A"}


def test_mapped_value_of_none_is_empty_not_crashing() -> None:
    assert str(MappedValue(None, "未知")) == ""


# -- Registration and lookup --


def test_register_and_load_a_value_mapping(order_source) -> None:
    register_value_mapping(
        order_source["platform_db"],
        order_source["ontology_id"],
        "sales_order",
        "status",
        "A",
        "生效中",
    )
    mappings = load_value_mappings(order_source["platform_db"], order_source["ontology_id"])
    assert state_for(mappings, "sales_order", "status", "A") == "生效中"
    assert state_for(mappings, "sales_order", "status", "Z") is None
    assert state_for(mappings, "sales_order", "status", None) is None


def test_registering_the_same_pair_twice_updates_rather_than_duplicates(order_source) -> None:
    for state in ("生效", "生效中"):
        register_value_mapping(
            order_source["platform_db"],
            order_source["ontology_id"],
            "sales_order",
            "status",
            "A",
            state,
        )
    mappings = load_value_mappings(order_source["platform_db"], order_source["ontology_id"])
    assert mappings["sales_order.status"] == {"A": "生效中"}


def test_pending_mappings_do_not_apply_by_default(order_source) -> None:
    """An unreviewed guess must not change what a compliance rule evaluates to."""
    register_value_mapping(
        order_source["platform_db"],
        order_source["ontology_id"],
        "sales_order",
        "status",
        "A",
        "生效中",
        status="pending",
    )
    assert load_value_mappings(order_source["platform_db"], order_source["ontology_id"]) == {}
    with_pending = load_value_mappings(order_source["platform_db"], order_source["ontology_id"], include_pending=True)
    assert with_pending["sales_order.status"] == {"A": "生效中"}


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_values_and_states_are_rejected(order_source, bad) -> None:
    with pytest.raises(ValueError):
        register_value_mapping(
            order_source["platform_db"],
            order_source["ontology_id"],
            "sales_order",
            "status",
            bad,
            "生效中",
        )
    with pytest.raises(ValueError):
        register_value_mapping(
            order_source["platform_db"],
            order_source["ontology_id"],
            "sales_order",
            "status",
            "A",
            bad,
        )


def test_published_ontology_rejects_new_value_mappings(order_source) -> None:
    """Value mappings are part of the ontology, so immutability applies to them."""
    platform_db, ontology_id = order_source["platform_db"], order_source["ontology_id"]
    from ontology_platform.governance import list_semantic_mappings

    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)

    with pytest.raises(ValueError, match="已发布"):
        register_value_mapping(platform_db, ontology_id, "sales_order", "status", "A", "生效中")


# -- Rule evaluation --


def _add_rule(source, expression: str, code: str) -> None:
    upsert_business_rule(
        source["platform_db"],
        source["ontology_id"],
        code=code,
        name=f"规则 {code}",
        rule_type="validation",
        scope_object_code="sales_order",
        expression=expression,
        severity="blocking",
        natural_language="订单状态必须是生效中。",
        actor="test",
    )


def test_a_rule_can_be_written_against_the_semantic_state(order_source) -> None:
    """The point of the feature: rules read in business language."""
    register_value_mapping(
        order_source["platform_db"],
        order_source["ontology_id"],
        "sales_order",
        "status",
        "A",
        "生效中",
    )
    _add_rule(order_source, "status == '生效中'", "status_must_be_active")

    approved = assess_instance(order_source["platform_db"], order_source["ontology_id"], "sales_order", "1")
    assert approved["decision"]["status"] == "approved", approved


def test_rules_written_against_the_raw_code_keep_working(order_source) -> None:
    """Introducing a mapping must not silently change existing verdicts."""
    register_value_mapping(
        order_source["platform_db"],
        order_source["ontology_id"],
        "sales_order",
        "status",
        "A",
        "生效中",
    )
    _add_rule(order_source, "status == 'A'", "status_raw_code")

    approved = assess_instance(order_source["platform_db"], order_source["ontology_id"], "sales_order", "1")
    assert approved["decision"]["status"] == "approved", approved


def test_an_unmapped_value_still_fails_a_state_rule(order_source) -> None:
    register_value_mapping(
        order_source["platform_db"],
        order_source["ontology_id"],
        "sales_order",
        "status",
        "A",
        "生效中",
    )
    _add_rule(order_source, "status == '生效中'", "status_must_be_active")

    # Order 2 has status 'C', which is not mapped to 生效中.
    blocked = assess_instance(order_source["platform_db"], order_source["ontology_id"], "sales_order", "2")
    assert blocked["decision"]["status"] == "blocked", blocked


# -- Candidate generation --


def test_enum_columns_produce_pending_candidates(order_source) -> None:
    """The platform cannot know 'A' means 生效中, but it can enumerate the values."""
    result = suggest_value_mappings_from_enums(
        order_source["platform_db"], order_source["ontology_id"], order_source["source_id"]
    )
    assert result["count"] > 0, result
    assert all(candidate["status"] == "pending" for candidate in result["candidates"])
    # Nothing takes effect until reviewed.
    assert load_value_mappings(order_source["platform_db"], order_source["ontology_id"]) == {}
