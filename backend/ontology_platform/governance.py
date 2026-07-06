from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import connect


VALID_MAPPING_STATUSES = {"pending", "confirmed", "rejected"}
VALID_ONTOLOGY_STATUSES = {"draft", "reviewing", "published", "deprecated"}
VALID_RULE_TYPES = {"validation", "derivation", "transition", "risk", "recommendation", "permission"}
VALID_RULE_SEVERITIES = {"info", "warning", "blocking"}


def list_semantic_mappings(platform_db: Path | str, ontology_id: int, status: str | None = None) -> dict[str, Any]:
    with connect(platform_db) as conn:
        _require_ontology(conn, ontology_id)
        params: list[Any] = [ontology_id]
        status_filter = ""
        if status:
            status_filter = " and status = ?"
            params.append(status)
        rows = conn.execute(
            f"""
            select id, mapping_type, source_ref, target_ref, confidence, status,
                   evidence, reviewer, reviewed_at, created_at
            from semantic_mapping
            where ontology_id = ?
            {status_filter}
            order by id
            """,
            tuple(params),
        ).fetchall()
        return {
            "ontologyId": ontology_id,
            "items": [dict(row) for row in rows],
        }


def review_semantic_mapping(
    platform_db: Path | str,
    mapping_id: int,
    status: str,
    reviewer: str,
    note: str = "",
) -> dict[str, Any]:
    _validate_mapping_status(status)
    with connect(platform_db) as conn:
        mapping = conn.execute("select * from semantic_mapping where id = ?", (mapping_id,)).fetchone()
        if mapping is None:
            raise ValueError(f"语义映射不存在: {mapping_id}")
        ontology = _require_ontology(conn, mapping["ontology_id"])
        if ontology["status"] == "published":
            raise ValueError("已发布本体的语义映射不可直接审核，请派生新版本。")
        evidence = _append_review_note(mapping["evidence"], note)
        conn.execute(
            """
            update semantic_mapping
            set status = ?, reviewer = ?, reviewed_at = current_timestamp, evidence = ?
            where id = ?
            """,
            (status, reviewer, evidence, mapping_id),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                reviewer,
                "review_semantic_mapping",
                "semantic_mapping",
                str(mapping_id),
                json.dumps({"status": status, "note": note}, ensure_ascii=False),
            ),
        )
        return dict(conn.execute("select * from semantic_mapping where id = ?", (mapping_id,)).fetchone())


def bulk_review_semantic_mappings(
    platform_db: Path | str,
    ontology_id: int,
    status: str,
    reviewer: str,
    note: str = "",
) -> dict[str, Any]:
    _validate_mapping_status(status)
    with connect(platform_db) as conn:
        ontology = _require_ontology(conn, ontology_id)
        if ontology["status"] == "published":
            raise ValueError("已发布本体的语义映射不可直接审核，请派生新版本。")
        rows = conn.execute(
            "select id, evidence from semantic_mapping where ontology_id = ? and status = 'pending'",
            (ontology_id,),
        ).fetchall()
        for row in rows:
            conn.execute(
                """
                update semantic_mapping
                set status = ?, reviewer = ?, reviewed_at = current_timestamp, evidence = ?
                where id = ?
                """,
                (status, reviewer, _append_review_note(row["evidence"], note), row["id"]),
            )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                reviewer,
                "bulk_review_semantic_mappings",
                "ontology",
                str(ontology_id),
                json.dumps({"status": status, "count": len(rows), "note": note}, ensure_ascii=False),
            ),
        )
        return {"ontologyId": ontology_id, "status": status, "reviewedCount": len(rows)}


def publish_ontology(platform_db: Path | str, ontology_id: int, publisher: str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        ontology = _require_ontology(conn, ontology_id)
        if ontology["status"] == "published":
            return _ontology_publication_summary(conn, ontology_id)
        if ontology["status"] not in {"draft", "reviewing"}:
            raise ValueError(f"当前本体状态不可发布: {ontology['status']}")
        pending_count = conn.execute(
            "select count(*) as count from semantic_mapping where ontology_id = ? and status = 'pending'",
            (ontology_id,),
        ).fetchone()["count"]
        if pending_count:
            raise ValueError(f"仍有 {pending_count} 条语义映射待审核，不能发布本体。")
        confirmed_count = conn.execute(
            "select count(*) as count from semantic_mapping where ontology_id = ? and status = 'confirmed'",
            (ontology_id,),
        ).fetchone()["count"]
        if confirmed_count == 0:
            raise ValueError("没有已确认的语义映射，不能发布本体。")
        conn.execute(
            "update ontology set status = 'published', published_at = current_timestamp where id = ?",
            (ontology_id,),
        )
        conn.execute(
            "update business_object set status = 'confirmed' where ontology_id = ?",
            (ontology_id,),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                publisher,
                "publish_ontology",
                "ontology",
                str(ontology_id),
                json.dumps({"confirmedMappings": confirmed_count}, ensure_ascii=False),
            ),
        )
        return _ontology_publication_summary(conn, ontology_id)


def list_business_rules(platform_db: Path | str, ontology_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        _require_ontology(conn, ontology_id)
        rows = conn.execute(
            """
            select id, code, name, rule_type, scope_object_code, expression,
                   severity, natural_language, status
            from business_rule
            where ontology_id = ?
            order by code
            """,
            (ontology_id,),
        ).fetchall()
        return {"ontologyId": ontology_id, "items": [dict(row) for row in rows]}


def upsert_business_rule(
    platform_db: Path | str,
    ontology_id: int,
    code: str,
    name: str,
    rule_type: str,
    scope_object_code: str,
    expression: str,
    severity: str,
    natural_language: str,
    actor: str,
    status: str = "published",
) -> dict[str, Any]:
    if rule_type not in VALID_RULE_TYPES:
        raise ValueError(f"不支持的规则类型: {rule_type}")
    if severity not in VALID_RULE_SEVERITIES:
        raise ValueError(f"不支持的规则严重级别: {severity}")
    with connect(platform_db) as conn:
        ontology = _require_ontology(conn, ontology_id)
        if ontology["status"] == "published":
            raise ValueError("已发布本体的规则不可直接修改，请派生新版本。")
        scope = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, scope_object_code),
        ).fetchone()
        if scope is None:
            raise ValueError(f"规则适用业务对象不存在: {scope_object_code}")
        conn.execute(
            """
            insert into business_rule (
                ontology_id, code, name, rule_type, scope_object_code,
                expression, severity, natural_language, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(ontology_id, code) do update set
                name = excluded.name,
                rule_type = excluded.rule_type,
                scope_object_code = excluded.scope_object_code,
                expression = excluded.expression,
                severity = excluded.severity,
                natural_language = excluded.natural_language,
                status = excluded.status
            """,
            (ontology_id, code, name, rule_type, scope_object_code, expression, severity, natural_language, status),
        )
        rule = conn.execute(
            "select * from business_rule where ontology_id = ? and code = ?",
            (ontology_id, code),
        ).fetchone()
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "upsert_business_rule",
                "business_rule",
                str(rule["id"]),
                json.dumps({"code": code, "scope": scope_object_code}, ensure_ascii=False),
            ),
        )
        return dict(rule)


def _require_ontology(conn: Any, ontology_id: int) -> Any:
    ontology = conn.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
    if ontology is None:
        raise ValueError(f"本体不存在: {ontology_id}")
    return ontology


def _validate_mapping_status(status: str) -> None:
    if status not in VALID_MAPPING_STATUSES:
        raise ValueError(f"不支持的语义映射状态: {status}")


def _append_review_note(evidence: str, note: str) -> str:
    if not note:
        return evidence
    if not evidence:
        return f"审核意见：{note}"
    return f"{evidence}\n审核意见：{note}"


def _ontology_publication_summary(conn: Any, ontology_id: int) -> dict[str, Any]:
    ontology = _require_ontology(conn, ontology_id)
    mapping_counts = conn.execute(
        """
        select status, count(*) as count
        from semantic_mapping
        where ontology_id = ?
        group by status
        """,
        (ontology_id,),
    ).fetchall()
    return {
        "id": ontology["id"],
        "name": ontology["name"],
        "domain": ontology["domain"],
        "version": ontology["version"],
        "status": ontology["status"],
        "publishedAt": ontology["published_at"],
        "mappingCounts": {row["status"]: row["count"] for row in mapping_counts},
    }

