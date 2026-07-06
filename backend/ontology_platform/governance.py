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


def derive_ontology_version(
    platform_db: Path | str,
    source_ontology_id: int,
    version: str,
    actor: str,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = _require_ontology(conn, source_ontology_id)
        if source["status"] != "published":
            raise ValueError("只能从已发布本体派生新版本。")
        existing = conn.execute(
            "select id from ontology where name = ? and version = ?",
            (source["name"], version),
        ).fetchone()
        if existing is not None:
            raise ValueError(f"本体版本已存在: {source['name']} {version}")

        conn.execute(
            "insert into ontology (name, domain, version, status) values (?, ?, ?, 'draft')",
            (source["name"], source["domain"], version),
        )
        new_ontology_id = int(conn.execute("select last_insert_rowid()").fetchone()[0])

        object_id_map: dict[int, int] = {}
        attribute_id_map: dict[int, int] = {}
        _copy_business_objects(conn, source_ontology_id, new_ontology_id, object_id_map, attribute_id_map)
        _copy_business_relations(conn, source_ontology_id, new_ontology_id, object_id_map)
        mapping_count = _copy_semantic_mappings(conn, source_ontology_id, new_ontology_id, object_id_map, attribute_id_map, source["version"])
        rule_count = _copy_business_rules(conn, source_ontology_id, new_ontology_id)

        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "derive_ontology_version",
                "ontology",
                str(source_ontology_id),
                json.dumps(
                    {
                        "newOntologyId": new_ontology_id,
                        "sourceVersion": source["version"],
                        "newVersion": version,
                        "mappings": mapping_count,
                        "rules": rule_count,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        return _ontology_derivation_summary(conn, new_ontology_id, source_ontology_id, mapping_count, rule_count)


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


def _copy_business_objects(
    conn: Any,
    source_ontology_id: int,
    new_ontology_id: int,
    object_id_map: dict[int, int],
    attribute_id_map: dict[int, int],
) -> None:
    objects = conn.execute(
        """
        select *
        from business_object
        where ontology_id = ?
        order by id
        """,
        (source_ontology_id,),
    ).fetchall()
    for business_object in objects:
        conn.execute(
            """
            insert into business_object (
                ontology_id, code, name, description, source_table_id, status
            )
            values (?, ?, ?, ?, ?, 'draft')
            """,
            (
                new_ontology_id,
                business_object["code"],
                business_object["name"],
                business_object["description"],
                business_object["source_table_id"],
            ),
        )
        new_object_id = int(conn.execute("select last_insert_rowid()").fetchone()[0])
        object_id_map[business_object["id"]] = new_object_id

        attributes = conn.execute(
            "select * from business_attribute where object_id = ? order by id",
            (business_object["id"],),
        ).fetchall()
        for attribute in attributes:
            conn.execute(
                """
                insert into business_attribute (
                    object_id, code, name, data_type, required, source_column_id
                )
                values (?, ?, ?, ?, ?, ?)
                """,
                (
                    new_object_id,
                    attribute["code"],
                    attribute["name"],
                    attribute["data_type"],
                    attribute["required"],
                    attribute["source_column_id"],
                ),
            )
            attribute_id_map[attribute["id"]] = int(conn.execute("select last_insert_rowid()").fetchone()[0])


def _copy_business_relations(
    conn: Any,
    source_ontology_id: int,
    new_ontology_id: int,
    object_id_map: dict[int, int],
) -> None:
    relations = conn.execute(
        "select * from business_relation where ontology_id = ? order by id",
        (source_ontology_id,),
    ).fetchall()
    for relation in relations:
        conn.execute(
            """
            insert into business_relation (
                ontology_id, source_object_id, target_object_id, code, name,
                relation_type, source_foreign_key_id
            )
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_ontology_id,
                object_id_map[relation["source_object_id"]],
                object_id_map[relation["target_object_id"]],
                relation["code"],
                relation["name"],
                relation["relation_type"],
                relation["source_foreign_key_id"],
            ),
        )


def _copy_semantic_mappings(
    conn: Any,
    source_ontology_id: int,
    new_ontology_id: int,
    object_id_map: dict[int, int],
    attribute_id_map: dict[int, int],
    source_version: str,
) -> int:
    mappings = conn.execute(
        "select * from semantic_mapping where ontology_id = ? order by id",
        (source_ontology_id,),
    ).fetchall()
    for mapping in mappings:
        conn.execute(
            """
            insert into semantic_mapping (
                ontology_id, mapping_type, source_ref, target_ref, confidence,
                status, evidence
            )
            values (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                new_ontology_id,
                mapping["mapping_type"],
                mapping["source_ref"],
                _remap_mapping_target(mapping["target_ref"], object_id_map, attribute_id_map),
                mapping["confidence"],
                _append_review_note(mapping["evidence"], f"由已发布版本 {source_version} 派生，需重新审核。"),
            ),
        )
    return len(mappings)


def _copy_business_rules(conn: Any, source_ontology_id: int, new_ontology_id: int) -> int:
    rules = conn.execute(
        "select * from business_rule where ontology_id = ? order by id",
        (source_ontology_id,),
    ).fetchall()
    for rule in rules:
        conn.execute(
            """
            insert into business_rule (
                ontology_id, code, name, rule_type, scope_object_code,
                expression, severity, natural_language, status
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_ontology_id,
                rule["code"],
                rule["name"],
                rule["rule_type"],
                rule["scope_object_code"],
                rule["expression"],
                rule["severity"],
                rule["natural_language"],
                rule["status"],
            ),
        )
    return len(rules)


def _remap_mapping_target(target_ref: str, object_id_map: dict[int, int], attribute_id_map: dict[int, int]) -> str:
    remapped = target_ref
    for old_id, new_id in object_id_map.items():
        remapped = remapped.replace(f"business_object:{old_id}", f"business_object:{new_id}")
    for old_id, new_id in attribute_id_map.items():
        remapped = remapped.replace(f"attribute:{old_id}", f"attribute:{new_id}")
    return remapped


def _ontology_derivation_summary(
    conn: Any,
    ontology_id: int,
    source_ontology_id: int,
    mapping_count: int,
    rule_count: int,
) -> dict[str, Any]:
    ontology = _require_ontology(conn, ontology_id)
    object_count = conn.execute(
        "select count(*) as count from business_object where ontology_id = ?",
        (ontology_id,),
    ).fetchone()["count"]
    return {
        "id": ontology["id"],
        "name": ontology["name"],
        "domain": ontology["domain"],
        "version": ontology["version"],
        "status": ontology["status"],
        "sourceOntologyId": source_ontology_id,
        "objectCount": object_count,
        "mappingCount": mapping_count,
        "ruleCount": rule_count,
    }
