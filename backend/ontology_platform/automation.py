from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request
from urllib.parse import urljoin

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


def execute_operation(
    platform_db: Path | str,
    ontology_id: int,
    data_source_id: int,
    operation_code: str,
    instance_id: str,
    object_code: str | None = None,
    payload: dict[str, Any] | None = None,
    actor: str = "semantic_kernel",
    dry_run: bool = True,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    preflight = preflight_operation(platform_db, ontology_id, data_source_id, operation_code, instance_id, object_code)
    operation = preflight["operation"]
    if not preflight["allowed"]:
        result = {
            "executed": False,
            "status": "blocked_by_semantic_kernel",
            "preflight": preflight,
            "execution": None,
            "message": "业务语义内核已拦截该操作，需按预检建议处理。",
        }
        _audit_execution(platform_db, actor, operation, result)
        return result

    execution_plan = {
        "method": operation["method"],
        "path": _render_operation_path(operation["path"], instance_id, payload or {}),
        "semanticAction": operation["semanticAction"],
        "payload": payload or {},
        "dryRun": dry_run,
    }
    if dry_run:
        result = {
            "executed": False,
            "status": "ready_for_execution",
            "preflight": preflight,
            "execution": execution_plan,
            "message": "预检通过，已生成可执行计划。关闭 dryRun 后可调用传统业务系统。",
        }
        _audit_execution(platform_db, actor, operation, result)
        return result

    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        connection_uri = source["connection_uri"]
    if not connection_uri.lower().startswith(("http://", "https://")):
        raise ValueError("真实执行仅支持 HTTP/HTTPS 业务系统连接；数据库类系统请使用 dryRun 或配置业务 API 网关地址")

    remote = _invoke_http_operation(connection_uri, execution_plan, timeout_seconds)
    result = {
        "executed": True,
        "status": "executed",
        "preflight": preflight,
        "execution": {**execution_plan, "remote": remote},
        "message": "预检通过，传统业务系统操作已执行。",
    }
    _audit_execution(platform_db, actor, operation, result)
    return result


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


def _render_operation_path(path: str, instance_id: str, payload: dict[str, Any]) -> str:
    rendered = path.replace("{id}", str(instance_id)).replace("{instanceId}", str(instance_id)).replace("{instance_id}", str(instance_id))
    for key, value in payload.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered


def _invoke_http_operation(base_url: str, execution_plan: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    url = urljoin(base_url.rstrip("/") + "/", execution_plan["path"].lstrip("/"))
    body = json.dumps(execution_plan["payload"], ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body if execution_plan["method"] not in {"GET", "DELETE"} else None,
        method=execution_plan["method"],
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read().decode("utf-8")
            return {
                "url": url,
                "statusCode": response.status,
                "body": _parse_json_or_text(content),
            }
    except urllib.error.HTTPError as error:
        content = error.read().decode("utf-8")
        return {
            "url": url,
            "statusCode": error.code,
            "body": _parse_json_or_text(content),
            "error": error.reason,
        }
    except urllib.error.URLError as error:
        raise ValueError(f"传统业务系统调用失败: {error.reason}") from error


def _parse_json_or_text(content: str) -> Any:
    if not content:
        return None
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return content


def _audit_execution(platform_db: Path | str, actor: str, operation: dict[str, Any], result: dict[str, Any]) -> None:
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "execute_operation",
                "source_api",
                operation["operationCode"],
                json.dumps(
                    {
                        "status": result["status"],
                        "executed": result["executed"],
                        "decision": result["preflight"]["decision"]["status"],
                        "nextAction": result["preflight"]["nextAction"],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
