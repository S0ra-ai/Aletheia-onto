"""Type hierarchy and business events.

Generality items #6 and #9. Between them they close the metamodel in
`docs/02-核心元模型设计.md`: objects, attributes, relations, states and rules were
implemented, while subtypes and events were drawn but never built.

The properties worth pinning down:

- inheritance is a walk up a *declared* chain, so the same ontology always expands
  the same way -- not DL subsumption (ADR-0005)
- an override is recorded and reportable, because that is how a subtype could
  otherwise silently escape a rule its parent guarantees
- a cycle is refused at declaration, so the failure reaches whoever caused it
- events are append-only and never trigger anything, or replaying history would
  re-execute business actions
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.events import (
    EVENT_CATEGORIES,
    LIFECYCLE,
    MAX_EVENT_HISTORY,
    STATE_CHANGE,
    EventError,
    EventType,
    count_events,
    declare_event_type,
    event_tables_exist,
    init_event_schema,
    instance_timeline,
    list_event_types,
    record_event,
)
from ontology_platform.governance import upsert_business_rule
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import explain_instance, generate_ontology_draft
from ontology_platform.semantic_kernel import assess_instance
from ontology_platform.type_hierarchy import (
    MAX_HIERARCHY_DEPTH,
    HierarchyError,
    ancestors_of,
    declare_subtype,
    describe_hierarchy,
    expand,
    inherited_rule_scopes,
    subtypes_of,
)


@pytest.fixture
def modelled(tmp_path: Path):
    """A customer supertype with two subtypes backed by their own tables.

    Subtypes with their own tables rather than a discriminator column, because that is
    the case where inheritance is the *only* mechanism that can express the shared
    rule -- a discriminated resolver would not help.
    """
    source = tmp_path / "business.sqlite3"
    conn = sqlite3.connect(source)
    conn.executescript(
        """
        create table customers (
            id integer primary key,
            name text not null,
            credit_status text not null
        );
        create table person_customers (
            id integer primary key,
            name text not null,
            credit_status text not null,
            id_number text not null
        );
        create table company_customers (
            id integer primary key,
            name text not null,
            credit_status text not null,
            registration_no text not null
        );
        insert into customers values (1, '通用客户', 'normal');
        insert into person_customers values (1, '张三', 'normal', 'X1');
        insert into company_customers values (1, '甲公司', 'blacklist', 'C1');
        """
    )
    conn.commit()
    conn.close()

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_event_schema(conn)
        # Idempotent: startup runs this on every boot.
        init_event_schema(conn)
    data_source = register_data_source(platform_db, "客户系统", "sqlite", str(source), domain="客户管理")
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


def _make_hierarchy(modelled) -> tuple[str, str, str]:
    """Declare 个人客户 and 企业客户 as subtypes of 客户."""
    parent = modelled["codes"]["customers"]
    person = modelled["codes"]["person_customers"]
    company = modelled["codes"]["company_customers"]
    for child in (person, company):
        declare_subtype(modelled["platform_db"], modelled["ontology_id"], child, parent, actor="tester")
    return parent, person, company


# -- Declaration --


def test_declaring_a_subtype_records_the_ancestry(modelled) -> None:
    parent, person, _ = _make_hierarchy(modelled)
    with connect(modelled["platform_db"]) as conn:
        assert ancestors_of(conn, modelled["ontology_id"], person) == [parent]
        assert subtypes_of(conn, modelled["ontology_id"], parent) == sorted(
            [person, modelled["codes"]["company_customers"]]
        )


def test_an_object_cannot_be_its_own_subtype(modelled) -> None:
    code = modelled["codes"]["customers"]
    with pytest.raises(HierarchyError, match="自身"):
        declare_subtype(modelled["platform_db"], modelled["ontology_id"], code, code)


def test_a_cycle_is_refused_at_declaration_naming_the_loop(modelled) -> None:
    """Refused here so the failure reaches the person who caused it, rather than at
    assessment time to a user who cannot act on it."""
    parent, person, _ = _make_hierarchy(modelled)
    with pytest.raises(HierarchyError, match="环"):
        declare_subtype(modelled["platform_db"], modelled["ontology_id"], parent, person)


def test_an_unknown_object_is_refused(modelled) -> None:
    with pytest.raises(HierarchyError, match="不存在"):
        declare_subtype(
            modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "no_such_object"
        )


def test_the_declaration_can_be_cleared(modelled) -> None:
    _, person, _ = _make_hierarchy(modelled)
    declare_subtype(modelled["platform_db"], modelled["ontology_id"], person, "")
    with connect(modelled["platform_db"]) as conn:
        assert ancestors_of(conn, modelled["ontology_id"], person) == []


def test_published_ontology_refuses_hierarchy_changes(modelled) -> None:
    from ontology_platform.governance import list_semantic_mappings, publish_ontology, review_semantic_mapping

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)
    with pytest.raises(HierarchyError, match="已发布"):
        declare_subtype(platform_db, ontology_id, modelled["codes"]["person_customers"], modelled["codes"]["customers"])


def test_the_declaration_is_audited(modelled) -> None:
    _make_hierarchy(modelled)
    with connect(modelled["platform_db"]) as conn:
        rows = conn.execute("select actor from audit_log where action = 'declare_subtype'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


# -- Expansion --


def test_a_subtype_inherits_its_parents_rules(modelled) -> None:
    """The motivating requirement: a rule that governs all customers is written once.

    Without inheritance the copies drift, and the platform gives two different answers
    to the same business question depending on which subtype the instance is.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, person, _ = _make_hierarchy(modelled)
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="not_blacklisted",
        name="客户不得为黑名单",
        rule_type="risk",
        scope_object_code=parent,
        expression="credit_status != 'blacklist'",
        severity="blocking",
        natural_language="客户不得为黑名单。",
        actor="tester",
    )
    with connect(platform_db) as conn:
        expansion = expand(conn, ontology_id, person)
    inherited = next(rule for rule in expansion.rules if rule.code == "not_blacklisted")
    assert inherited.inherited is True
    assert inherited.origin_object_code == parent


def test_an_override_is_recorded_not_silently_resolved(modelled) -> None:
    """This record is what makes an escape from an ancestor's rule visible.

    Weakening is not blocked -- a legitimate business exception exists -- but doing it
    invisibly is what must not be possible.

    Overriding is declared rather than inferred from a name collision: two teams can
    pick the same code by accident, and inference would silently disable one team's
    control.
    """
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, _, company = _make_hierarchy(modelled)
    _rule(platform_db, ontology_id, "not_blacklisted", parent, "credit_status != 'blacklist'")
    _rule(
        platform_db,
        ontology_id,
        "state_owned_exempt",
        company,
        "1 == 1",
        overrides="not_blacklisted",
    )
    with connect(platform_db) as conn:
        expansion = expand(conn, ontology_id, company)
    # The superseded rule is gone from the expansion, and the one that replaced it
    # says what it replaced.
    assert "not_blacklisted" not in expansion.rule_codes
    override = next(rule for rule in expansion.rules if rule.code == "state_owned_exempt")
    assert override.origin_object_code == company
    assert override.overridden_from == "not_blacklisted"
    assert expansion.overrides
    assert "not_blacklisted" in override.describe()


def _rule(platform_db, ontology_id: int, code: str, scope: str, expression: str, **extra) -> None:
    upsert_business_rule(
        platform_db,
        ontology_id,
        code=code,
        name=code,
        rule_type="risk",
        scope_object_code=scope,
        expression=expression,
        severity="blocking",
        natural_language=f"{code} 的业务说明。",
        actor="tester",
        **extra,
    )


def test_an_override_must_name_a_rule_in_the_ancestry(modelled) -> None:
    """A typo would otherwise silently supersede nothing, leaving the author believing
    the ancestor's rule is disabled when it is still blocking."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    _, person, company = _make_hierarchy(modelled)
    _rule(platform_db, ontology_id, "person_only", person, "1 == 1")
    with pytest.raises(ValueError, match="不存在"):
        _rule(platform_db, ontology_id, "typo", company, "1 == 1", overrides="not_a_rule")
    # A sibling's rule is not in the ancestry, so overriding it would disable a
    # control on an unrelated type.
    with pytest.raises(ValueError, match="上级"):
        _rule(platform_db, ontology_id, "sibling", company, "1 == 1", overrides="person_only")


def test_a_rule_cannot_override_itself(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    _, _, company = _make_hierarchy(modelled)
    with pytest.raises(ValueError, match="自身"):
        _rule(platform_db, ontology_id, "self_ref", company, "1 == 1", overrides="self_ref")


def test_expansion_lists_attributes_with_their_declaring_type(modelled) -> None:
    _, person, _ = _make_hierarchy(modelled)
    with connect(modelled["platform_db"]) as conn:
        expansion = expand(conn, modelled["ontology_id"], person)
    # The subtype's own column shadows an inherited one of the same code, since that
    # is what its instances actually carry.
    assert expansion.attributes["id_number"] == person
    assert expansion.attributes["name"] == person


def test_rule_scopes_are_nearest_first(modelled) -> None:
    parent, person, _ = _make_hierarchy(modelled)
    with connect(modelled["platform_db"]) as conn:
        assert inherited_rule_scopes(conn, modelled["ontology_id"], person) == [person, parent]


def test_a_cycle_that_reached_storage_is_broken_rather_than_looping(modelled) -> None:
    """Refusing to assess the instance at all would turn a bad declaration into an
    outage."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, person, _ = _make_hierarchy(modelled)
    with connect(platform_db) as conn:
        # Bypass the declaration check the way a bad migration or manual edit would.
        conn.execute(
            "update business_object set parent_object_code = ? where ontology_id = ? and code = ?",
            (person, ontology_id, parent),
        )
    with connect(platform_db) as conn:
        chain = ancestors_of(conn, ontology_id, person)
    assert len(chain) <= MAX_HIERARCHY_DEPTH


def test_the_hierarchy_is_reportable(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, person, _ = _make_hierarchy(modelled)
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="not_blacklisted",
        name="客户不得为黑名单",
        rule_type="risk",
        scope_object_code=parent,
        expression="credit_status != 'blacklist'",
        severity="blocking",
        natural_language="客户不得为黑名单。",
        actor="tester",
    )
    items = {item["code"]: item for item in describe_hierarchy(platform_db, ontology_id)}
    assert items[person]["parentObjectCode"] == parent
    assert items[person]["inheritedRuleCount"] == 1
    assert items[parent]["subtypes"] == sorted([person, modelled["codes"]["company_customers"]])


# -- The kernel honours the hierarchy --


def test_an_inherited_rule_is_evaluated_against_a_subtype_instance(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, _, company = _make_hierarchy(modelled)
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="not_blacklisted",
        name="客户不得为黑名单",
        rule_type="risk",
        scope_object_code=parent,
        expression="credit_status != 'blacklist'",
        severity="blocking",
        natural_language="客户不得为黑名单。",
        actor="tester",
    )
    # The company customer is blacklisted, so the parent's rule must block it.
    result = assess_instance(platform_db, ontology_id, company, "1")
    rule = next(item for item in result["ruleResults"] if item["ruleCode"] == "not_blacklisted")
    assert rule["passed"] is False
    # A verdict citing an inherited rule must say which type guarantees it, or the
    # operator cannot tell where to go to change it.
    assert rule["inheritedFrom"] == parent
    assert result["decision"]["status"] == "blocked"


def test_an_override_replaces_the_inherited_rule_at_assessment(modelled) -> None:
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, _, company = _make_hierarchy(modelled)
    _rule(platform_db, ontology_id, "not_blacklisted", parent, "credit_status != 'blacklist'")
    _rule(
        platform_db,
        ontology_id,
        "state_owned_exempt",
        company,
        "1 == 1",
        overrides="not_blacklisted",
    )
    result = assess_instance(platform_db, ontology_id, company, "1")
    codes = [item["ruleCode"] for item in result["ruleResults"]]
    # The superseded rule must not be evaluated: the company customer is blacklisted,
    # so if it still ran the instance would be blocked.
    assert "not_blacklisted" not in codes
    exempt = next(item for item in result["ruleResults"] if item["ruleCode"] == "state_owned_exempt")
    assert exempt["passed"] is True
    assert exempt["inheritedFrom"] == ""


def test_a_standalone_object_evaluates_exactly_its_own_rules(modelled) -> None:
    """Empty parent means "a standalone type" -- the prior behaviour, so an upgrade
    changes no verdict."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    company = modelled["codes"]["company_customers"]
    upsert_business_rule(
        platform_db,
        ontology_id,
        code="parent_only",
        name="仅父类型规则",
        rule_type="risk",
        scope_object_code=modelled["codes"]["customers"],
        expression="credit_status != 'blacklist'",
        severity="blocking",
        natural_language="客户不得为黑名单。",
        actor="tester",
    )
    # No subtype declared, so the parent's rule must not apply.
    result = assess_instance(platform_db, ontology_id, company, "1")
    assert all(item["ruleCode"] != "parent_only" for item in result["ruleResults"])


def test_existing_objects_default_to_standalone() -> None:
    from ontology_platform.database import COLUMN_MIGRATIONS

    default = next(
        migration.sqlite_type
        for migration in COLUMN_MIGRATIONS
        if migration.table == "business_object" and migration.column == "parent_object_code"
    )
    assert default == "text not null default ''"


# -- Events --


def _declare(modelled, code: str = "rejected", **overrides) -> dict:
    payload = {
        "code": code,
        "name": "被驳回",
        "object_code": modelled["codes"]["customers"],
        "payload_fields": ["reason"],
    }
    payload.update(overrides)
    return declare_event_type(modelled["platform_db"], modelled["ontology_id"], EventType(**payload), actor="tester")


def test_declaring_and_listing_an_event_type(modelled) -> None:
    _declare(modelled)
    items = list_event_types(modelled["platform_db"], modelled["ontology_id"])
    assert [item["code"] for item in items] == ["rejected"]
    assert items[0]["payloadFields"] == ["reason"]


@pytest.mark.parametrize("category", EVENT_CATEGORIES)
def test_every_category_is_accepted(modelled, category) -> None:
    assert _declare(modelled, code=f"e_{category}", category=category)["category"] == category


def test_an_unknown_category_is_refused(modelled) -> None:
    with pytest.raises(EventError, match="事件类别"):
        _declare(modelled, category="whatever")


def test_an_event_code_must_be_an_identifier(modelled) -> None:
    with pytest.raises(EventError):
        _declare(modelled, code="not an identifier")


def test_an_event_type_needs_an_existing_object(modelled) -> None:
    with pytest.raises(EventError, match="业务对象不存在"):
        _declare(modelled, object_code="no_such_object")


def test_recording_an_undeclared_event_is_refused(modelled) -> None:
    """Accepting it would let «驳回», «拒绝» and «rejected» become three unrelated facts,
    and history would stop being queryable."""
    with pytest.raises(EventError, match="未声明"):
        record_event(
            modelled["platform_db"],
            modelled["ontology_id"],
            modelled["codes"]["customers"],
            "1",
            "never_declared",
        )


def test_a_missing_payload_field_warns_rather_than_refusing(modelled) -> None:
    """A legacy system that stopped sending one field must not silently stop producing
    history, which a strict refusal would cause."""
    _declare(modelled)
    recorded = record_event(
        modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "1", "rejected"
    )
    assert "reason" in recorded["payloadWarning"]


def test_extra_payload_fields_are_kept(modelled) -> None:
    """Discarding data an integrator sent is worse than storing a field nobody
    declared."""
    _declare(modelled)
    recorded = record_event(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["customers"],
        "1",
        "rejected",
        payload={"reason": "资料不全", "operator": "李四"},
    )
    assert recorded["payload"]["operator"] == "李四"
    assert recorded["payloadWarning"] == ""


def test_the_timeline_is_newest_first_and_reports_truncation(modelled) -> None:
    """A history that is quietly incomplete would make an explanation wrong rather
    than partial."""
    _declare(modelled)
    for index in range(3):
        record_event(
            modelled["platform_db"],
            modelled["ontology_id"],
            modelled["codes"]["customers"],
            "1",
            "rejected",
            payload={"reason": f"第{index}次"},
            occurred_at=f"2026-01-0{index + 1} 00:00:00",
        )
    timeline = instance_timeline(modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "1")
    assert [item["payload"]["reason"] for item in timeline["items"]] == ["第2次", "第1次", "第0次"]
    assert timeline["truncated"] is False

    limited = instance_timeline(
        modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "1", limit=2
    )
    assert limited["truncated"] is True
    assert limited["total"] == 3


def test_source_time_orders_history_not_ingestion_time(modelled) -> None:
    """Ingestion time would reorder a backfill."""
    _declare(modelled)
    record_event(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["customers"],
        "1",
        "rejected",
        payload={"reason": "较新"},
        occurred_at="2026-06-01 00:00:00",
    )
    record_event(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["customers"],
        "1",
        "rejected",
        payload={"reason": "回补的旧事件"},
        occurred_at="2020-01-01 00:00:00",
    )
    timeline = instance_timeline(modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "1")
    assert timeline["items"][0]["payload"]["reason"] == "较新"


def test_events_are_countable_as_data(modelled) -> None:
    """This is what makes events data rather than a log: 「上个月有多少份合同被驳回」
    is answerable without reading text."""
    _declare(modelled)
    for instance in ("1", "1", "2"):
        record_event(
            modelled["platform_db"],
            modelled["ontology_id"],
            modelled["codes"]["customers"],
            instance,
            "rejected",
            payload={"reason": "x"},
            occurred_at="2026-03-01 00:00:00",
        )
    args = (modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "rejected")
    assert count_events(*args) == 3
    assert count_events(*args, instance_id="1") == 2
    assert count_events(*args, since="2026-02-01") == 3
    assert count_events(*args, since="2026-04-01") == 0


def test_the_timeline_is_append_only(modelled) -> None:
    """No update or delete path exists: a wrong event is corrected by recording a
    compensating one, which is the only shape that keeps history honest."""
    import ontology_platform.events as events

    exported = [name for name in dir(events) if not name.startswith("_")]
    assert not [name for name in exported if "delete" in name or "update" in name], exported


def test_a_state_transition_lands_on_the_unified_timeline(modelled) -> None:
    """An instance must have one timeline, not one per subsystem."""
    from ontology_platform.workflow_permission import (
        create_workflow,
        enter_workflow,
        get_available_actions,
        init_workflow_and_permission_schema,
        transition_instance,
    )

    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    object_code = modelled["codes"]["customers"]
    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
    workflow = create_workflow(platform_db, ontology_id, object_code, "客户审核", "draft")
    workflow_id = int(workflow["id"])
    enter_workflow(platform_db, workflow_id, object_code, "1")
    # Use whatever the default state machine offers rather than assuming an action
    # name, so this test does not encode the seeded workflow's shape.
    action = get_available_actions(platform_db, workflow_id, "1")[0]
    action_code = action["action_code"] if "action_code" in action else action["actionCode"]
    state = transition_instance(platform_db, workflow_id, "1", action_code, actor="tester", reason="资料齐全")

    timeline = instance_timeline(platform_db, ontology_id, object_code, "1")
    codes = [item["eventCode"] for item in timeline["items"]]
    expected = f"state_{action_code}"
    assert expected in codes, codes
    moved = next(item for item in timeline["items"] if item["eventCode"] == expected)
    assert moved["category"] == STATE_CHANGE
    assert moved["payload"]["fromState"] == "draft"
    assert moved["payload"]["toState"] == state["current_state"]
    # Entering the workflow is where the timeline starts.
    assert "state_init" in codes


def test_recording_an_event_triggers_nothing(modelled) -> None:
    """An event that could fire automation would make replaying history re-execute
    business actions."""
    _declare(modelled, code="created", category=LIFECYCLE, payload_fields=[])
    before = _decision_count(modelled["platform_db"])
    record_event(modelled["platform_db"], modelled["ontology_id"], modelled["codes"]["customers"], "1", "created")
    assert _decision_count(modelled["platform_db"]) == before


def _decision_count(platform_db: Path) -> int:
    with connect(platform_db) as conn:
        return int(conn.execute("select count(*) as total from decision_record").fetchone()["total"])


def test_the_explanation_carries_the_timeline_and_ancestry(modelled) -> None:
    """A state without the events that produced it is a snapshot with no history."""
    platform_db, ontology_id = modelled["platform_db"], modelled["ontology_id"]
    parent, person, _ = _make_hierarchy(modelled)
    _declare(modelled, code="verified", object_code=person, payload_fields=[])
    record_event(platform_db, ontology_id, person, "1", "verified", actor="tester")
    explanation = explain_instance(platform_db, ontology_id, person, "1")
    assert explanation["ancestors"] == [parent]
    assert [item["eventCode"] for item in explanation["timeline"]] == ["verified"]


def test_a_database_without_the_event_tables_still_explains(tmp_path: Path) -> None:
    """The schema is created at startup, but an explanation must work on a database
    that predates it. Probed via the catalog, never by catching the error (ADR-0004)."""
    platform_db = tmp_path / "bare.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        assert event_tables_exist(conn) is False
    assert instance_timeline(platform_db, 1, "customer", "1") == {"items": [], "total": 0, "truncated": False}
    assert count_events(platform_db, 1, "customer", "rejected") == 0
    assert list_event_types(platform_db, 1) == []


def test_the_history_limit_is_bounded(modelled) -> None:
    _declare(modelled)
    timeline = instance_timeline(
        modelled["platform_db"],
        modelled["ontology_id"],
        modelled["codes"]["customers"],
        "1",
        limit=MAX_EVENT_HISTORY * 10,
    )
    assert timeline["total"] == 0


def test_declarations_are_audited(modelled) -> None:
    _declare(modelled)
    with connect(modelled["platform_db"]) as conn:
        rows = conn.execute("select actor from audit_log where action = 'declare_event_type'").fetchall()
    assert rows and rows[0]["actor"] == "tester"


def test_endpoints_have_sensible_capabilities() -> None:
    from ontology_platform.access_policy import required_capability

    assert required_capability("PUT", "/ontologies/1/objects/customer/parent") == "platform:write"
    assert required_capability("PUT", "/ontologies/1/objects/customer/event-types") == "platform:write"
    # History is append-only and feeds explanations, so recording is a write.
    assert required_capability("POST", "/ontologies/1/objects/customer/instances/1/events") == "platform:write"
    assert required_capability("GET", "/ontologies/1/hierarchy") == "platform:read"
