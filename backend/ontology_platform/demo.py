"""The built-in demo scenarios, in one place.

This flow existed three times -- in the CLI, in the HTTP layer and in a script under
`scripts/` -- and the three had already drifted. The terminal path assessed an instance and
the browser path did not, so a reader who clicked "先体验演示" was promised "one complete
verdict" by the button's own caption and arrived at a workbench reporting **0 决策留痕**.
Two implementations of one scenario is one implementation that is wrong.

A function rather than three call sites: the demo is the first thing anybody sees, and it
is the single most expensive thing to have disagree with itself.

What the scenario covers is deliberate. It runs the whole loop -- register, scan, draft --
and then performs the three things a fresh deployment otherwise cannot show: one verdict,
one recorded event and one recorded attribute value. Without those the instance
explanation, the timeline and the value history are all empty screens, and **an empty
screen is indistinguishable from a missing feature**.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import PlatformDb
from .metadata import register_data_source, register_source_api, scan_data_source
from .ontology import explain_instance, generate_ontology_draft
from .sample_data import create_contract_sample_db, create_equipment_sample_db
from .semantic_kernel import assess_instance
from .vocabulary import default_object_code_for_ontology

__all__ = [
    "run_contract_demo",
    "run_equipment_demo",
]

# The instant the demo's recorded value history starts. Fixed rather than "now", so a
# reader asking "what did it say before" gets an answer that predates the live row instead
# of one identical to it.
DEMO_HISTORY_START = "2026-01-01 00:00:00"


def run_contract_demo(platform_db: PlatformDb, sample_db_path: Path | str) -> dict[str, Any]:
    """Register, scan and model the contract sample system, then exercise it once."""
    sample_path = create_contract_sample_db(Path(sample_db_path))
    return _run_scenario(
        platform_db,
        name="合同管理样例系统",
        sample_path=sample_path,
        domain="合同管理",
        operation=("submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval"),
        event=("signed", "签订"),
    )


def run_equipment_demo(platform_db: PlatformDb, sample_db_path: Path | str) -> dict[str, Any]:
    """The second scenario. Same shape, so the two cannot diverge in what they demonstrate."""
    sample_path = create_equipment_sample_db(Path(sample_db_path))
    return _run_scenario(
        platform_db,
        name="设备运维样例系统",
        sample_path=sample_path,
        domain="设备运维",
        operation=("close_work_order", "关闭工单", "POST", "/work-orders/{id}/close", "work_order.close"),
        event=("closed", "已关闭"),
    )


def _run_scenario(
    platform_db: PlatformDb,
    *,
    name: str,
    sample_path: Path,
    domain: str,
    operation: tuple[str, str, str, str, str],
    event: tuple[str, str],
) -> dict[str, Any]:
    from .database import connect
    from .events import EventType, declare_event_type, init_event_schema, record_event
    from .temporal import init_temporal_schema, record_attribute_version

    # The event and value-history schemas belong to optional feature bundles, so a caller
    # that only ran `initialize_platform_db` does not have their tables. Creating them here
    # rather than requiring it of the caller is the difference between "the demo works on a
    # database it just made" and "the demo works if you happened to start the server first"
    # -- and the latter is how this failed the first time it ran from a test.
    with connect(platform_db) as conn:
        init_event_schema(conn)
        init_temporal_schema(conn)

    source = register_data_source(
        platform_db,
        name,
        "sqlite",
        str(sample_path),
        domain=domain,
        system_category="database+api",
    )
    register_source_api(platform_db, source.id, *operation)
    scan = scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    ontology_id = int(ontology["id"])
    # Discovered from the blueprint's lexicon rather than assumed (ADR-0003): hardcoding
    # "contract" would break the moment the blueprint is renamed.
    object_code = default_object_code_for_ontology(platform_db, ontology_id)

    verdict = assess_instance(platform_db, ontology_id, object_code, "1")

    event_code, event_name = event
    declare_event_type(
        platform_db,
        ontology_id,
        EventType(code=event_code, name=event_name, object_code=object_code, description=name),
        actor="bootstrap",
    )
    record_event(
        platform_db,
        ontology_id,
        object_code,
        "1",
        event_code,
        payload={"source": "aletheia demo"},
        actor="bootstrap",
    )

    # One declared attribute with a value, so the value-history section has something in it.
    # Which one is discovered rather than named: recording a version for an attribute the
    # object does not have is refused, and guessing the name would tie the demo to the
    # blueprint's wording.
    explanation = explain_instance(platform_db, ontology_id, object_code, "1")
    for attribute in explanation.get("attributes", []):
        if attribute.get("value") not in (None, ""):
            record_attribute_version(
                platform_db,
                ontology_id,
                object_code,
                "1",
                str(attribute["attributeCode"]),
                attribute["value"],
                valid_from=DEMO_HISTORY_START,
                actor="bootstrap",
            )
            break

    # A workflow, entered and moved once. Without it the workflow screen is empty on a fresh
    # install -- and it is the governance capability a reviewer most wants to see working:
    # states, a permitted transition, and the same change appearing on the instance timeline
    # through the mirror. An empty screen is indistinguishable from a missing feature.
    from .workflow_permission import (
        create_workflow,
        enter_workflow,
        get_available_actions,
        init_workflow_and_permission_schema,
        transition_instance,
    )

    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
    workflow = create_workflow(platform_db, ontology_id, object_code, f"{domain}审批流")
    enter_workflow(platform_db, workflow["id"], object_code, "1")
    # The first permitted action, whatever the seeded state machine calls it: it is defined
    # by the workflow module, not by this scenario, and naming it here would tie the demo to
    # a detail that module is free to change.
    actions = get_available_actions(platform_db, workflow["id"], "1")
    if actions:
        transition_instance(platform_db, workflow["id"], "1", actions[0]["action_code"], actor="bootstrap")

    return {
        "source": source,
        "samplePath": sample_path,
        "scan": scan,
        "ontology": ontology,
        "ontologyId": ontology_id,
        "objectCode": object_code,
        "decision": (verdict.get("decision") or {}).get("status", ""),
        "workflowId": workflow["id"],
    }
