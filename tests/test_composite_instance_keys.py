"""Composite primary keys, end to end.

The platform used to raise "当前原型不支持复合主键" in three places, which ruled out
junction tables, versioned records and partitioned history tables -- a large share
of real legacy schemas. These tests drive a genuinely composite-keyed table
through explanation, assessment and batch consistency.

They double as the conformance suite for `InstanceKey`: an implementation that
changes the token format must keep every round-trip here passing, because those
tokens are persisted in decision records and audit rows.
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
from ontology_platform.instance_key import (
    InstanceKey,
    InstanceKeyError,
    is_composite,
    parse_key_columns,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import explain_instance, generate_ontology_draft
from ontology_platform.semantic_kernel import (
    assess_decision_consistency,
    assess_instance,
    list_instance_ids,
)

# -- Key definition parsing --


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("id", ("id",)),
        ("contract_id,clause_no", ("contract_id", "clause_no")),
        ("contract_id, clause_no", ("contract_id", "clause_no")),
        ("  spaced  ", ("spaced",)),
        ("", ("id",)),
        (None, ("id",)),
    ],
)
def test_key_columns_are_parsed_from_the_stored_definition(stored, expected) -> None:
    assert parse_key_columns(stored) == expected


def test_is_composite_reflects_column_count() -> None:
    assert is_composite("a,b") is True
    assert is_composite("a") is False


# -- Token round-trips --


def test_single_column_token_is_the_bare_value() -> None:
    """Backwards compatibility: existing decision records store bare ids."""
    key = InstanceKey.from_token("id", "42")
    assert key.token == "42"
    assert key.as_mapping() == {"id": "42"}


@pytest.mark.parametrize(
    "values",
    [
        ("HT-1", "3"),
        ("x;y", "p=q"),
        ("back\\slash", "v"),
        ("", ""),
        ("中文合同编号", "第二条"),
        ("=leading", "trailing="),
        (";;;", "==="),
        ("percent%20already", "50%"),
    ],
)
def test_composite_tokens_round_trip_including_delimiters(values) -> None:
    """Business keys legitimately contain ';' and '='; encoding must survive them."""
    key = InstanceKey(columns=("contract_id", "clause_no"), values=values)
    restored = InstanceKey.from_token("contract_id,clause_no", key.token)
    assert restored.values == values
    assert restored.columns == key.columns


def test_composite_token_accepts_positional_form() -> None:
    """Convenience for hand-written requests: values in declared column order."""
    key = InstanceKey.from_token("contract_id,clause_no", "HT-1;3")
    assert key.as_mapping() == {"contract_id": "HT-1", "clause_no": "3"}


def test_named_form_is_order_independent() -> None:
    key = InstanceKey.from_token("contract_id,clause_no", "clause_no=3;contract_id=HT-1")
    assert key.values == ("HT-1", "3")


@pytest.mark.parametrize(
    "token",
    [
        "contract_id=HT-1",
        "contract_id=HT-1;clause_no=3;extra=9",
        "HT-1",
        "",
        "wrong=1;names=2",
    ],
)
def test_malformed_composite_tokens_are_rejected(token) -> None:
    with pytest.raises(InstanceKeyError):
        InstanceKey.from_token("contract_id,clause_no", token)


def test_key_column_and_value_counts_must_match() -> None:
    with pytest.raises(InstanceKeyError):
        InstanceKey(columns=("a", "b"), values=("only-one",))


def test_where_clause_binds_values_as_parameters() -> None:
    """Key values must never be interpolated into SQL text."""
    key = InstanceKey(columns=("contract_id", "clause_no"), values=("HT-1'; drop table x --", 3))
    conditions, params = key.where_clause(lambda c: f'"{c}"', placeholder="?")
    assert conditions == '"contract_id" = ? and "clause_no" = ?'
    assert params == ("HT-1'; drop table x --", 3)


# -- End to end against a composite-keyed table --


@pytest.fixture
def clause_source(tmp_path: Path):
    """A contract-clause table keyed on (contract_id, clause_no)."""
    business_db = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(business_db)
    conn.executescript(
        """
        create table contract_clause (
            contract_id text not null,
            clause_no   integer not null,
            content     text not null,
            amount      numeric,
            primary key (contract_id, clause_no)
        );
        insert into contract_clause values ('HT-1', 1, '付款条款', 1000);
        insert into contract_clause values ('HT-1', 2, '违约责任', 500);
        insert into contract_clause values ('HT-2', 1, '保密条款', 0);
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "合同条款系统", "sqlite", str(business_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    ontology_id = ontology["ontology"]["id"]

    with connect(platform_db) as platform:
        row = platform.execute(
            "select primary_key from source_table where data_source_id = ? and table_name = ?",
            (source.id, "contract_clause"),
        ).fetchone()
        object_row = platform.execute(
            "select code from business_object where ontology_id = ?", (ontology_id,)
        ).fetchone()
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "object_code": object_row["code"],
        "primary_key": row["primary_key"],
    }


def test_scan_records_the_composite_key(clause_source) -> None:
    """Everything downstream depends on the scan capturing both columns."""
    assert parse_key_columns(clause_source["primary_key"]) == ("contract_id", "clause_no")


def test_listing_instances_returns_composite_tokens(clause_source) -> None:
    ids = list_instance_ids(
        clause_source["platform_db"], clause_source["ontology_id"], clause_source["object_code"], 10
    )
    assert len(ids) == 3
    for token in ids:
        key = InstanceKey.from_token(clause_source["primary_key"], str(token))
        assert set(key.columns) == {"contract_id", "clause_no"}


def test_explaining_a_composite_key_instance_no_longer_raises(clause_source) -> None:
    """This is one of the three call sites that used to refuse outright."""
    token = InstanceKey(columns=("contract_id", "clause_no"), values=("HT-1", 2)).token
    explanation = explain_instance(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        clause_source["object_code"],
        token,
    )
    values = {attribute["value"] for attribute in explanation["attributes"]}
    assert "违约责任" in values, explanation


def test_assessing_a_composite_key_instance_applies_rules(clause_source) -> None:
    upsert_business_rule(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        code="clause_amount_positive",
        name="条款金额必须为正数",
        rule_type="validation",
        scope_object_code=clause_source["object_code"],
        expression="amount != null and amount > 0",
        severity="blocking",
        natural_language="条款金额必须大于 0。",
        actor="test",
    )

    passing = InstanceKey(columns=("contract_id", "clause_no"), values=("HT-1", 1)).token
    failing = InstanceKey(columns=("contract_id", "clause_no"), values=("HT-2", 1)).token

    approved = assess_instance(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        clause_source["object_code"],
        passing,
    )
    blocked = assess_instance(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        clause_source["object_code"],
        failing,
    )

    assert approved["decision"]["status"] == "approved", approved
    # HT-2 clause 1 has amount 0, so the blocking rule must refuse it.
    assert blocked["decision"]["status"] == "blocked", blocked


def test_decision_records_store_the_composite_token(clause_source) -> None:
    """The token is the audit trail's handle on the instance; it must persist."""
    token = InstanceKey(columns=("contract_id", "clause_no"), values=("HT-1", 2)).token
    assess_instance(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        clause_source["object_code"],
        token,
    )
    with connect(clause_source["platform_db"]) as platform:
        rows = platform.execute("select instance_id from decision_record where instance_id = ?", (token,)).fetchall()
    assert rows, "决策记录未保存复合主键实例标识"


def test_batch_consistency_works_across_composite_keys(clause_source) -> None:
    """The third former raise site: batch assessment over composite keys."""
    report = assess_decision_consistency(
        clause_source["platform_db"],
        clause_source["ontology_id"],
        clause_source["object_code"],
        limit=10,
    )
    assert report["assessed"] == 3, report
    assert report["status"] in {"consistent", "mixed"}
