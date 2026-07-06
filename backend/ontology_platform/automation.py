from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import connect
from .semantic_kernel import assess_instance


def preflight_operation(
    platform_db: Path | str,
    ontology_id: int,
    data_source_id: int,
    operation_code: str,
    instance_id: str,
    object_code: str | None = None,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        operation = conn.execute(
            """
            select *
            from source_api
            where data_source_id = ?
              and operation_code = ?
            """,
            (data_source_id, operation_code),
        ).fetchone()
        if operation is None:
            raise ValueError(f"业务操作不存在: {operation_code}")

    resolved_object_code = object_code or _infer_object_code(operation["semantic_action"], operation_code)
    assessment = assess_instance(platform_db, ontology_id, resolved_object_code, instance_id)
    decision_status = assessment["decision"]["status"]
    allowed = decision_status == "approved"
    preflight = {
        "operation": {
            "dataSourceId": data_source_id,
            "operationCode": operation["operation_code"],
            "name": operation["name"],
            "method": operation["method"],
            "path": operation["path"],
            "semanticAction": operation["semantic_action"],
        },
        "target": {
            "ontologyId": ontology_id,
            "objectCode": resolved_object_code,
            "instanceId": instance_id,
        },
        "allowed": allowed,
        "decision": assessment["decision"],
        "ruleResults": assessment["ruleResults"],
        "nextAction": _next_action(allowed, decision_status),
    }
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "semantic_kernel",
                "preflight_operation",
                "source_api",
                str(operation["id"]),
                json.dumps(
                    {
                        "ontologyId": ontology_id,
                        "objectCode": resolved_object_code,
                        "instanceId": instance_id,
                        "allowed": allowed,
                        "decision": decision_status,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
    return preflight


def _infer_object_code(semantic_action: str, operation_code: str) -> str:
    if semantic_action and "." in semantic_action:
        return semantic_action.split(".", 1)[0]
    if "_" in operation_code:
        return operation_code.rsplit("_", 1)[0]
    raise ValueError("无法从业务操作推断业务对象，请显式传入 objectCode")


def _next_action(allowed: bool, decision_status: str) -> str:
    if allowed:
        return "allow_automation"
    if decision_status == "blocked":
        return "block_and_require_correction"
    return "route_to_human_review"

