from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .database import connect


def build_semantic_coverage(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")

        objects = _object_rows(conn, data_source_id)
        if not objects:
            return {
                "dataSourceId": data_source_id,
                "name": source["name"],
                "domain": source["domain"],
                "status": "not_modeled",
                "score": 0,
                "summary": _summary(),
                "objects": [],
                "operations": _operation_rows(conn, data_source_id),
                "nextActions": ["先扫描元数据并生成本体草案，建立业务对象与传统表的语义映射。"],
            }

        coverage_objects = [_object_coverage(conn, row) for row in objects]
        operations = _operation_rows(conn, data_source_id)
        summary = _summary(
            business_objects=len(coverage_objects),
            fully_covered_objects=sum(1 for item in coverage_objects if item["status"] == "ready"),
            partial_objects=sum(1 for item in coverage_objects if item["status"] == "partial"),
            blocked_objects=sum(1 for item in coverage_objects if item["status"] == "blocked"),
            attributes=sum(item["attributeCount"] for item in coverage_objects),
            confirmed_mappings=sum(item["confirmedMappings"] for item in coverage_objects),
            pending_mappings=sum(item["pendingMappings"] for item in coverage_objects),
            rules=sum(item["ruleCount"] for item in coverage_objects),
            operations=len(operations),
            semantic_operations=sum(1 for item in operations if item["semanticAction"]),
            executable_operations=sum(1 for item in operations if item["automationReady"]),
        )
        score = _coverage_score(summary, coverage_objects, operations)
        return {
            "dataSourceId": data_source_id,
            "name": source["name"],
            "domain": source["domain"],
            "status": _coverage_status(score, summary),
            "score": score,
            "summary": summary,
            "objects": coverage_objects,
            "operations": operations,
            "nextActions": _next_actions(summary, coverage_objects, operations),
        }


def _object_rows(conn: sqlite3.Connection, data_source_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        select bo.id, bo.ontology_id, bo.code, bo.name, bo.status,
               st.data_source_id,
               st.table_name, st.primary_key, o.name as ontology_name, o.version, o.status as ontology_status
        from business_object bo
        join source_table st on st.id = bo.source_table_id
        join ontology o on o.id = bo.ontology_id
        where st.data_source_id = ?
        order by o.id, bo.code
        """,
        (data_source_id,),
    ).fetchall()


def _object_coverage(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    attributes = conn.execute("select count(*) as total from business_attribute where object_id = ?", (row["id"],)).fetchone()["total"]
    mapping_counts = conn.execute(
        """
        select status, count(*) as total
        from semantic_mapping
        where ontology_id = ?
          and (source_ref = ? or source_ref like ?)
        group by status
        """,
        (row["ontology_id"], f"table:{row['table_name']}", f"table:{row['table_name']}.column:%"),
    ).fetchall()
    rule_count = conn.execute(
        "select count(*) as total from business_rule where ontology_id = ? and scope_object_code = ?",
        (row["ontology_id"], row["code"]),
    ).fetchone()["total"]
    operation_rows = conn.execute(
        """
        select operation_code, name, method, path, semantic_action
        from source_api
        where data_source_id = ?
          and semantic_action like ?
        order by operation_code
        """,
        (row["data_source_id"], f"{row['code']}.%"),
    ).fetchall()
    confirmed = _mapping_count(mapping_counts, "confirmed")
    pending = _mapping_count(mapping_counts, "pending")
    rejected = _mapping_count(mapping_counts, "rejected")
    operation_count = len(operation_rows)
    automation_ready = bool(row["primary_key"]) and confirmed > 0 and rule_count > 0 and operation_count > 0
    status = "ready" if automation_ready else "partial" if confirmed > 0 or pending > 0 or rule_count > 0 or operation_count > 0 else "blocked"
    return {
        "ontologyId": row["ontology_id"],
        "ontologyName": row["ontology_name"],
        "ontologyVersion": row["version"],
        "ontologyStatus": row["ontology_status"],
        "objectId": row["id"],
        "objectCode": row["code"],
        "objectName": row["name"],
        "sourceTable": row["table_name"],
        "primaryKey": row["primary_key"],
        "attributeCount": attributes,
        "confirmedMappings": confirmed,
        "pendingMappings": pending,
        "rejectedMappings": rejected,
        "ruleCount": rule_count,
        "operationCount": operation_count,
        "automationReady": automation_ready,
        "status": status,
        "gaps": _object_gaps(row, confirmed, pending, rule_count, operation_count),
        "operations": [_operation_dict(item, row["code"]) for item in operation_rows],
    }


def _operation_rows(conn: sqlite3.Connection, data_source_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select operation_code, name, method, path, semantic_action
        from source_api
        where data_source_id = ?
        order by operation_code
        """,
        (data_source_id,),
    ).fetchall()
    return [_operation_dict(row, _operation_object_code(row["semantic_action"])) for row in rows]


def _operation_dict(row: sqlite3.Row, object_code: str) -> dict[str, Any]:
    semantic_action = row["semantic_action"] or ""
    return {
        "operationCode": row["operation_code"],
        "name": row["name"],
        "method": row["method"],
        "path": row["path"],
        "semanticAction": semantic_action,
        "objectCode": object_code,
        "automationReady": bool(semantic_action and object_code),
    }


def _operation_object_code(semantic_action: str) -> str:
    if semantic_action and "." in semantic_action:
        return semantic_action.split(".", 1)[0]
    return ""


def _object_gaps(row: sqlite3.Row, confirmed: int, pending: int, rule_count: int, operation_count: int) -> list[str]:
    gaps: list[str] = []
    if not row["primary_key"]:
        gaps.append("缺少主键，无法稳定定位业务对象实例。")
    if confirmed == 0:
        gaps.append("缺少已确认语义映射，自动化决策证据不足。")
    if pending > 0:
        gaps.append("存在待审核语义映射，需要业务专家确认。")
    if rule_count == 0:
        gaps.append("缺少业务规则，无法进行主动研判。")
    if operation_count == 0:
        gaps.append("缺少绑定到该对象的业务 API 操作，暂不能闭环自动化。")
    return gaps


def _mapping_count(rows: list[sqlite3.Row], status: str) -> int:
    for row in rows:
        if row["status"] == status:
            return int(row["total"])
    return 0


def _summary(
    business_objects: int = 0,
    fully_covered_objects: int = 0,
    partial_objects: int = 0,
    blocked_objects: int = 0,
    attributes: int = 0,
    confirmed_mappings: int = 0,
    pending_mappings: int = 0,
    rules: int = 0,
    operations: int = 0,
    semantic_operations: int = 0,
    executable_operations: int = 0,
) -> dict[str, int]:
    return {
        "businessObjects": business_objects,
        "fullyCoveredObjects": fully_covered_objects,
        "partialObjects": partial_objects,
        "blockedObjects": blocked_objects,
        "attributes": attributes,
        "confirmedMappings": confirmed_mappings,
        "pendingMappings": pending_mappings,
        "rules": rules,
        "operations": operations,
        "semanticOperations": semantic_operations,
        "executableOperations": executable_operations,
    }


def _coverage_score(summary: dict[str, int], objects: list[dict[str, Any]], operations: list[dict[str, Any]]) -> int:
    if summary["businessObjects"] == 0:
        return 0
    object_score = sum(1 for item in objects if item["confirmedMappings"] > 0) / summary["businessObjects"] * 35
    rule_score = sum(1 for item in objects if item["ruleCount"] > 0) / summary["businessObjects"] * 25
    operation_score = (summary["semanticOperations"] / len(operations) * 20) if operations else 0
    automation_score = summary["fullyCoveredObjects"] / summary["businessObjects"] * 20
    return round(object_score + rule_score + operation_score + automation_score)


def _coverage_status(score: int, summary: dict[str, int]) -> str:
    if summary["businessObjects"] == 0:
        return "not_modeled"
    if score >= 85 and summary["blockedObjects"] == 0 and summary["pendingMappings"] == 0:
        return "ready"
    if score >= 50:
        return "partial"
    return "blocked"


def _next_actions(summary: dict[str, int], objects: list[dict[str, Any]], operations: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    if summary["pendingMappings"]:
        actions.append("优先审核待确认语义映射，提升决策证据确定性。")
    if any(item["ruleCount"] == 0 for item in objects):
        actions.append("为缺少规则的业务对象补充准入、风险、自动化放行等业务规则。")
    if not operations:
        actions.append("登记传统业务系统 API，并用语义动作绑定到业务对象。")
    elif summary["semanticOperations"] < len(operations):
        actions.append("为未绑定语义动作的 API 补充 object.action 形式的语义动作。")
    if any(not item["primaryKey"] for item in objects):
        actions.append("为缺少主键的传统表补充实例标识策略。")
    if not actions:
        actions.append("语义覆盖已形成闭环，可进入运行期监控、漂移分析和版本治理。")
    return actions
