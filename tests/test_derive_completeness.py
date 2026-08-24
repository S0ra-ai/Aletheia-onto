"""`derive` must carry forward everything that decides a verdict.

Deriving a new ontology version copies objects, attributes, relations, mappings and rules.
Two things it did not copy were recorded in README as limitations, and both are worse than
"missing metadata" -- they change what the new version *decides*:

- **workflow definitions.** A derived version's objects had no state machine, so an instance
  entering it had nowhere to go. The symptom was "this object has no workflow", which reads
  as a modelling omission rather than as something `derive` dropped.
- **five rule columns.** `priority` decides evaluation order, `effective_start`/`_end` decide
  whether a rule applies at all, and `depends_on` is read by the engine. So a derived version
  evaluated the same rules differently from the version it came from -- and "the new version
  gives a different verdict" is the one thing `derive` must not do silently.

What is deliberately *not* copied is instance state. A workflow definition is part of the
model; an instance's current state is data about a specific contract. Copying it would assert
that a contract sits at two points in two state machines at once, and reconciling that later
needs to know which the business considers authoritative -- a question the platform cannot
answer for them.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.bootstrap import prepare_database
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import (
    derive_ontology_version,
    publish_ontology,
    upsert_business_rule,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.workflow_permission import (
    add_workflow_transition,
    create_workflow,
    enter_workflow,
)


@pytest.fixture
def published(tmp_path: Path):
    source = tmp_path / "business.sqlite3"
    sqlite3.connect(source).executescript(
        """
        create table contracts (
            id integer primary key,
            amount numeric not null,
            status text not null
        );
        insert into contracts values (1, 100, 'draft');
        """
    )

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        prepare_database(conn)

    data_source = register_data_source(platform_db, "业务系统", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    with connect(platform_db) as conn:
        object_code = conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchone()[
            "code"
        ]

    workflow = create_workflow(platform_db, ontology_id, object_code, "合同审批")
    states = [state["code"] for state in workflow["states"]]
    # A guarded, review-requiring transition: the parts of a workflow that make a transition
    # refusable, and therefore the parts whose loss changes behaviour rather than appearance.
    add_workflow_transition(
        platform_db,
        workflow["id"],
        states[0],
        states[-1],
        "fast_approve",
        "加急批准",
        guard_expression="amount > 0",
        requires_review=True,
        review_role="approver",
    )

    with connect(platform_db) as conn:
        conn.execute(
            "update semantic_mapping set status = 'confirmed' where ontology_id = ?",
            (ontology_id,),
        )
        # Rule columns that decide evaluation, set to non-default values so a dropped column
        # is observable. All defaults would make "copied" and "re-defaulted" identical.
        conn.execute(
            """
            update business_rule set priority = 7, category = '合规', depends_on = '["other_rule"]',
                   effective_start = '2026-01-01', effective_end = '2026-12-31'
             where ontology_id = ?
            """,
            (ontology_id,),
        )
    publish_ontology(platform_db, ontology_id, "tester")

    return {
        "platform_db": platform_db,
        "ontology_id": ontology_id,
        "object_code": object_code,
        "workflow_id": workflow["id"],
        "states": states,
    }


def _derive(published) -> int:
    derived = derive_ontology_version(published["platform_db"], published["ontology_id"], "0.2.0", "架构师")
    return int(derived.get("id") or derived["ontology"]["id"])


# -- Workflow definitions --


def test_the_workflow_definition_is_carried_forward(published) -> None:
    """Without it, every object in the derived version has nowhere for an instance to go."""
    derived_id = _derive(published)
    with connect(published["platform_db"]) as conn:
        definition = conn.execute(
            "select id, object_code, initial_state, status from workflow_definition where ontology_id = ?",
            (derived_id,),
        ).fetchone()
    assert definition is not None, "派生版本缺少工作流定义"
    assert definition["object_code"] == published["object_code"]


def test_every_state_is_carried_forward(published) -> None:
    derived_id = _derive(published)
    with connect(published["platform_db"]) as conn:
        source_states = {
            row["code"]
            for row in conn.execute(
                "select code from workflow_state where workflow_id = ?", (published["workflow_id"],)
            ).fetchall()
        }
        derived_workflow = conn.execute(
            "select id from workflow_definition where ontology_id = ?", (derived_id,)
        ).fetchone()
        derived_states = {
            row["code"]
            for row in conn.execute(
                "select code from workflow_state where workflow_id = ?", (derived_workflow["id"],)
            ).fetchall()
        }
    assert derived_states == source_states


def test_a_transition_keeps_its_guard_and_review_requirement(published) -> None:
    """The guard is what makes a transition refusable.

    Dropping it would turn every gated transition into an open one -- silently, since the
    transition still exists and still works. It would simply stop refusing anything.
    """
    derived_id = _derive(published)
    with connect(published["platform_db"]) as conn:
        derived_workflow = conn.execute(
            "select id from workflow_definition where ontology_id = ?", (derived_id,)
        ).fetchone()
        transition = conn.execute(
            "select guard_expression, requires_review, review_role from workflow_transition"
            " where workflow_id = ? and action_code = 'fast_approve'",
            (derived_workflow["id"],),
        ).fetchone()

    assert transition is not None, "带 guard 的流转未被复制"
    assert transition["guard_expression"] == "amount > 0", "guard 丢失会让受限流转变成开放流转"
    assert transition["requires_review"], "审核要求丢失"
    assert transition["review_role"] == "approver"


def test_instance_state_is_not_carried_forward(published) -> None:
    """Deliberately not copied.

    A workflow definition is part of the model; an instance's state is data about a specific
    contract. Copying it would assert the contract sits at two points in two state machines at
    once, and reconciling that later needs to know which one the business considers
    authoritative -- which the platform cannot decide for them.
    """
    enter_workflow(published["platform_db"], published["workflow_id"], published["object_code"], "1")
    derived_id = _derive(published)

    with connect(published["platform_db"]) as conn:
        derived_workflow = conn.execute(
            "select id from workflow_definition where ontology_id = ?", (derived_id,)
        ).fetchone()
        instances = conn.execute(
            "select count(*) as total from instance_workflow where workflow_id = ?",
            (derived_workflow["id"],),
        ).fetchone()["total"]
    assert instances == 0, "实例状态不应随定义一起复制"


def test_deriving_without_any_workflow_still_succeeds(tmp_path: Path) -> None:
    """A deployment that never configured a workflow must still be able to derive.

    Zero workflows rather than an error: an absent feature is not a failure.
    """
    source = tmp_path / "b.sqlite3"
    sqlite3.connect(source).executescript("create table t (id integer primary key, name text not null);")
    platform_db = tmp_path / "p.sqlite3"
    initialize_platform_db(platform_db)
    data_source = register_data_source(platform_db, "s", "sqlite", str(source), domain="合同管理")
    scan_data_source(platform_db, data_source.id)
    ontology_id = generate_ontology_draft(platform_db, data_source.id)["ontology"]["id"]

    with connect(platform_db) as conn:
        conn.execute("update semantic_mapping set status = 'confirmed' where ontology_id = ?", (ontology_id,))
        object_code = conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchone()[
            "code"
        ]
    # The release gate requires at least one published rule, and that gate is correct: an
    # ontology that decides nothing is not a semantic kernel. So the fixture satisfies it
    # rather than working around it.
    upsert_business_rule(
        platform_db,
        ontology_id,
        "name_required",
        "名称不能为空",
        "validation",
        object_code,
        "name != null",
        "blocking",
        "名称不能为空。",
        "tester",
    )
    publish_ontology(platform_db, ontology_id, "tester")

    derived = derive_ontology_version(platform_db, ontology_id, "0.2.0", "tester")
    assert derived.get("id") or derived["ontology"]["id"]


# -- Rule columns that decide evaluation --


def test_rule_columns_that_change_evaluation_are_carried_forward(published) -> None:
    """These five were dropped, and losing them changes verdicts rather than only metadata.

    `priority` decides evaluation order, the effective dates decide whether a rule applies at
    all, and `depends_on` is read by the engine. A derived version was therefore evaluating
    the same rules differently from the one it came from.
    """
    derived_id = _derive(published)
    with connect(published["platform_db"]) as conn:
        rule = conn.execute(
            "select priority, category, effective_start, effective_end, depends_on"
            " from business_rule where ontology_id = ? limit 1",
            (derived_id,),
        ).fetchone()

    assert rule is not None, "派生版本缺少规则"
    assert int(rule["priority"]) == 7, "priority 丢失会改变规则求值顺序"
    assert rule["category"] == "合规"
    assert str(rule["effective_start"]) == "2026-01-01", "生效期丢失会让规则在不该生效时生效"
    assert str(rule["effective_end"]) == "2026-12-31"
    assert rule["depends_on"] == '["other_rule"]', "depends_on 丢失会改变依赖求值"


def test_the_audit_entry_reports_what_was_copied(published) -> None:
    """ "How much did this derivation carry over" must be answerable after the fact, without
    diffing two ontologies by hand."""
    import json

    derived_id = _derive(published)
    with connect(published["platform_db"]) as conn:
        row = conn.execute(
            "select detail from audit_log where action = 'derive_ontology_version' order by id desc"
        ).fetchone()
    detail = json.loads(row["detail"])
    assert detail["newOntologyId"] == derived_id
    assert detail["workflows"] == 1, "审计未记录复制的工作流数量"
    assert detail["rules"] >= 1
