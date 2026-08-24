from __future__ import annotations

import sqlite3
from typing import Any

from .context import PlatformDb
from .database import connect


def assess_operation_bindings(platform_db: PlatformDb, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        objects = {
            row["code"]: row
            for row in conn.execute(
                """
                select bo.id, bo.ontology_id, bo.code, bo.name, st.table_name, st.primary_key
                from business_object bo
                join source_table st on st.id = bo.source_table_id
                where st.data_source_id = ?
                order by bo.code
                """,
                (data_source_id,),
            ).fetchall()
        }
        rows = conn.execute(
            "select * from source_api where data_source_id = ? order by operation_code",
            (data_source_id,),
        ).fetchall()
        items = [_operation_binding(conn, row, objects) for row in rows]

    summary = {
        "operations": len(items),
        "boundOperations": sum(1 for item in items if item["status"] in {"bound", "ready", "incomplete"}),
        "readyOperations": sum(1 for item in items if item["status"] == "ready"),
        "unboundOperations": sum(1 for item in items if item["status"] == "unbound"),
        "invalidActions": sum(1 for item in items if item["status"] == "invalid"),
        "blockedOperations": sum(1 for item in items if item["status"] in {"invalid", "unbound", "incomplete"}),
    }
    status = (
        "ready"
        if items and summary["readyOperations"] == len(items)
        else "partial"
        if summary["boundOperations"]
        else "blocked"
    )
    return {
        "dataSourceId": data_source_id,
        "name": source["name"],
        "status": status,
        "summary": summary,
        "items": items,
        "nextActions": _next_actions(items),
    }


def _operation_binding(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    objects: dict[str, sqlite3.Row],
) -> dict[str, Any]:
    semantic_action = row["semantic_action"] or ""
    object_code, action_code = _parse_semantic_action(semantic_action)
    gaps: list[str] = []
    if not semantic_action:
        gaps.append("缺少语义动作。")
        status = "invalid"
    elif not object_code or not action_code:
        gaps.append("语义动作必须使用 object.action 格式。")
        status = "invalid"
    elif object_code not in objects:
        gaps.append(f"语义动作对象 {object_code} 未绑定到当前数据源本体对象。")
        status = "unbound"
    else:
        business_object = objects[object_code]
        confirmed_mappings = conn.execute(
            """
            select count(*) as total
            from semantic_mapping
            where ontology_id = ?
              and status = 'confirmed'
              and (source_ref = ? or source_ref like ?)
            """,
            (
                business_object["ontology_id"],
                f"table:{business_object['table_name']}",
                f"table:{business_object['table_name']}.column:%",
            ),
        ).fetchone()["total"]
        rule_count = conn.execute(
            "select count(*) as total from business_rule where ontology_id = ? and scope_object_code = ? and status = 'published'",
            (business_object["ontology_id"], object_code),
        ).fetchone()["total"]
        if not business_object["primary_key"]:
            gaps.append("业务对象来源表缺少主键，无法稳定执行预检。")
        if confirmed_mappings == 0:
            gaps.append("业务对象缺少已确认语义映射。")
        if rule_count == 0:
            gaps.append("业务对象缺少发布态业务规则。")
        status = "ready" if not gaps else "incomplete"

    return {
        "operationCode": row["operation_code"],
        "name": row["name"],
        "method": row["method"],
        "path": row["path"],
        "semanticAction": semantic_action,
        "objectCode": object_code,
        "actionCode": action_code,
        "status": status,
        "automationReady": status == "ready",
        "gaps": gaps,
    }


def _parse_semantic_action(semantic_action: str) -> tuple[str, str]:
    if "." not in semantic_action:
        return semantic_action, ""
    object_code, action_code = semantic_action.split(".", 1)
    return object_code.strip(), action_code.strip()


def _next_actions(items: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if any(item["status"] == "invalid" for item in items):
        actions.append("为缺少或格式错误的 API 补充 object.action 形式语义动作。")
    if any(item["status"] == "unbound" for item in items):
        actions.append("将 API 语义动作中的对象编码绑定到当前数据源本体对象。")
    if any(item["status"] == "incomplete" for item in items):
        actions.append("补齐已确认映射、发布态规则和实例主键后再开放自动化执行。")
    if not items:
        actions.append("登记传统业务系统 API，并绑定语义动作。")
    if not actions:
        actions.append("API 语义动作已完成绑定，可进入预检和执行治理。")
    return actions
