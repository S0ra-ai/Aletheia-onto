"""Value domain mapping: legacy magic values to semantic states.

Legacy systems encode meaning in short codes -- ``status='A'``, ``level=1``,
``flag='Y'``. Two problems follow from that:

1. Business rules have to be written against the codes, so a rule reads
   ``status == 'A'`` instead of ``status == '生效中'``. The rule is then only
   reviewable by someone who remembers the code table.
2. Answers quote the raw code back at the user, who has to translate it.

A `value_to_state` mapping records "column X value 'A' means 生效中" as a governed
part of the ontology. Rule evaluation then accepts either form, and answers can
render the human-readable name.

Mappings live in `semantic_mapping` as a third mapping_type alongside
`table_to_object` and `column_to_attribute`, so they inherit the existing review
workflow: a generated candidate starts as `pending` and only takes effect once
confirmed. Nothing auto-applies an unreviewed guess to a compliance verdict.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .database import connect, last_insert_id

MAPPING_TYPE = "value_to_state"

# `source_ref` is "table.column", `target_ref` is the semantic state name, and
# the raw value lives in `evidence` as JSON so the pair stays queryable without
# adding columns to semantic_mapping.
EVIDENCE_VALUE_KEY = "sourceValue"


def _source_ref(table_name: str, column_name: str) -> str:
    return f"{table_name}.{column_name}"


def register_value_mapping(
    platform_db: Path | str,
    ontology_id: int,
    table_name: str,
    column_name: str,
    source_value: str,
    state_name: str,
    *,
    confidence: float = 1.0,
    status: str = "confirmed",
    actor: str = "system",
) -> dict[str, Any]:
    """Record that one raw column value means one semantic state.

    Defaults to `confirmed` because an explicit call is a deliberate act by an
    operator; generated candidates use `pending` (see
    `suggest_value_mappings_from_enums`).
    """
    if not str(source_value).strip():
        raise ValueError("原始值不能为空")
    if not state_name.strip():
        raise ValueError("语义状态名不能为空")

    source_ref = _source_ref(table_name, column_name)
    evidence = json.dumps({EVIDENCE_VALUE_KEY: str(source_value)}, ensure_ascii=False)
    with connect(platform_db) as conn:
        ontology = conn.execute("select status from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")
        if ontology["status"] == "published":
            raise ValueError("已发布本体不可修改值域映射，请派生新版本。")

        existing = conn.execute(
            """
            select id from semantic_mapping
            where ontology_id = ? and mapping_type = ? and source_ref = ? and evidence = ?
            """,
            (ontology_id, MAPPING_TYPE, source_ref, evidence),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "update semantic_mapping set target_ref = ?, confidence = ?, status = ?, reviewer = ? where id = ?",
                (state_name, confidence, status, actor, existing["id"]),
            )
            mapping_id = int(existing["id"])
        else:
            conn.execute(
                """
                insert into semantic_mapping
                    (ontology_id, mapping_type, source_ref, target_ref, confidence, status, evidence, reviewer)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ontology_id,
                    MAPPING_TYPE,
                    source_ref,
                    state_name,
                    confidence,
                    status,
                    evidence,
                    actor,
                ),
            )
            mapping_id = last_insert_id(conn)
    return {
        "id": mapping_id,
        "ontologyId": ontology_id,
        "sourceRef": source_ref,
        "sourceValue": str(source_value),
        "state": state_name,
        "status": status,
    }


def load_value_mappings_in_connection(
    conn: Any,
    ontology_id: int,
    *,
    include_pending: bool = False,
) -> dict[str, dict[str, str]]:
    """Load mappings using a connection the caller already holds.

    Separate from `load_value_mappings` because the rule runtime is built inside
    an open transaction; opening a second connection there would both waste a
    handle and read outside the caller's transaction.
    """
    statuses = ("confirmed", "pending") if include_pending else ("confirmed",)
    placeholders = ", ".join("?" for _ in statuses)
    rows = conn.execute(
        f"""
        select source_ref, target_ref, evidence from semantic_mapping
        where ontology_id = ? and mapping_type = ? and status in ({placeholders})
        """,
        (ontology_id, MAPPING_TYPE, *statuses),
    ).fetchall()
    mappings: dict[str, dict[str, str]] = {}
    for row in rows:
        try:
            raw_value = json.loads(row["evidence"]).get(EVIDENCE_VALUE_KEY)
        except (ValueError, AttributeError):
            continue
        if raw_value is None:
            continue
        mappings.setdefault(row["source_ref"], {})[str(raw_value)] = row["target_ref"]
    return mappings


def load_value_mappings(
    platform_db: Path | str,
    ontology_id: int,
    *,
    include_pending: bool = False,
) -> dict[str, dict[str, str]]:
    """Return {"table.column": {raw value: state name}}.

    Only confirmed mappings apply by default: an unreviewed guess must not change
    what a compliance rule evaluates to.
    """
    with connect(platform_db) as conn:
        return load_value_mappings_in_connection(conn, ontology_id, include_pending=include_pending)


def state_for(mappings: dict[str, dict[str, str]], table_name: str, column_name: str, value: Any) -> str | None:
    """The semantic state for a raw value, or None when unmapped."""
    if value is None:
        return None
    return mappings.get(_source_ref(table_name, column_name), {}).get(str(value))


def suggest_value_mappings_from_enums(
    platform_db: Path | str,
    ontology_id: int,
    data_source_id: int,
    actor: str = "system",
) -> dict[str, Any]:
    """Propose value mappings for columns the scan flagged as enumerations.

    Candidates are written as `pending` with the raw value as a placeholder state
    name: the platform has no way to know that 'A' means 生效中, so a human must
    supply the meaning. What this saves is the enumeration of which values exist.
    """
    with connect(platform_db) as conn:
        columns = conn.execute(
            """
            select st.table_name, sc.column_name, sc.sample_values
            from source_column sc
            join source_table st on st.id = sc.source_table_id
            where st.data_source_id = ? and sc.enum_candidate = 1
            order by st.table_name, sc.ordinal
            """,
            (data_source_id,),
        ).fetchall()

    created: list[dict[str, Any]] = []
    for column in columns:
        try:
            samples = json.loads(column["sample_values"] or "[]")
        except ValueError:
            continue
        distinct = []
        for sample in samples:
            text = "" if sample is None else str(sample)
            if text and text not in distinct:
                distinct.append(text)
        for value in distinct:
            created.append(
                register_value_mapping(
                    platform_db,
                    ontology_id,
                    column["table_name"],
                    column["column_name"],
                    value,
                    value,
                    confidence=0.5,
                    status="pending",
                    actor=actor,
                )
            )
    return {
        "ontologyId": ontology_id,
        "dataSourceId": data_source_id,
        "candidates": created,
        "count": len(created),
        "note": "候选值域映射为 pending 状态，需人工填写语义状态名并确认后才会生效。",
    }
