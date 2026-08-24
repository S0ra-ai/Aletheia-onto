"""Axioms: the fifth component of an ontology, and the release gate that uses it.

GB/T 48000.3—2026 names five components -- entity types, data properties, object
properties, axioms, rules. This platform had four. These tests pin down what makes the
fifth one worth having rather than a synonym for "rule":

- an axiom is checked against the **model**, with no instance data
- a model that violates its own axioms **cannot publish**, because every verdict it
  produces would be derived from declarations that cannot all be true
- an axiom naming something that does not exist is **refused**, not warned about: a
  vacuously satisfied axiom makes a modeller believe a control exists when it does not
- re-checking at publication catches what declaration-time checking cannot -- an axiom
  that held when written and was broken later by the model moving underneath it

Every property has a counter-example test. An axiom check that has never been shown to
fail is indistinguishable from one that always passes.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.axioms import (
    AXIOM_KINDS,
    AxiomError,
    AxiomSpec,
    check_axioms,
    declare_axiom,
    describe_axiom_kinds,
    init_axiom_schema,
    list_axioms,
    remove_axiom,
)
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.release_readiness import assess_ontology_release_readiness
from ontology_platform.type_hierarchy import declare_subtype


@pytest.fixture
def modelled(tmp_path: Path):
    """A contract/customer/equipment model with the shapes axioms are about.

    `contracts` carries two references to the same customer table, which is what makes
    an irreflexive axiom meaningful: 甲方 and 乙方 are both customers, and nothing in
    the schema stops them being the *same* customer.
    """
    source = tmp_path / "business.sqlite3"
    connection = sqlite3.connect(source)
    connection.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_status text not null
        );
        create table person_customers (
            id integer primary key,
            name text not null,
            id_number text not null
        );
        create table company_customers (
            id integer primary key,
            name text not null,
            registration_no text not null
        );
        create table equipment_families (
            id integer primary key,
            name text not null
        );
        create table equipment (
            id integer primary key,
            family_id integer not null references equipment_families(id),
            serial_no text not null,
            prepaid_amount numeric,
            final_amount numeric
        );
        insert into customers values (1, '甲公司', 'normal');
        insert into equipment_families values (1, '压缩机');
        insert into equipment values (1, 1, 'S1', 100, null);
        """
    )
    connection.commit()
    connection.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_axiom_schema(conn)
        # Idempotent: startup runs this on every boot.
        init_axiom_schema(conn)
    data_source = register_data_source(platform_db, "业务系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

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
        relations = {
            row["code"]: (row["source_code"], row["target_code"])
            for row in conn.execute(
                """
                select br.code, src.code as source_code, tgt.code as target_code
                from business_relation br
                join business_object src on src.id = br.source_object_id
                join business_object tgt on tgt.id = br.target_object_id
                where br.ontology_id = ?
                """,
                (ontology_id,),
            ).fetchall()
        }
    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "codes": codes,
        "relations": relations,
    }


def _attribute_reference(modelled, table: str, column: str) -> str:
    return f"{modelled['codes'][table]}.{column}"


# -- The kind catalogue --


def test_every_kind_states_the_consequence_of_violating_it() -> None:
    """ "Irreflexive" tells a modeller nothing about whether they need it.

    The consequence does. A catalogue that only names kinds pushes the modeller to guess,
    and a guessed axiom is either vacuous or wrong.
    """
    described = describe_axiom_kinds()
    assert {item["kind"] for item in described} == set(AXIOM_KINDS)
    for item in described:
        assert item["summary"], item
        assert len(item["consequence"]) > 20, f"{item['kind']} 未说明违反后果"


# -- Declaration refuses what it cannot check --


def test_an_axiom_naming_a_missing_relation_is_refused(modelled) -> None:
    """A vacuously satisfied axiom is worse than no axiom.

    It constrains nothing and reports nothing, so the modeller believes a control is in
    place. Refusing at declaration is the only point where the typo is still visible.
    """
    with pytest.raises(AxiomError, match="业务关系不存在"):
        declare_axiom(
            modelled["platform_db"],
            modelled["ontology_id"],
            AxiomSpec(code="ax_typo", kind="irreflexive_relation", subject="relation_that_does_not_exist"),
        )
    assert list_axioms(modelled["platform_db"], modelled["ontology_id"]) == []


def test_an_axiom_naming_a_missing_object_is_refused(modelled) -> None:
    with pytest.raises(AxiomError, match="业务对象不存在"):
        declare_axiom(
            modelled["platform_db"],
            modelled["ontology_id"],
            AxiomSpec(code="ax_missing", kind="disjoint_types", subject="ghost_a", object="ghost_b"),
        )


def test_an_unknown_kind_is_refused_rather_than_stored(modelled) -> None:
    """Stored, it would be silently skipped by the checker -- a control that never runs."""
    with pytest.raises(AxiomError, match="未知公理类型"):
        AxiomSpec(code="ax_bad", kind="equivalent_class", subject="anything")


def test_a_thing_cannot_be_declared_disjoint_from_itself(modelled) -> None:
    """Such an axiom can never hold, so it would block publication forever with a
    message nobody can act on."""
    code = modelled["codes"]["customers"]
    with pytest.raises(AxiomError, match="不能相同"):
        AxiomSpec(code="ax_self", kind="disjoint_types", subject=code, object=code)


def test_mutually_exclusive_attributes_must_share_an_object(modelled) -> None:
    """Two attributes on different objects are never in conflict: there is no single
    record on which both could be set."""
    with pytest.raises(AxiomError, match="必须属于同一对象"):
        declare_axiom(
            modelled["platform_db"],
            modelled["ontology_id"],
            AxiomSpec(
                code="ax_cross",
                kind="disjoint_attributes",
                subject=_attribute_reference(modelled, "equipment", "prepaid_amount"),
                object=_attribute_reference(modelled, "customers", "name"),
            ),
        )


def test_an_attribute_reference_must_name_its_object(modelled) -> None:
    with pytest.raises(AxiomError, match=r"对象编码\.属性编码"):
        declare_axiom(
            modelled["platform_db"],
            modelled["ontology_id"],
            AxiomSpec(code="ax_shape", kind="required_attribute", subject="serial_no"),
        )


# -- Declaration refuses an axiom the model already violates --


def test_declaring_an_axiom_the_model_violates_is_refused(modelled) -> None:
    """The person who wrote the axiom sees the contradiction.

    Storing it and reporting later would defer the failure to whoever next tries to
    publish -- who is usually not the person who can decide whether the axiom or the
    model is wrong.
    """
    reference = _attribute_reference(modelled, "equipment", "prepaid_amount")
    # `prepaid_amount` is nullable in the source schema, so it scans as optional.
    with pytest.raises(AxiomError, match="模型当前违反该公理"):
        declare_axiom(
            modelled["platform_db"],
            modelled["ontology_id"],
            AxiomSpec(code="ax_required", kind="required_attribute", subject=reference),
        )


def test_a_satisfied_axiom_is_stored_and_listed(modelled) -> None:
    reference = _attribute_reference(modelled, "equipment", "serial_no")
    stored = declare_axiom(
        modelled["platform_db"],
        modelled["ontology_id"],
        AxiomSpec(
            code="ax_serial",
            kind="required_attribute",
            subject=reference,
            note="设备序列号是实例标识的一部分",
        ),
    )
    assert stored["code"] == "ax_serial"

    listed = list_axioms(modelled["platform_db"], modelled["ontology_id"])
    assert [item["code"] for item in listed] == ["ax_serial"]
    # The summary travels with the axiom so a reviewer does not need the source.
    assert listed[0]["summary"]

    report = check_axioms(modelled["platform_db"], modelled["ontology_id"])
    assert report["satisfied"] is True
    assert report["declared"] == 1


def test_declaring_the_same_code_twice_replaces_rather_than_duplicates(modelled) -> None:
    """Two axioms with one code would both be checked, and only one could be removed."""
    reference = _attribute_reference(modelled, "equipment", "serial_no")
    spec = AxiomSpec(code="ax_serial", kind="required_attribute", subject=reference)
    declare_axiom(modelled["platform_db"], modelled["ontology_id"], spec)
    declare_axiom(modelled["platform_db"], modelled["ontology_id"], spec)
    assert len(list_axioms(modelled["platform_db"], modelled["ontology_id"])) == 1


# -- Disjoint types, checked structurally --


def test_a_type_inheriting_two_disjoint_types_is_a_violation(modelled) -> None:
    """The shape a modeller actually creates by accident.

    A type that inherits from both is a type whose instances are instances of both,
    which is exactly what the axiom forbids -- and it is establishable without data.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    person = modelled["codes"]["person_customers"]
    company = modelled["codes"]["company_customers"]

    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_disjoint", kind="disjoint_types", subject=person, object=company),
    )
    assert check_axioms(platform_db, ontology_id)["satisfied"] is True

    # Now make one a subtype of the other: every 企业客户 becomes a 个人客户.
    declare_subtype(platform_db, ontology_id, company, person, actor="tester")

    report = check_axioms(platform_db, ontology_id)
    assert report["satisfied"] is False
    assert "互斥类型" in report["violations"][0]["detail"]


def test_an_axiom_broken_after_declaration_is_caught_at_check_time(modelled) -> None:
    """The case declaration-time checking cannot see.

    This is why `check_axioms` exists separately: the axiom was satisfiable when
    written, and the *model* changed underneath it.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    person = modelled["codes"]["person_customers"]
    company = modelled["codes"]["company_customers"]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_disjoint", kind="disjoint_types", subject=person, object=company),
    )
    declare_subtype(platform_db, ontology_id, company, person, actor="tester")
    assert check_axioms(platform_db, ontology_id)["satisfied"] is False


# -- Relation axioms --


def test_a_self_referential_relation_violates_irreflexivity(modelled) -> None:
    """A relation whose two ends are the same object permits self-reference.

    Checked on the model, not on rows: the question is whether the declaration *allows*
    it, which is what a modeller can fix.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    with connect(platform_db) as conn:
        equipment_id = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, modelled["codes"]["equipment"]),
        ).fetchone()["id"]
        conn.execute(
            """
            insert into business_relation
                (ontology_id, source_object_id, target_object_id, code, name, relation_type)
            values (?, ?, ?, 'equipment_parent', '上级设备', 'references')
            """,
            (ontology_id, equipment_id, equipment_id),
        )

    with pytest.raises(AxiomError, match="模型当前违反该公理"):
        declare_axiom(
            platform_db,
            ontology_id,
            AxiomSpec(code="ax_irreflexive", kind="irreflexive_relation", subject="equipment_parent"),
        )


def test_a_relation_between_two_objects_satisfies_irreflexivity(modelled) -> None:
    relation_code = next(code for code, (source, target) in modelled["relations"].items() if source != target)
    stored = declare_axiom(
        modelled["platform_db"],
        modelled["ontology_id"],
        AxiomSpec(code="ax_ok", kind="irreflexive_relation", subject=relation_code),
    )
    assert stored["kind"] == "irreflexive_relation"


def test_a_declared_inverse_relation_violates_asymmetry(modelled) -> None:
    """If A→B and B→A are both declared, both can hold and a hierarchy walk need not
    terminate."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    relation_code, (source, target) = next(
        (code, pair) for code, pair in modelled["relations"].items() if pair[0] != pair[1]
    )
    with connect(platform_db) as conn:
        ids = {
            row["code"]: row["id"]
            for row in conn.execute(
                "select id, code from business_object where ontology_id = ?", (ontology_id,)
            ).fetchall()
        }
        conn.execute(
            """
            insert into business_relation
                (ontology_id, source_object_id, target_object_id, code, name, relation_type)
            values (?, ?, ?, 'reverse_link', '反向', 'references')
            """,
            (ontology_id, ids[target], ids[source]),
        )

    with pytest.raises(AxiomError, match="模型当前违反该公理"):
        declare_axiom(
            platform_db,
            ontology_id,
            AxiomSpec(code="ax_asym", kind="asymmetric_relation", subject=relation_code),
        )


# -- Removal --


def test_removing_a_nonexistent_axiom_reports_rather_than_silently_succeeding(modelled) -> None:
    """A silent success would let a caller believe a control was removed, or that one
    they meant to remove is gone when a typo left it in place."""
    with pytest.raises(AxiomError, match="公理不存在"):
        remove_axiom(modelled["platform_db"], modelled["ontology_id"], "ax_never_declared")


def test_removing_an_axiom_clears_the_violation(modelled) -> None:
    """Removal is the escape hatch: an axiom that turned out not to reflect the business
    must be retractable, or a wrong axiom would permanently block publication."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    person = modelled["codes"]["person_customers"]
    company = modelled["codes"]["company_customers"]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_disjoint", kind="disjoint_types", subject=person, object=company),
    )
    declare_subtype(platform_db, ontology_id, company, person, actor="tester")
    assert check_axioms(platform_db, ontology_id)["satisfied"] is False

    remove_axiom(platform_db, ontology_id, "ax_disjoint")
    assert check_axioms(platform_db, ontology_id)["satisfied"] is True


# -- The release gate --


def test_a_model_violating_its_axioms_cannot_publish(modelled) -> None:
    """The reason axioms exist at all.

    A model that contradicts itself still produced verdicts before this gate: nothing
    looked at whether the declarations could all be true at once. Every verdict from
    such a model is suspect, which is why this is a blocker rather than a warning.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    person = modelled["codes"]["person_customers"]
    company = modelled["codes"]["company_customers"]
    declare_axiom(
        platform_db,
        ontology_id,
        AxiomSpec(code="ax_disjoint", kind="disjoint_types", subject=person, object=company),
    )

    before = _gate(assess_ontology_release_readiness(platform_db, ontology_id), "axioms_satisfied")
    assert before["passed"] is True, before

    declare_subtype(platform_db, ontology_id, company, person, actor="tester")

    after_report = assess_ontology_release_readiness(platform_db, ontology_id)
    after = _gate(after_report, "axioms_satisfied")
    assert after["passed"] is False
    assert after["severity"] == "blocker", "公理违反必须阻断发布，而非仅警告"
    # The gate must name the contradiction; "axioms failed" is not actionable.
    assert "互斥类型" in after["evidence"]


def test_the_gate_passes_when_no_axioms_are_declared(modelled) -> None:
    """A gate nothing can pass gets bypassed rather than fixed.

    Axioms are opt-in: an existing deployment that declares none must not suddenly
    become unpublishable.
    """
    report = assess_ontology_release_readiness(modelled["platform_db"], modelled["ontology_id"])
    gate = _gate(report, "axioms_satisfied")
    assert gate["passed"] is True
    assert "0 条公理" in gate["evidence"]


def _gate(report: dict, code: str) -> dict:
    for gate in report["gates"]:
        if gate["code"] == code:
            return gate
    raise AssertionError(f"发布评估缺少门禁 {code}: {[item['code'] for item in report['gates']]}")


# -- Absent schema reads as "not configured", never as an error --


def test_listing_axioms_without_the_table_returns_empty(tmp_path: Path) -> None:
    """An installation that has not applied the migration must read as "none declared".

    Raising here would make every release assessment fail on an upgrade, which is the
    failure mode that gets a feature reverted.
    """
    platform_db = tmp_path / "bare.sqlite3"
    initialize_platform_db(platform_db)
    assert list_axioms(platform_db, 1) == []
    report = check_axioms(platform_db, 1)
    assert report["satisfied"] is True
    assert report["declared"] == 0
