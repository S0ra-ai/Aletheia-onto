from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import connect, last_insert_id
from .release_readiness import assess_ontology_release_readiness
from .semantic_kernel import validate_rule_expression
from .type_hierarchy import inherited_rule_scopes

VALID_MAPPING_STATUSES = {"pending", "confirmed", "rejected"}
VALID_ONTOLOGY_STATUSES = {"draft", "reviewing", "published", "deprecated"}
VALID_RULE_TYPES = {"validation", "derivation", "transition", "risk", "recommendation", "permission"}
VALID_RULE_SEVERITIES = {"info", "warning", "blocking"}


def _validate_rule_write(rule_type: str, severity: str, expression: str) -> None:
    """Reject rules that could never be evaluated.

    The kernel now fails closed, so an unparseable expression would turn into a
    permanent "not passed" verdict. Catching it at write time keeps the failure
    at the point where a human can fix it.
    """
    if rule_type not in VALID_RULE_TYPES:
        raise ValueError(f"不支持的规则类型: {rule_type}")
    if severity not in VALID_RULE_SEVERITIES:
        raise ValueError(f"不支持的规则严重级别: {severity}")
    validation = validate_rule_expression(expression)
    if not validation["valid"]:
        raise ValueError(f"规则表达式不可执行: {validation['error']}")


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


def publish_ontology(
    platform_db: Path | str,
    ontology_id: int,
    publisher: str,
    force: bool = False,
) -> dict[str, Any]:
    """Publish an ontology version after the release gates pass.

    `force` records an explicit override in the audit log so a deliberate
    business decision to publish with open warnings stays traceable.
    """
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

    # Assessed outside the write transaction because readiness reads the live
    # source databases for drift detection.
    readiness = _assess_release_gates(platform_db, ontology_id)
    blockers = [gate for gate in readiness["gates"] if gate["severity"] == "blocker" and not gate["passed"]]
    if blockers and not force:
        blocker_summary = "；".join(f"{gate['name']}: {gate['evidence']}" for gate in blockers[:5])
        raise ValueError(f"发布门禁未通过，存在 {len(blockers)} 项阻断项，不能发布本体。{blocker_summary}")

    with connect(platform_db) as conn:
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
                json.dumps(
                    {
                        "confirmedMappings": confirmed_count,
                        "releaseStatus": readiness["status"],
                        "passedGates": readiness["summary"]["passedGates"],
                        "totalGates": readiness["summary"]["totalGates"],
                        "blockers": len(blockers),
                        "warnings": readiness["summary"]["warnings"],
                        "forced": bool(force and blockers),
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        summary = _ontology_publication_summary(conn, ontology_id)
    summary["releaseReadiness"] = {
        "status": readiness["status"],
        "passedGates": readiness["summary"]["passedGates"],
        "totalGates": readiness["summary"]["totalGates"],
        "blockers": len(blockers),
        "warnings": readiness["summary"]["warnings"],
        "forced": bool(force and blockers),
    }
    return summary


def _assess_release_gates(platform_db: Path | str, ontology_id: int) -> dict[str, Any]:
    return assess_ontology_release_readiness(platform_db, ontology_id)


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
        new_ontology_id = last_insert_id(conn)

        object_id_map: dict[int, int] = {}
        attribute_id_map: dict[int, int] = {}
        _copy_business_objects(conn, source_ontology_id, new_ontology_id, object_id_map, attribute_id_map)
        _copy_business_relations(conn, source_ontology_id, new_ontology_id, object_id_map)
        mapping_count = _copy_semantic_mappings(
            conn, source_ontology_id, new_ontology_id, object_id_map, attribute_id_map, source["version"]
        )
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
                   severity, natural_language, status, priority, category,
                   effective_start, effective_end, depends_on
            from business_rule
            where ontology_id = ?
            order by priority desc, code
            """,
            (ontology_id,),
        ).fetchall()
        return {"ontologyId": ontology_id, "items": [dict(row) for row in rows]}


def get_business_rule(platform_db: Path | str, ontology_id: int, rule_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        _require_ontology(conn, ontology_id)
        rule = conn.execute(
            "select id, code, name, rule_type, scope_object_code, expression, severity, natural_language, status, priority, category, effective_start, effective_end, depends_on from business_rule where id = ? and ontology_id = ?",
            (rule_id, ontology_id),
        ).fetchone()
        if rule is None:
            raise ValueError(f"规则不存在: {rule_id}")
        return dict(rule)


def update_business_rule(
    platform_db: Path | str,
    ontology_id: int,
    rule_id: int,
    code: str,
    name: str,
    rule_type: str,
    scope_object_code: str,
    expression: str,
    severity: str,
    natural_language: str,
    actor: str,
    status: str = "published",
    priority: int = 0,
    category: str = "",
    effective_start: str | None = None,
    effective_end: str | None = None,
    depends_on: str | None = None,
) -> dict[str, Any]:
    _validate_rule_write(rule_type, severity, expression)
    with connect(platform_db) as conn:
        ontology = _require_ontology(conn, ontology_id)
        if ontology["status"] == "published":
            raise ValueError("已发布本体的规则不可直接修改，请派生新版本。")
        existing = conn.execute(
            "select id from business_rule where id = ? and ontology_id = ?",
            (rule_id, ontology_id),
        ).fetchone()
        if existing is None:
            raise ValueError(f"规则不存在: {rule_id}")
        scope = conn.execute(
            "select id from business_object where ontology_id = ? and code = ?",
            (ontology_id, scope_object_code),
        ).fetchone()
        if scope is None:
            raise ValueError(f"规则适用业务对象不存在: {scope_object_code}")
        depends = depends_on if depends_on is not None else "[]"
        conn.execute(
            """
            update business_rule
            set code = ?, name = ?, rule_type = ?, scope_object_code = ?,
                expression = ?, severity = ?, natural_language = ?, status = ?,
                priority = ?, category = ?, effective_start = ?, effective_end = ?, depends_on = ?
            where id = ? and ontology_id = ?
            """,
            (
                code,
                name,
                rule_type,
                scope_object_code,
                expression,
                severity,
                natural_language,
                status,
                priority,
                category,
                effective_start,
                effective_end,
                depends,
                rule_id,
                ontology_id,
            ),
        )
        rule = conn.execute("select * from business_rule where id = ?", (rule_id,)).fetchone()
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "update_business_rule",
                "business_rule",
                str(rule_id),
                json.dumps({"code": code, "scope": scope_object_code}, ensure_ascii=False),
            ),
        )
        return dict(rule)


def delete_business_rule(
    platform_db: Path | str, ontology_id: int, rule_id: int, actor: str = "system"
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        ontology = _require_ontology(conn, ontology_id)
        if ontology["status"] == "published":
            raise ValueError("已发布本体的规则不可直接删除，请派生新版本。")
        rule = conn.execute(
            "select id, code from business_rule where id = ? and ontology_id = ?",
            (rule_id, ontology_id),
        ).fetchone()
        if rule is None:
            raise ValueError(f"规则不存在: {rule_id}")
        conn.execute("delete from business_rule where id = ? and ontology_id = ?", (rule_id, ontology_id))
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "delete_business_rule",
                "business_rule",
                str(rule_id),
                json.dumps({"code": rule["code"]}, ensure_ascii=False),
            ),
        )
        return {"deleted": True, "ruleId": rule_id, "code": rule["code"]}


def toggle_business_rule_status(
    platform_db: Path | str, ontology_id: int, rule_id: int, status: str, actor: str = "system"
) -> dict[str, Any]:
    if status not in {"draft", "published", "disabled"}:
        raise ValueError(f"不支持的状态: {status}")
    with connect(platform_db) as conn:
        _require_ontology(conn, ontology_id)
        rule = conn.execute(
            "select id from business_rule where id = ? and ontology_id = ?",
            (rule_id, ontology_id),
        ).fetchone()
        if rule is None:
            raise ValueError(f"规则不存在: {rule_id}")
        conn.execute(
            "update business_rule set status = ? where id = ? and ontology_id = ?",
            (status, rule_id, ontology_id),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "toggle_business_rule_status",
                "business_rule",
                str(rule_id),
                json.dumps({"status": status}, ensure_ascii=False),
            ),
        )
        return {"ruleId": rule_id, "status": status}


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
    priority: int = 0,
    category: str = "",
    effective_start: str | None = None,
    effective_end: str | None = None,
    depends_on: str | None = None,
    overrides: str = "",
) -> dict[str, Any]:
    _validate_rule_write(rule_type, severity, expression)
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
        if overrides:
            _validate_override(conn, ontology_id, code, scope_object_code, overrides)
        depends = depends_on if depends_on is not None else "[]"
        conn.execute(
            """
            insert into business_rule (
                ontology_id, code, name, rule_type, scope_object_code,
                expression, severity, natural_language, status,
                priority, category, effective_start, effective_end, depends_on, overrides
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(ontology_id, code) do update set
                name = excluded.name,
                rule_type = excluded.rule_type,
                scope_object_code = excluded.scope_object_code,
                expression = excluded.expression,
                severity = excluded.severity,
                natural_language = excluded.natural_language,
                status = excluded.status,
                priority = excluded.priority,
                category = excluded.category,
                effective_start = excluded.effective_start,
                effective_end = excluded.effective_end,
                depends_on = excluded.depends_on,
                overrides = excluded.overrides
            """,
            (
                ontology_id,
                code,
                name,
                rule_type,
                scope_object_code,
                expression,
                severity,
                natural_language,
                status,
                priority,
                category,
                effective_start,
                effective_end,
                depends,
                overrides,
            ),
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


def _validate_override(conn: Any, ontology_id: int, code: str, scope_object_code: str, overrides: str) -> None:
    """Check that an override declaration names a rule this object actually inherits.

    Refused up front for two reasons. A typo would otherwise silently supersede
    nothing, leaving the author believing the ancestor's rule is disabled when it is
    still blocking. And a declaration naming a rule outside the ancestry would
    disable a control on a type this object has no relationship to.
    """
    if overrides == code:
        raise ValueError(f"规则不能覆盖自身: {code}")
    target = conn.execute(
        "select scope_object_code from business_rule where ontology_id = ? and code = ?",
        (ontology_id, overrides),
    ).fetchone()
    if target is None:
        raise ValueError(f"被覆盖的规则不存在: {overrides}")
    ancestry = inherited_rule_scopes(conn, ontology_id, scope_object_code)[1:]
    if target["scope_object_code"] not in ancestry:
        raise ValueError(
            f"只能覆盖上级类型的规则。{overrides} 属于 {target['scope_object_code']}，"
            f"不在 {scope_object_code} 的上级链 {'、'.join(ancestry) or '(无)'} 中。"
        )


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
        new_object_id = last_insert_id(conn)
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
            attribute_id_map[attribute["id"]] = last_insert_id(conn)


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
