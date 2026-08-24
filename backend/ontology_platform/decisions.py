from __future__ import annotations

import json
import sqlite3
from typing import Any
from uuid import uuid4

from .context import PlatformDb
from .database import connect


def record_decision(
    platform_db: PlatformDb,
    decision_type: str,
    status: str,
    recommendation: str = "",
    ontology_id: int | None = None,
    object_code: str = "",
    instance_id: str = "",
    operation_code: str = "",
    input_ref: dict[str, Any] | None = None,
    rule_results: list[dict[str, Any]] | None = None,
    evidence: dict[str, Any] | None = None,
    actor: str = "semantic_kernel",
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        return record_decision_in_connection(
            conn,
            decision_type,
            status,
            recommendation,
            ontology_id,
            object_code,
            instance_id,
            operation_code,
            input_ref,
            rule_results,
            evidence,
            actor,
        )


def record_decision_in_connection(
    conn: sqlite3.Connection,
    decision_type: str,
    status: str,
    recommendation: str = "",
    ontology_id: int | None = None,
    object_code: str = "",
    instance_id: str = "",
    operation_code: str = "",
    input_ref: dict[str, Any] | None = None,
    rule_results: list[dict[str, Any]] | None = None,
    evidence: dict[str, Any] | None = None,
    actor: str = "semantic_kernel",
) -> dict[str, Any]:
    decision_id = f"DR-{uuid4().hex[:12]}"
    conn.execute(
        """
        insert into decision_record (
            decision_id, decision_type, ontology_id, object_code, instance_id,
            operation_code, status, recommendation, input_ref, rule_results,
            evidence, actor
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision_id,
            decision_type,
            ontology_id,
            object_code,
            instance_id,
            operation_code,
            status,
            recommendation,
            json.dumps(input_ref or {}, ensure_ascii=False),
            json.dumps(rule_results or [], ensure_ascii=False),
            json.dumps(evidence or {}, ensure_ascii=False),
            actor,
        ),
    )
    row = conn.execute("select * from decision_record where decision_id = ?", (decision_id,)).fetchone()
    return _decision_row(row)


def list_decisions(platform_db: PlatformDb, limit: int = 50) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select *
            from decision_record
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return [_decision_row(row) for row in rows]


def _decision_row(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "decisionId": row["decision_id"],
        "decision_id": row["decision_id"],
        "decisionType": row["decision_type"],
        "decision_type": row["decision_type"],
        "ontologyId": row["ontology_id"],
        "ontology_id": row["ontology_id"],
        "objectCode": row["object_code"],
        "object_code": row["object_code"],
        "instanceId": row["instance_id"],
        "instance_id": row["instance_id"],
        "operationCode": row["operation_code"],
        "operation_code": row["operation_code"],
        "status": row["status"],
        "recommendation": row["recommendation"],
        "inputRef": json.loads(row["input_ref"] or "{}"),
        "input_ref": json.loads(row["input_ref"] or "{}"),
        "ruleResults": json.loads(row["rule_results"] or "[]"),
        "rule_results": json.loads(row["rule_results"] or "[]"),
        "evidence": json.loads(row["evidence"] or "{}"),
        "actor": row["actor"],
        "createdAt": row["created_at"],
        "created_at": row["created_at"],
    }
