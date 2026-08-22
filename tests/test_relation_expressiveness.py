"""Relation semantics: cardinality, strength and many-to-many.

Every foreign key used to produce one relation row with `relation_type =
"references"` -- a constant that restated the foreign key rather than modelling the
link. These tests pin the properties that make a relation usable:

- cardinality is inferred from declared structure, never from data
- a one-to-one child is exposed as a row, not a one-element collection, because
  `profile.status != 'x'` on a collection yields `[False]`, which is *truthy*
- a junction table collapses into a direct many-to-many, while keeping its own
  object so its attributes are not lost

Generality item #4.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft, summarize_ontology
from ontology_platform.relations import (
    AGGREGATION,
    ASSOCIATION,
    COMPOSITION,
    MANY_TO_MANY,
    MANY_TO_ONE,
    ONE_TO_MANY,
    ONE_TO_ONE,
    ForeignKeyShape,
    classify_foreign_key,
    detect_junction,
    shapes_for_table,
)


def _shape(**overrides) -> ForeignKeyShape:
    defaults = {
        "column_name": "customer_id",
        "target_table": "customers",
        "target_column": "id",
        "in_primary_key": False,
        "is_whole_primary_key": False,
        "nullable": False,
    }
    return ForeignKeyShape(**{**defaults, **overrides})


# -- Classification is structural --


def test_whole_primary_key_foreign_key_is_one_to_one_composition() -> None:
    """`profile(user_id primary key)` can hold at most one row per user, and cannot
    exist without one -- both facts follow from the key, not from the data."""
    semantics = classify_foreign_key(_shape(in_primary_key=True, is_whole_primary_key=True))
    assert semantics.cardinality == ONE_TO_ONE
    assert semantics.kind == COMPOSITION
    assert semantics.optional is False


def test_part_of_composite_key_is_identity_dependent() -> None:
    """A line item keyed on (order_id, line_no) cannot be identified without its
    order, which is what composition means."""
    semantics = classify_foreign_key(_shape(column_name="order_id", in_primary_key=True))
    assert semantics.cardinality == MANY_TO_ONE
    assert semantics.kind == COMPOSITION


def test_not_null_foreign_key_outside_the_key_is_aggregation() -> None:
    """Mandatory parent, independent identity: the child exists in its own right but
    never without a parent."""
    semantics = classify_foreign_key(_shape(nullable=False))
    assert semantics.kind == AGGREGATION
    assert semantics.optional is False


def test_nullable_foreign_key_is_an_optional_association() -> None:
    semantics = classify_foreign_key(_shape(nullable=True))
    assert semantics.kind == ASSOCIATION
    assert semantics.optional is True


def test_every_classification_states_its_basis() -> None:
    """An operator correcting a generated relation needs to know why it was
    classified that way; a classification with no stated basis cannot be reviewed."""
    for shape in (
        _shape(in_primary_key=True, is_whole_primary_key=True),
        _shape(in_primary_key=True),
        _shape(nullable=False),
        _shape(nullable=True),
    ):
        assert classify_foreign_key(shape).reason


def test_inverse_cardinality_is_the_mirror() -> None:
    assert classify_foreign_key(_shape(nullable=False)).inverse_cardinality == ONE_TO_MANY
    assert classify_foreign_key(_shape(is_whole_primary_key=True)).inverse_cardinality == ONE_TO_ONE


def test_a_column_missing_from_the_scan_gets_the_weakest_classification() -> None:
    """Overstating a relation's strength would licence a cascade, so an unknown
    column is assumed nullable."""
    shapes = shapes_for_table(
        "id",
        columns=[],
        foreign_keys=[{"column_name": "customer_id", "target_table": "customers", "target_column": "id"}],
    )
    assert shapes[0].nullable is True
    assert classify_foreign_key(shapes[0]).kind == ASSOCIATION


# -- Junction detection --


def test_two_foreign_keys_forming_the_primary_key_is_a_junction() -> None:
    junction = detect_junction(
        "contract_tag",
        "contract_id,tag_id",
        [
            _shape(column_name="contract_id", target_table="contracts", in_primary_key=True),
            _shape(column_name="tag_id", target_table="tags", in_primary_key=True),
        ],
    )
    assert junction is not None
    assert junction.left.target_table == "contracts"
    assert junction.right.target_table == "tags"


def test_a_surrogate_key_table_is_not_a_junction() -> None:
    """An order line has its own identity, which usually means the business talks
    about it. Wrongly collapsing a real object would hide it from the model
    entirely, whereas missing a junction only leaves an extra hop."""
    assert (
        detect_junction(
            "order_line",
            "id",
            [
                _shape(column_name="order_id", target_table="orders"),
                _shape(column_name="product_id", target_table="products"),
            ],
        )
        is None
    )


def test_a_self_link_table_is_left_alone() -> None:
    """Collapsing it would produce a relation whose two sides are
    indistinguishable."""
    assert (
        detect_junction(
            "prerequisite",
            "course_id,requires_course_id",
            [
                _shape(column_name="course_id", target_table="courses", in_primary_key=True),
                _shape(column_name="requires_course_id", target_table="courses", in_primary_key=True),
            ],
        )
        is None
    )


def test_a_two_column_key_that_is_not_all_foreign_keys_is_not_a_junction() -> None:
    assert (
        detect_junction(
            "contract_version",
            "contract_id,version_no",
            [_shape(column_name="contract_id", target_table="contracts", in_primary_key=True)],
        )
        is None
    )


# -- End to end through draft generation --


@pytest.fixture
def modelled(tmp_path: Path):
    """A schema exercising all four structures at once."""
    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        create table customers (id integer primary key, name text not null);
        create table tags (id integer primary key, label text not null);
        create table contracts (
            id integer primary key,
            -- NOT NULL, outside the key: mandatory parent, independent identity.
            customer_id integer not null references customers(id),
            -- Nullable: optional association.
            reviewer_id integer references customers(id),
            amount numeric not null
        );
        -- Whole primary key is the FK: one-to-one composition.
        create table contract_signature (
            contract_id integer primary key references contracts(id),
            signed_by text not null,
            status text not null
        );
        -- Part of a composite key: identity-dependent many-to-one.
        create table contract_line (
            contract_id integer not null references contracts(id),
            line_no integer not null,
            amount numeric not null,
            primary key (contract_id, line_no)
        );
        -- Junction: primary key is exactly two foreign keys.
        create table contract_tag (
            contract_id integer not null references contracts(id),
            tag_id integer not null references tags(id),
            primary key (contract_id, tag_id)
        );
        insert into customers values (1, '甲公司');
        insert into tags values (1, '重点'), (2, '高风险');
        insert into contracts values (1, 1, null, 500);
        insert into contract_signature values (1, '张三', 'signed');
        insert into contract_line values (1, 1, 300), (1, 2, 200);
        insert into contract_tag values (1, 1), (1, 2);
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
        detail = summarize_ontology(conn, ontology_id)
    codes = {row["table_name"]: row["code"] for row in _object_rows(platform_db, ontology_id)}
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "detail": detail,
        "codes": codes,
    }


def _object_rows(platform_db: Path, ontology_id: int):
    with connect(platform_db) as conn:
        return conn.execute(
            """
            select bo.code, st.table_name
            from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ?
            """,
            (ontology_id,),
        ).fetchall()


def _relation(detail, source_code: str, target_code: str, cardinality: str):
    return next(
        (
            item
            for item in detail["relations"]
            if item["sourceCode"] == source_code
            and item["targetCode"] == target_code
            and item["cardinality"] == cardinality
        ),
        None,
    )


def test_generated_relations_carry_real_cardinality(modelled) -> None:
    """Not a single `references` constant: each link states its own shape."""
    detail, codes = modelled["detail"], modelled["codes"]
    cardinalities = {item["cardinality"] for item in detail["relations"]}
    assert cardinalities != {"references"}
    assert ONE_TO_ONE in cardinalities
    assert MANY_TO_ONE in cardinalities
    assert MANY_TO_MANY in cardinalities

    signature = _relation(detail, codes["contract_signature"], codes["contracts"], ONE_TO_ONE)
    assert signature is not None and signature["relationKind"] == COMPOSITION

    line = _relation(detail, codes["contract_line"], codes["contracts"], MANY_TO_ONE)
    assert line is not None and line["relationKind"] == COMPOSITION


def test_mandatory_and_optional_parents_are_distinguished(modelled) -> None:
    """Same target table, two foreign keys, different strength -- the distinction the
    old constant erased."""
    detail, codes = modelled["detail"], modelled["codes"]
    links = [
        item
        for item in detail["relations"]
        if item["sourceCode"] == codes["contracts"] and item["targetCode"] == codes["customers"]
    ]
    # Both foreign keys produce a relation; the codes must not collide, or the
    # second insert would be lost.
    assert len({item["code"] for item in links}) == 2
    assert {item["relationKind"] for item in links} == {AGGREGATION, ASSOCIATION}
    assert {item["optional"] for item in links} == {False, True}


def test_a_junction_becomes_a_direct_many_to_many_in_both_directions(modelled) -> None:
    detail, codes = modelled["detail"], modelled["codes"]
    forward = _relation(detail, codes["contracts"], codes["tags"], MANY_TO_MANY)
    backward = _relation(detail, codes["tags"], codes["contracts"], MANY_TO_MANY)
    assert forward is not None and backward is not None
    assert forward["junctionTable"] == "contract_tag"
    assert forward["junctionSourceColumn"] == "contract_id"
    assert forward["junctionTargetColumn"] == "tag_id"
    # Mirrored, so a traversal from either side finds its own columns.
    assert backward["junctionSourceColumn"] == "tag_id"


def test_the_junction_object_survives_the_collapse(modelled) -> None:
    """Junction tables routinely carry attributes of their own (`role`,
    `valid_from`, `weight`); dropping the object would lose them."""
    assert "contract_tag" in modelled["codes"]


def test_relations_state_why_they_were_classified(modelled) -> None:
    for item in modelled["detail"]["relations"]:
        assert item["inferenceReason"], item


def test_export_carries_the_semantics(modelled) -> None:
    """A downstream consumer cannot use an exported relation that does not say its
    cardinality."""
    from ontology_platform.ontology import export_ontology_asset

    jsonld = export_ontology_asset(modelled["platform_db"], modelled["ontology_id"], "jsonld")
    assert '"cardinality"' in jsonld["content"]
    turtle = export_ontology_asset(modelled["platform_db"], modelled["ontology_id"], "turtle")
    assert "ont:cardinality" in turtle["content"]


# -- The kernel honours the semantics --


def test_a_one_to_one_child_is_a_row_not_a_collection(modelled) -> None:
    """The reason this matters is not ergonomics. On a collection,
    `contract_signature.status != 'void'` evaluates to `[False]` -- a non-empty list,
    which is truthy -- so a rule written the obvious way would silently pass.
    """
    from ontology_platform.semantic_kernel import RelatedRows, RowObject, build_runtime

    with connect(modelled["platform_db"]) as conn:
        runtime = build_runtime(conn, modelled["ontology_id"], modelled["codes"]["contracts"], "1")
    signature = runtime.related["contract_signature"]
    assert isinstance(signature, RowObject), type(signature)
    assert signature.status == "signed"
    # A genuine collection is still a collection.
    assert isinstance(runtime.related["contract_line"], RelatedRows)


def test_a_rule_can_read_a_one_to_one_child_directly(modelled) -> None:
    from ontology_platform.governance import upsert_business_rule
    from ontology_platform.semantic_kernel import assess_instance

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="signature_present",
        name="合同必须已签署",
        rule_type="validation",
        scope_object_code=modelled["codes"]["contracts"],
        expression="contract_signature.status == 'signed'",
        severity="blocking",
        natural_language="合同必须已签署。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, modelled["codes"]["contracts"], "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "signature_present")
    assert rule["passed"] is True, rule


def test_a_many_to_many_is_traversed_without_touching_the_junction(modelled) -> None:
    """Otherwise a rule about "the contract's tags" has to hop through the junction
    by hand -- and `contract_tag.tag_id` gives ids, not tags."""
    from ontology_platform.semantic_kernel import build_runtime

    with connect(modelled["platform_db"]) as conn:
        runtime = build_runtime(conn, modelled["ontology_id"], modelled["codes"]["contracts"], "1")
    tags = runtime.related[modelled["codes"]["tags"]]
    assert sorted(row["label"] for row in tags.as_list()) == ["重点", "高风险"]


def test_a_rule_can_reason_over_a_many_to_many(modelled) -> None:
    from ontology_platform.governance import upsert_business_rule
    from ontology_platform.semantic_kernel import assess_instance

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="tag_count_limit",
        name="合同标签数量上限",
        rule_type="validation",
        scope_object_code=modelled["codes"]["contracts"],
        expression=f"len({modelled['codes']['tags']}) <= 1",
        severity="blocking",
        natural_language="合同标签不得超过 1 个。",
        actor="tester",
    )
    result = assess_instance(platform_db, ontology_id, modelled["codes"]["contracts"], "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "tag_count_limit")
    # Two tags against a limit of one.
    assert rule["passed"] is False, rule


def test_existing_deployments_get_the_weakest_defaults() -> None:
    """Relation rows predate these columns. The migration default must never
    overstate a link's strength, or something previously non-cascading becomes
    cascading on upgrade."""
    from ontology_platform.database import COLUMN_MIGRATIONS

    defaults = {
        migration.column: migration.sqlite_type
        for migration in COLUMN_MIGRATIONS
        if migration.table == "business_relation"
    }
    assert "many_to_one" in defaults["cardinality"]
    assert "association" in defaults["relation_kind"]
    assert "default 1" in defaults["optional"]
