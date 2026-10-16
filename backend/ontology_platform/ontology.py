from __future__ import annotations

import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence
from urllib.parse import quote

from .config import MAPPING_CONFIDENCE, SEMANTIC_ASSET_NAMING
from .context import PlatformDb
from .database import connect, last_insert_id
from .derived_attributes import Quantity, UnitError, get_unit
from .events import EVENT_CATEGORY_LABELS, EVENT_TABLE, EVENT_TYPE_TABLE, event_tables_exist
from .industry_blueprints import IndustryBlueprint, get_industry_blueprint, infer_industry_blueprint
from .metadata import delete_referencing_rows
from .relations import (
    AGGREGATION,
    ASSOCIATION,
    CARDINALITY_LABELS,
    COMPOSITION,
    KIND_LABELS,
    RelationSemantics,
    classify_foreign_key,
    detect_junction,
    junction_semantics,
    shapes_for_table,
)
from .rule_sandbox import MappedValue, validate_rule_expression
from .type_hierarchy import ancestors_of
from .vocabulary import blueprint_attribute_labels, blueprint_object_labels

logger = logging.getLogger(__name__)


def generate_ontology_draft(
    platform_db: PlatformDb,
    data_source_id: int,
    name: str | None = None,
    domain: str | None = None,
    blueprint_id: str | None = None,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        data_source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if data_source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        tables = conn.execute(
            "select * from source_table where data_source_id = ? order by table_name", (data_source_id,)
        ).fetchall()
        table_names = [table["table_name"] for table in tables]
        blueprint = (
            get_industry_blueprint(blueprint_id, domain or data_source["domain"], platform_db)
            if blueprint_id
            else infer_industry_blueprint(table_names, domain or data_source["domain"], platform_db)
        )
        resolved_domain = domain or data_source["domain"] or blueprint.domain
        resolved_name = name or f"{resolved_domain}本体"
        ontology_id, discarded = _create_ontology(conn, data_source_id, resolved_name, resolved_domain)
        object_ids: dict[int, int] = {}
        # Labels contributed by every registered blueprint, including user
        # imported ones. This replaces a built-in table of industry terms, so a
        # new domain gets good names by importing a blueprint rather than by
        # changing platform code.
        lexicon = _build_lexicon(platform_db)

        for table in tables:
            object_id = _create_business_object(conn, ontology_id, table, blueprint, lexicon)
            object_ids[table["id"]] = object_id
            _create_table_mapping(conn, ontology_id, table, object_id, blueprint)
            columns = conn.execute(
                "select * from source_column where source_table_id = ? order by ordinal", (table["id"],)
            ).fetchall()
            for column in columns:
                attribute_id = _create_attribute(conn, object_id, column, blueprint, lexicon)
                _create_column_mapping(conn, ontology_id, table, column, object_id, attribute_id, blueprint, lexicon)

        _create_relations(conn, ontology_id, data_source_id, tables)

        _create_generic_rules(conn, ontology_id)
        _create_blueprint_rules(conn, ontology_id, blueprint)
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "system",
                "generate_ontology_draft",
                "ontology",
                str(ontology_id),
                json.dumps(
                    {"dataSourceId": data_source_id, "blueprintId": blueprint.id, "blueprintName": blueprint.name},
                    ensure_ascii=False,
                ),
            ),
        )
        summary = summarize_ontology(conn, ontology_id)
        summary["blueprint"] = blueprint.to_dict()
        # What this regeneration removed, so a caller can say it. Empty when the draft was
        # created rather than rebuilt, which is the common case on a fresh source.
        summary["discarded"] = discarded
        if discarded:
            summary["discardedSummary"] = describe_discarded(discarded)
        return summary


def resolve_ontology_for_object(platform_db: PlatformDb, object_code: str) -> int:
    """Find the newest ontology that models the given business object.

    Callers used to default to ontology id 1, which silently pointed at whatever
    was created first and broke as soon as a second ontology existed.
    """
    with connect(platform_db) as conn:
        row = conn.execute(
            """
            select o.id
            from ontology o
            join business_object bo on bo.ontology_id = o.id
            where bo.code = ?
            order by case o.status when 'published' then 0 else 1 end, o.id desc
            limit 1
            """,
            (object_code,),
        ).fetchone()
        if row is None:
            raise ValueError(f"没有任何本体包含业务对象: {object_code}")
        return int(row["id"])


# The semantic runtime -- cross-source resolution, temporal override, aggregates, units,
# value mappings and derived attributes -- is built by `semantic_kernel`, which imports
# this module. Binding it rather than importing it keeps the dependency one-directional,
# the same arrangement `derived_attributes.bind_sandbox` uses and for the same reason.
#
# It is not a plugin point. An explanation built by a different runtime would show values
# other than the ones the rules saw, which is exactly the divergence this arrangement
# exists to prevent.
_runtime_builder: Optional[Callable[..., Any]] = None


def bind_runtime_builder(build: Callable[..., Any]) -> None:
    """Wire in the runtime builder. Called once by the kernel at import time."""
    global _runtime_builder
    _runtime_builder = build


def explain_instance(
    platform_db: PlatformDb,
    ontology_id: int,
    object_code: str,
    instance_id: str,
    *,
    as_of: Any = None,
) -> dict[str, Any]:
    """What this instance is, where each value came from, and how it got that way.

    The values shown are the ones a rule would evaluate against, not the raw stored
    cells. That distinction is the whole point of an explanation: the platform
    transforms the record before any verdict is produced -- cross-source fields are
    merged in, recorded history overrides live values for an as-of assessment,
    declared units wrap magnitudes, value mappings let `status == '生效中'` mean the
    same as `status == 'A'`, and derived attributes are computed from all of it. An
    explanation built from the stored row would show numbers the rules never saw, and
    a reader comparing it against a verdict would find a discrepancy that is not there.

    This function used to do exactly that, and along the way it dropped two things
    outright: the inner join to `source_column` silently excluded every derived
    attribute (their rows have no source column), and neither `unit` nor
    `derived_expression` was selected at all. A contract measured in 万元 was explained
    as the bare number 1200000, and a derived attribute declared for the object was
    simply absent from its own explanation.

    `as_of` explains a verdict about a past instant rather than the present one.
    """
    if _runtime_builder is None:  # pragma: no cover - the kernel binds on import
        # Reachable only when a caller imports this module without the kernel. The message
        # names the import that fixes it: "not bound" alone leaves the reader with nothing
        # to act on, which is the failure this codebase keeps removing elsewhere.
        raise RuntimeError(
            "语义运行时尚未绑定，无法解释实例：解释需要内核改写的运行上下文。"
            "请先 `import ontology_platform.semantic_kernel`（应用经由 api 启动时已自动绑定）。"
        )

    with connect(platform_db) as platform:
        runtime = _runtime_builder(platform, ontology_id, object_code, instance_id, as_of=as_of)
        attributes = platform.execute(
            """
            select ba.code, ba.name, ba.unit, ba.derived_expression, sc.column_name
            from business_attribute ba
            left join source_column sc on sc.id = ba.source_column_id
            where ba.object_id = ?
            order by ba.id
            """,
            (runtime_business_object_id(platform, ontology_id, object_code),),
        ).fetchall()
        values = [_explained_attribute(attribute, runtime) for attribute in attributes]
        # Cross-object aggregates are values a rule reads by name, and they belong to no
        # attribute row -- so unlike a derived attribute they have nowhere else to appear.
        # A verdict citing `invoice_total` used to cite a name the explanation did not
        # mention at all, which is the one thing an explanation cannot do. Kept apart from
        # `attributes` because an aggregate is a query over other rows, not a value of this
        # one, and its row count and truncation flag have no attribute to hang on.
        aggregates = [
            {
                "name": name,
                "definition": result.get("definition", ""),
                "value": result.get("value"),
                "rowCount": result.get("rowCount", 0),
                "truncated": bool(result.get("truncated")),
                "error": result.get("error", ""),
            }
            for name, result in sorted(runtime.aggregates.items())
        ]
        # The event history is what turns "what is true" into "how it got that way".
        # Read on the caller's connection and capped, since an explanation must not
        # scale with total event volume.
        timeline = _recent_events(platform, ontology_id, object_code, instance_id)
        # Declared ancestry, so an explanation can say which type's rules apply.
        ancestors = ancestors_of(platform, ontology_id, object_code)
        return {
            "ontology": {
                "id": runtime.ontology_id,
                "name": runtime.object_name,
                "version": runtime.ontology_version,
            },
            "object": {"code": runtime.object_code, "name": runtime.object_name},
            "objectCode": runtime.object_code,
            "instanceId": instance_id,
            "source": {
                "table": runtime.source_table,
                "primaryKey": runtime.primary_key,
                "instanceId": instance_id,
            },
            "asOf": runtime.as_of,
            "attributes": values,
            "aggregates": aggregates,
            "ancestors": ancestors,
            "timeline": timeline,
            "explanation": _explanation_sentence(runtime, values, aggregates),
        }


def runtime_business_object_id(platform: sqlite3.Connection, ontology_id: int, object_code: str) -> int:
    row = platform.execute(
        "select id from business_object where ontology_id = ? and code = ?", (ontology_id, object_code)
    ).fetchone()
    if row is None:
        raise ValueError(f"业务对象不存在: {object_code}")
    return int(row["id"])


# `runtime` is typed loosely on purpose: naming the kernel's SemanticRuntime here would be a
# module-level import of `semantic_kernel`, which imports this module.
def _explained_attribute(attribute: Any, runtime: Any) -> dict[str, Any]:
    """One declared attribute, with the value the rules saw and where it came from."""
    code = attribute["code"]
    column = attribute["column_name"] or ""
    expression = attribute["derived_expression"] or ""
    stored = runtime.record.get(column) if column else None

    entry: dict[str, Any] = {
        "attributeCode": code,
        "attributeName": attribute["name"],
        "sourceColumn": column,
        "unit": attribute["unit"] or "",
        "unitName": _unit_name(attribute["unit"] or ""),
        "derived": bool(expression),
        "derivedExpression": expression,
        "value": stored,
    }

    if expression:
        derived = runtime.derived.get(code) or {}
        entry["value"] = derived.get("value")
        # A derived attribute that could not be computed is a fact about the model, not a
        # missing value: a rule referencing it fails closed, and the reader needs to see
        # why rather than an empty cell.
        entry["error"] = derived.get("error", "")
        return entry

    # Keyed by column, because that is how the stored context is built: units and value
    # mappings are applied to the record's own keys.
    effective = runtime.context.get(column, stored)
    entry["value"] = effective
    if isinstance(effective, MappedValue):
        # The raw code and the business state it maps to. Both, because a rule may be
        # written in either and a reader needs to see that `status == '生效中'` was true.
        entry["stateName"] = effective.state
    elif isinstance(effective, Quantity) and attribute["unit"]:
        entry["unitName"] = _unit_name(effective.unit)
    # Recorded history overrode the live row for this attribute. Stated because the reader
    # of an as-of explanation is looking at a past moment and needs to know which fields
    # came from it -- "what it says now" is deliberately not included: the live value was
    # replaced on the record before this point, and re-reading it here would be a second
    # query answering a question this endpoint is not being asked.
    if runtime.temporal_values and column in runtime.temporal_values:
        entry["fromHistory"] = True
    return entry


def _unit_name(code: str) -> str:
    if not code:
        return ""
    try:
        return str(get_unit(code).name)
    except Exception:  # pragma: no cover - a unit that vanished from the registry
        return code


def _explanation_sentence(runtime: Any, values: list[dict[str, Any]], aggregates: list[dict[str, Any]]) -> str:
    parts = [f"{runtime.object_name}实例 {runtime.instance_id} 已映射到传统表 {runtime.source_table}。"]
    if runtime.as_of:
        parts.append(f"本次解释针对 {runtime.as_of} 这一刻，历史覆盖的字段以当时取值为准。")
    derived = [item["attributeCode"] for item in values if item["derived"]]
    if derived:
        parts.append(f"其中 {len(derived)} 个属性由表达式算出而非直接读取：{'、'.join(derived)}。")
    united = [item["attributeCode"] for item in values if item["unit"] and not item["derived"]]
    if united:
        parts.append(f"{len(united)} 个属性带声明单位，比较时会先换算。")
    if aggregates:
        named = "、".join(item["name"] for item in aggregates)
        parts.append(f"另有 {len(aggregates)} 个跨对象聚合值可供规则引用：{named}。")
        # A truncated aggregate is a partial answer, and a rule that compared it reached a
        # verdict on partial data. That has to be said here rather than left in a field.
        if any(item["truncated"] for item in aggregates):
            parts.append("其中部分聚合已达到取数上限，结果为部分数据。")
    return "".join(parts)


# How many events an explanation carries. Small on purpose: an explanation is read
# interactively, and the full history is available from the timeline endpoint.
EXPLANATION_EVENT_LIMIT = 20


def _recent_events(
    platform: sqlite3.Connection, ontology_id: int, object_code: str, instance_id: str
) -> list[dict[str, Any]]:
    """The instance's most recent events, newest first.

    A missing event table is treated as "no history": the schema is created at
    startup, but an explanation must still work on a database that predates it.

    Probed via the catalog rather than by catching the error: on PostgreSQL a failed
    statement aborts the transaction, so every later command in the same explanation
    would fail (ADR-0004).
    """
    if not event_tables_exist(platform):
        return []
    rows = platform.execute(
        f"""
        select be.event_code, be.category, be.actor, be.occurred_at, bet.name as event_name
        from {EVENT_TABLE} be
        left join {EVENT_TYPE_TABLE} bet
            on bet.ontology_id = be.ontology_id
           and bet.object_code = be.object_code
           and bet.code = be.event_code
        where be.ontology_id = ? and be.object_code = ? and be.instance_id = ?
        order by be.occurred_at desc, be.id desc
        """,
        (ontology_id, object_code, str(instance_id)),
    ).fetchall()
    return [
        {
            "eventCode": row["event_code"],
            "eventName": row["event_name"] or row["event_code"],
            "category": row["category"],
            "categoryLabel": EVENT_CATEGORY_LABELS.get(row["category"], row["category"]),
            "actor": row["actor"],
            "occurredAt": str(row["occurred_at"]),
        }
        for row in rows[:EXPLANATION_EVENT_LIMIT]
    ]


def list_ontologies(platform_db: PlatformDb) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select o.id, o.name, o.domain, o.version, o.status, o.published_at, o.created_at,
                   (select count(*) from business_object bo where bo.ontology_id = o.id) as object_count
            from ontology o
            order by o.id
            """
        ).fetchall()
        summaries = []
        for row in rows:
            summary = _ontology_summary_row(row)
            # Callers need to distinguish a modelled ontology from an empty one
            # without fetching each ontology's detail.
            count = int(row["object_count"] or 0)
            summary["objectCount"] = count
            summary["object_count"] = count
            summaries.append(summary)
        return summaries


def summarize_ontology(conn: sqlite3.Connection, ontology_id: int) -> dict[str, Any]:
    ontology = conn.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
    if ontology is None:
        raise ValueError(f"本体不存在: {ontology_id}")
    objects = conn.execute(
        """
        select bo.id, bo.ontology_id, bo.code, bo.name, bo.description, st.table_name
        from business_object bo
        left join source_table st on st.id = bo.source_table_id
        where bo.ontology_id = ?
        order by bo.code
        """,
        (ontology_id,),
    ).fetchall()
    attributes = conn.execute(
        """
        select ba.id, bo.id as object_id, ba.code, ba.name, ba.data_type,
               ba.required, sc.column_name, bo.code as object_code,
               ba.derived_expression, ba.unit
        from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        left join source_column sc on sc.id = ba.source_column_id
        where bo.ontology_id = ?
        order by bo.code, ba.id
        """,
        (ontology_id,),
    ).fetchall()
    relations = conn.execute(
        """
        select br.id, br.code, br.name, br.relation_type, fk.column_name as source_foreign_key,
               br.cardinality, br.relation_kind, br.optional, br.inference_reason,
               br.junction_table, br.junction_source_column, br.junction_target_column,
               so.id as source_object_id, tobj.id as target_object_id,
               so.code as source_code, tobj.code as target_code
        from business_relation br
        join business_object so on so.id = br.source_object_id
        join business_object tobj on tobj.id = br.target_object_id
        left join source_foreign_key fk on fk.id = br.source_foreign_key_id
        where br.ontology_id = ?
        order by br.id
        """,
        (ontology_id,),
    ).fetchall()
    mappings = conn.execute(
        """
        select id, ontology_id, mapping_type, source_ref, target_ref,
               confidence, status, evidence, reviewer, reviewed_at, created_at
        from semantic_mapping
        where ontology_id = ?
        order by id
        """,
        (ontology_id,),
    ).fetchall()
    rules = conn.execute(
        """
        select id, ontology_id, code, name, rule_type, scope_object_code,
               expression, severity, natural_language, status
        from business_rule
        where ontology_id = ?
        order by code
        """,
        (ontology_id,),
    ).fetchall()
    return {
        **_ontology_summary_row(ontology),
        "ontology": _ontology_summary_row(ontology),
        "objects": [_business_object_row(row) for row in objects],
        "attributes": [_business_attribute_row(row) for row in attributes],
        "relations": [_business_relation_row(row) for row in relations],
        "mappings": [semantic_mapping_row(row, mapping_target_codes(conn, ontology_id)) for row in mappings],
        "rules": [business_rule_row(row) for row in rules],
    }


def export_ontology_asset(platform_db: PlatformDb, ontology_id: int, export_format: str = "jsonld") -> dict[str, str]:
    export_format = export_format.lower()
    if export_format not in {"jsonld", "turtle", "ttl"}:
        raise ValueError("仅支持 jsonld 或 turtle 导出格式")
    with connect(platform_db) as conn:
        detail = summarize_ontology(conn, ontology_id)
    if export_format == "jsonld":
        content = _export_jsonld(detail)
        extension = "jsonld"
        media_type = "application/ld+json"
    else:
        content = _export_turtle(detail)
        extension = "ttl"
        media_type = "text/turtle"
    filename = f"ontology-{ontology_id}-v{detail['version']}.{extension}"
    return {"content": content, "mediaType": media_type, "filename": filename}


def _export_jsonld(detail: dict[str, Any]) -> str:
    ontology = detail["ontology"]
    base = _ontology_base_uri(ontology)
    object_by_id = {item["id"]: item for item in detail["objects"]}
    graph: list[dict[str, Any]] = [
        {
            "@id": base.rstrip("/"),
            "@type": "ont:Ontology",
            "name": ontology["name"],
            "domain": ontology["domain"],
            "version": ontology["version"],
            "status": ontology["status"],
        }
    ]

    for item in detail["objects"]:
        graph.append(
            {
                "@id": f"{base}object/{_uri_part(item['code'])}",
                "@type": "ont:BusinessObject",
                "code": item["code"],
                "name": item["name"],
                "description": item["description"],
                "sourceTable": item["sourceTable"],
                "definedBy": {"@id": base.rstrip("/")},
            }
        )
    for item in detail["attributes"]:
        object_item = object_by_id.get(item["objectId"])
        graph.append(
            {
                "@id": f"{base}object/{_uri_part(item['objectCode'])}/attribute/{_uri_part(item['code'])}",
                "@type": "ont:BusinessAttribute",
                "code": item["code"],
                "name": item["name"],
                "dataType": item["dataType"],
                "required": item["required"],
                # A consumer cannot interpret a number without its unit, nor
                # reproduce a derived value without its expression.
                "unit": item["unit"],
                "derivedExpression": item["derivedExpression"],
                "sourceColumn": item["sourceColumn"],
                "belongsTo": {"@id": f"{base}object/{_uri_part(object_item['code'])}"} if object_item else None,
            }
        )
    for item in detail["relations"]:
        graph.append(
            {
                "@id": f"{base}relation/{_uri_part(item['code'])}",
                "@type": "ont:BusinessRelation",
                "code": item["code"],
                "name": item["name"],
                "relationType": item["relationType"],
                # Cardinality and kind are what make an exported relation usable by
                # a downstream consumer; without them every link looks alike.
                "cardinality": item["cardinality"],
                "relationKind": item["relationKind"],
                "optional": item["optional"],
                "junctionTable": item["junctionTable"],
                "sourceObject": {"@id": f"{base}object/{_uri_part(item['sourceCode'])}"},
                "targetObject": {"@id": f"{base}object/{_uri_part(item['targetCode'])}"},
                "sourceForeignKey": item["sourceForeignKey"],
            }
        )
    for item in detail["rules"]:
        graph.append(
            {
                "@id": f"{base}rule/{_uri_part(item['code'])}",
                "@type": "ont:BusinessRule",
                "code": item["code"],
                "name": item["name"],
                "ruleType": item["ruleType"],
                "scopeObject": {"@id": f"{base}object/{_uri_part(item['scopeObjectCode'])}"},
                "expression": item["expression"],
                "severity": item["severity"],
                "naturalLanguage": item["naturalLanguage"],
                "status": item["status"],
            }
        )
    for item in detail["mappings"]:
        graph.append(
            {
                "@id": f"{base}mapping/{item['id']}",
                "@type": "ont:SemanticMapping",
                "mappingType": item["mappingType"],
                "sourceRef": item["sourceRef"],
                "targetRef": item["targetRef"],
                "confidence": item["confidence"],
                "status": item["status"],
                "evidence": item["evidence"],
            }
        )
    document = {
        "@context": {
            "ont": SEMANTIC_ASSET_NAMING.vocabulary_base,
            "name": "ont:name",
            "code": "ont:code",
            "domain": "ont:domain",
            "version": "ont:version",
            "status": "ont:status",
            "description": "ont:description",
            "sourceTable": "ont:sourceTable",
            "sourceColumn": "ont:sourceColumn",
            "dataType": "ont:dataType",
            "required": "ont:required",
            # Without a context entry a term is dropped by a strict JSON-LD
            # processor, so every emitted key needs one.
            "unit": "ont:unit",
            "derivedExpression": "ont:derivedExpression",
            "relationType": "ont:relationType",
            "cardinality": "ont:cardinality",
            "relationKind": "ont:relationKind",
            "optional": "ont:optional",
            "junctionTable": "ont:junctionTable",
            "sourceForeignKey": "ont:sourceForeignKey",
            "ruleType": "ont:ruleType",
            "expression": "ont:expression",
            "severity": "ont:severity",
            "naturalLanguage": "ont:naturalLanguage",
            "mappingType": "ont:mappingType",
            "sourceRef": "ont:sourceRef",
            "targetRef": "ont:targetRef",
            "confidence": "ont:confidence",
            "evidence": "ont:evidence",
            "definedBy": {"@id": "ont:definedBy", "@type": "@id"},
            "belongsTo": {"@id": "ont:belongsTo", "@type": "@id"},
            "sourceObject": {"@id": "ont:sourceObject", "@type": "@id"},
            "targetObject": {"@id": "ont:targetObject", "@type": "@id"},
            "scopeObject": {"@id": "ont:scopeObject", "@type": "@id"},
        },
        "@graph": [_drop_none(node) for node in graph],
    }
    return json.dumps(document, ensure_ascii=False, indent=2)


def _export_turtle(detail: dict[str, Any]) -> str:
    ontology = detail["ontology"]
    base = _ontology_base_uri(ontology)
    lines = [
        f"@prefix ont: <{SEMANTIC_ASSET_NAMING.vocabulary_base}> .",
        f"@prefix bp: <{base}> .",
        "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .",
        "",
        "bp: a ont:Ontology ;",
        f"  ont:name {_ttl_literal(ontology['name'])} ;",
        f"  ont:domain {_ttl_literal(ontology['domain'])} ;",
        f"  ont:version {_ttl_literal(ontology['version'])} ;",
        f"  ont:status {_ttl_literal(ontology['status'])} .",
        "",
    ]
    for item in detail["objects"]:
        lines.extend(
            [
                f"{_ttl_iri(base, 'object', item['code'])} a ont:BusinessObject ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:description {_ttl_literal(item['description'])} ;",
                f"  ont:sourceTable {_ttl_literal(item['sourceTable'])} ;",
                "  ont:definedBy bp: .",
                "",
            ]
        )
    for item in detail["attributes"]:
        lines.extend(
            [
                f"{_ttl_iri(base, 'object', item['objectCode'], 'attribute', item['code'])} a ont:BusinessAttribute ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:dataType {_ttl_literal(item['dataType'])} ;",
                f"  ont:required {_ttl_bool(item['required'])} ;",
                f"  ont:unit {_ttl_literal(item['unit'])} ;",
                f"  ont:derivedExpression {_ttl_literal(item['derivedExpression'])} ;",
                f"  ont:sourceColumn {_ttl_literal(item['sourceColumn'])} ;",
                f"  ont:belongsTo {_ttl_iri(base, 'object', item['objectCode'])} .",
                "",
            ]
        )
    for item in detail["relations"]:
        lines.extend(
            [
                f"{_ttl_iri(base, 'relation', item['code'])} a ont:BusinessRelation ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:relationType {_ttl_literal(item['relationType'])} ;",
                f"  ont:cardinality {_ttl_literal(item['cardinality'])} ;",
                f"  ont:relationKind {_ttl_literal(item['relationKind'])} ;",
                f"  ont:optional {'true' if item['optional'] else 'false'} ;",
                f"  ont:sourceObject {_ttl_iri(base, 'object', item['sourceCode'])} ;",
                f"  ont:targetObject {_ttl_iri(base, 'object', item['targetCode'])} ;",
                f"  ont:sourceForeignKey {_ttl_literal(item['sourceForeignKey'])} .",
                "",
            ]
        )
    for item in detail["rules"]:
        lines.extend(
            [
                f"{_ttl_iri(base, 'rule', item['code'])} a ont:BusinessRule ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:ruleType {_ttl_literal(item['ruleType'])} ;",
                f"  ont:scopeObject {_ttl_iri(base, 'object', item['scopeObjectCode'])} ;",
                f"  ont:expression {_ttl_literal(item['expression'])} ;",
                f"  ont:severity {_ttl_literal(item['severity'])} ;",
                f"  ont:naturalLanguage {_ttl_literal(item['naturalLanguage'])} ;",
                f"  ont:status {_ttl_literal(item['status'])} .",
                "",
            ]
        )
    for item in detail["mappings"]:
        lines.extend(
            [
                f"{_ttl_iri(base, 'mapping', str(item['id']))} a ont:SemanticMapping ;",
                f"  ont:mappingType {_ttl_literal(item['mappingType'])} ;",
                f"  ont:sourceRef {_ttl_literal(item['sourceRef'])} ;",
                f"  ont:targetRef {_ttl_literal(item['targetRef'])} ;",
                f"  ont:confidence {item['confidence']} ;",
                f"  ont:status {_ttl_literal(item['status'])} ;",
                f"  ont:evidence {_ttl_literal(item['evidence'])} .",
                "",
            ]
        )
    return "\n".join(lines)


def _draft_for_source(conn: sqlite3.Connection, data_source_id: int) -> sqlite3.Row | None:
    """The newest draft this source was used to build, if there is one.

    A draft's identity is the *source it was derived from*, not its name. It used to be the
    name -- which defaults to `<domain>本体` -- so two data sources in the same domain were the
    same ontology row, and generating a draft for the second one *rebuilt* the first one,
    clearing the rules, mappings and workflows somebody had attached to it. The 演示中心 button
    reached the same path on a second click: it re-runs the demo, and the demo silently took
    its own draft apart. Only the draft-generation endpoint warns, and its warning says the
    clearing applies 「若该数据源已有草案」 -- which is false in exactly this case.
    """
    return conn.execute(
        """select o.id, o.name, o.status
           from ontology o
           join business_object bo on bo.ontology_id = o.id
           join source_table st on st.id = bo.source_table_id
           where st.data_source_id = ? and o.version = '0.1.0'
           order by o.id desc limit 1""",
        (data_source_id,),
    ).fetchone()


def _create_ontology(
    conn: sqlite3.Connection, data_source_id: int, name: str, domain: str
) -> tuple[int, dict[str, int]]:
    """The ontology row to build into, and what regenerating it destroyed.

    The second half is returned so the caller can *say* what it removed. Regenerating a
    draft is destructive by design -- it rebuilds the model from the current scan -- but a
    caller that reports only 「本体草案生成成功」 is announcing a rebuild while a user's
    hand-written rules and workflows disappear behind it.
    """
    own = _draft_for_source(conn, data_source_id)
    if own is None:
        # A name that belongs to another source's *draft* must not be taken over, and must not
        # collide either: this source gets its own row under a name that says which source it
        # came from. A published name is a different matter -- that is the caller's error.
        taken = conn.execute(
            "select id, status from ontology where name = ? and version = '0.1.0'", (name,)
        ).fetchone()
        if taken is not None and taken["status"] == "published":
            raise ValueError(f"本体版本已发布，不能重新生成草案: {name} 0.1.0。请派生新版本。")
        name = _distinct_draft_name(conn, name, data_source_id)
    existing = own
    if existing:
        if existing["status"] == "published":
            raise ValueError(f"本体版本已发布，不能重新生成草案: {name} 0.1.0。请派生新版本。")
        ontology_id = int(existing["id"])
        discarded = _count_attached_rows(conn, ontology_id)
        # Through the catalog, to any depth. A hand-written list of tables was correct when it
        # was written and stopped being correct the first time a feature module added one:
        # regenerating a draft on a source that had a workflow, an event or a knowledge
        # document failed with `FOREIGN KEY constraint failed`, which reached a user as a 500
        # from `POST /ontologies/draft`.
        # This is the only path that discards a draft. A scan deliberately does not: it
        # refreshes source metadata, and clearing the model is what *this* does, when asked.
        delete_referencing_rows(conn, "business_object", _object_ids(conn, ontology_id))
        conn.execute("delete from business_object where ontology_id = ?", (ontology_id,))
        delete_referencing_rows(conn, "ontology", [ontology_id])
        return ontology_id, discarded

    conn.execute(
        "insert into ontology (name, domain, version, status) values (?, ?, ?, ?)",
        (name, domain, "0.1.0", "draft"),
    )
    return last_insert_id(conn), {}


def _distinct_draft_name(conn: sqlite3.Connection, name: str, data_source_id: int) -> str:
    """`name`, or a variant of it that no other ontology is using.

    Two sources in the same domain both default to `<domain>本体`; the second one is not the
    first one, and saying so in the name is cheaper than explaining later why one model's
    rules disappeared when the other was drafted.
    """
    candidate = name
    suffix = 2
    while conn.execute(
        "select 1 from ontology where name = ? and version = '0.1.0'", (candidate,)
    ).fetchone():
        candidate = f"{name}（{suffix}）"
        suffix += 1
    return candidate


# What a regeneration takes with it, and what to call each in a message to the person who
# asked for it. Counted before the deletes rather than inferred from them: `business_rule` is
# cleared by a catalog-driven sweep that returns table names, and "3 tables" is not an answer
# to "did I lose my rules".
_ATTACHED = (
    ("business_rule", "rules", "条规则"),
    ("semantic_mapping", "mappings", "条映射"),
    ("business_relation", "relations", "条关系"),
    ("workflow_definition", "workflows", "个工作流"),
    ("knowledge_document", "documents", "份知识文档"),
)


def _count_attached_rows(conn: sqlite3.Connection, ontology_id: int) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table, key, _label in _ATTACHED:
        try:
            total = conn.execute(f"select count(*) from {table} where ontology_id = ?", (ontology_id,)).fetchone()[0]
        except sqlite3.OperationalError:
            # An optional feature bundle the deployment never installed. Its absence is not a
            # reason to fail the regeneration, and it is not a count of zero either.
            continue
        if total:
            counts[key] = int(total)
    return counts


def describe_discarded(counts: dict[str, int]) -> str:
    """`{"rules": 3, "workflows": 1}` as 「3 条规则、1 个工作流」, for a message to a person."""
    labels = {key: label for _table, key, label in _ATTACHED}
    return "、".join(f"{total} {labels.get(key, key)}" for key, total in counts.items())


def _object_ids(conn: sqlite3.Connection, ontology_id: int) -> list[int]:
    return [
        int(row["id"])
        for row in conn.execute("select id from business_object where ontology_id = ?", (ontology_id,)).fetchall()
    ]


@dataclass(frozen=True)
class DraftLexicon:
    """Naming hints available while generating a draft.

    Sourced from registered industry blueprints so the platform carries no
    built-in industry vocabulary of its own.
    """

    object_labels: dict[str, str]
    attribute_labels: dict[str, str]

    def object_label(self, *candidates: str) -> str:
        for candidate in candidates:
            if candidate and candidate in self.object_labels:
                return self.object_labels[candidate]
        return ""

    def attribute_label(self, column_name: str) -> str:
        return self.attribute_labels.get(column_name, "")

    def knows_attribute(self, column_name: str) -> bool:
        return column_name in self.attribute_labels


def _build_lexicon(platform_db: PlatformDb) -> DraftLexicon:
    return DraftLexicon(
        object_labels=blueprint_object_labels(platform_db),
        attribute_labels=blueprint_attribute_labels(platform_db),
    )


def _create_business_object(
    conn: sqlite3.Connection,
    ontology_id: int,
    table: sqlite3.Row,
    blueprint: IndustryBlueprint,
    lexicon: DraftLexicon,
) -> int:
    table_name = table["table_name"]
    code = _canonical_object_code(table_name, blueprint)
    name = (
        blueprint.object_hints.get(code)
        or blueprint.object_hints.get(table_name)
        or lexicon.object_label(code, table_name)
        or _humanize(table_name)
    )
    conn.execute(
        """
        insert into business_object (ontology_id, code, name, description, source_table_id)
        values (?, ?, ?, ?, ?)
        """,
        (ontology_id, code, name, f"由传统表 {table['table_name']} 生成的业务对象候选。", table["id"]),
    )
    return last_insert_id(conn)


def _canonical_object_code(table_name: str, blueprint: IndustryBlueprint) -> str:
    """Map conventional plural table names onto blueprint object codes."""
    code = _to_code(table_name)
    candidates = []
    if code.endswith("ies"):
        candidates.append(f"{code[:-3]}y")
    if code.endswith("s"):
        candidates.append(code[:-1])
    return next((candidate for candidate in candidates if candidate in blueprint.object_hints), code)


def _create_attribute(
    conn: sqlite3.Connection,
    object_id: int,
    column: sqlite3.Row,
    blueprint: IndustryBlueprint,
    lexicon: DraftLexicon,
) -> int:
    code = _to_code(column["column_name"])
    name = (
        blueprint.attribute_hints.get(column["column_name"])
        or lexicon.attribute_label(column["column_name"])
        or _humanize(column["column_name"])
    )
    conn.execute(
        """
        insert into business_attribute (object_id, code, name, data_type, required, source_column_id)
        values (?, ?, ?, ?, ?, ?)
        """,
        (object_id, code, name, _map_data_type(column["data_type"]), 0 if column["nullable"] else 1, column["id"]),
    )
    return last_insert_id(conn)


def _create_relations(
    conn: sqlite3.Connection, ontology_id: int, data_source_id: int, tables: Sequence[sqlite3.Row]
) -> None:
    """Generate relations with real cardinality, strength and many-to-many.

    Previously every foreign key produced one `references` row -- a constant that
    restated the foreign key rather than modelling the link. Classification is
    structural (see `relations`), so the same schema always yields the same
    relations.
    """
    objects_by_table = {
        row["table_name"]: row
        for row in conn.execute(
            """
            select bo.id, bo.code, bo.name, st.table_name
            from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.data_source_id = ?
            """,
            (ontology_id, data_source_id),
        ).fetchall()
    }
    for table in tables:
        columns = conn.execute(
            "select column_name, nullable from source_column where source_table_id = ?", (table["id"],)
        ).fetchall()
        foreign_keys = conn.execute(
            "select * from source_foreign_key where source_table_id = ?", (table["id"],)
        ).fetchall()
        if not foreign_keys:
            continue
        shapes = shapes_for_table(table["primary_key"], columns, foreign_keys)
        foreign_key_ids = {row["column_name"]: row["id"] for row in foreign_keys}
        # Two foreign keys from the same table to the same target (`created_by` and
        # `approved_by` both pointing at `users`) would otherwise collide on one
        # relation code, and the second insert would be lost.
        targets = [shape.target_table for shape in shapes]

        # A junction collapses into a direct many-to-many, but its own per-hop
        # relations are still recorded: the junction object keeps its attributes,
        # and a rule may legitimately need to reach the link row itself.
        junction = detect_junction(table["table_name"], table["primary_key"], shapes)
        for shape in shapes:
            _insert_relation(
                conn,
                ontology_id,
                objects_by_table.get(table["table_name"]),
                objects_by_table.get(shape.target_table),
                classify_foreign_key(shape),
                source_foreign_key_id=foreign_key_ids.get(shape.column_name),
                # Only disambiguate when needed, so the common single-link case
                # keeps a clean code.
                via_column=shape.column_name if targets.count(shape.target_table) > 1 else "",
            )
        if junction is not None:
            semantics = junction_semantics(junction)
            left = objects_by_table.get(junction.left.target_table)
            right = objects_by_table.get(junction.right.target_table)
            # Both directions, because a many-to-many read from either side is the
            # same business fact and both are traversed in practice.
            _insert_relation(
                conn,
                ontology_id,
                left,
                right,
                semantics,
                junction_table=junction.table_name,
                junction_source_column=junction.left.column_name,
                junction_target_column=junction.right.column_name,
            )
            _insert_relation(
                conn,
                ontology_id,
                right,
                left,
                semantics,
                junction_table=junction.table_name,
                junction_source_column=junction.right.column_name,
                junction_target_column=junction.left.column_name,
            )


def _insert_relation(
    conn: sqlite3.Connection,
    ontology_id: int,
    source_object: Any,
    target_object: Any,
    semantics: RelationSemantics,
    *,
    source_foreign_key_id: int | None = None,
    junction_table: str = "",
    junction_source_column: str = "",
    junction_target_column: str = "",
    via_column: str = "",
) -> None:
    """Store one relation, skipping links whose endpoints are not both modelled.

    A foreign key pointing at a table outside this ontology has no target object,
    so there is nothing to relate; silently skipping matches the previous behaviour.
    """
    if source_object is None or target_object is None:
        return
    code = _relation_code(source_object["code"], target_object["code"], semantics, junction_table, via_column)
    name = f"{source_object['name']}{RELATION_NAME_VERBS[semantics.kind]}{target_object['name']}"
    conn.execute(
        """
        insert into business_relation (
            ontology_id, source_object_id, target_object_id, code, name, relation_type,
            source_foreign_key_id, cardinality, relation_kind, optional, inference_reason,
            junction_table, junction_source_column, junction_target_column
        )
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ontology_id,
            source_object["id"],
            target_object["id"],
            code,
            name,
            # `relation_type` is kept as the coarse kind so existing readers and
            # exports keep a value they understand; cardinality lives in its own
            # column rather than being encoded into this string.
            semantics.kind,
            source_foreign_key_id,
            semantics.cardinality,
            semantics.kind,
            1 if semantics.optional else 0,
            semantics.reason,
            junction_table,
            junction_source_column,
            junction_target_column,
        ),
    )


# Verb per kind, so a generated relation name states the strength in business
# language instead of the uniform "关联" every relation used to get.
RELATION_NAME_VERBS = {
    COMPOSITION: "组成",
    AGGREGATION: "隶属",
    ASSOCIATION: "关联",
}


def _relation_code(
    source_code: str,
    target_code: str,
    semantics: RelationSemantics,
    junction_table: str,
    via_column: str = "",
) -> str:
    """A code that stays unique when two objects are linked more than once.

    Two foreign keys from the same table to the same target (`created_by` and
    `approved_by` both pointing at `users`) previously collided on one code. The
    junction table name disambiguates a collapsed many-to-many from the per-hop
    relations it coexists with.
    """
    if junction_table:
        return f"{source_code}_{semantics.cardinality}_{target_code}_via_{_to_code(junction_table)}"
    if via_column:
        return f"{source_code}_{semantics.cardinality}_{target_code}_by_{_to_code(via_column)}"
    return f"{source_code}_{semantics.cardinality}_{target_code}"


def _create_table_mapping(
    conn: sqlite3.Connection, ontology_id: int, table: sqlite3.Row, object_id: int, blueprint: IndustryBlueprint
) -> None:
    confidence = (
        MAPPING_CONFIDENCE.blueprint_match
        if table["table_name"] in blueprint.object_hints
        else MAPPING_CONFIDENCE.structural_match
    )
    conn.execute(
        """
        insert into semantic_mapping (ontology_id, mapping_type, source_ref, target_ref, confidence, status, evidence)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ontology_id,
            "table_to_object",
            f"table:{table['table_name']}",
            f"business_object:{object_id}",
            confidence,
            "pending",
            f"由{blueprint.name}、表名和主键结构自动生成",
        ),
    )


def _create_column_mapping(
    conn: sqlite3.Connection,
    ontology_id: int,
    table: sqlite3.Row,
    column: sqlite3.Row,
    object_id: int,
    attribute_id: int,
    blueprint: IndustryBlueprint,
    lexicon: DraftLexicon,
) -> None:
    if column["column_name"] in blueprint.attribute_hints:
        confidence = MAPPING_CONFIDENCE.blueprint_match
    elif lexicon.knows_attribute(column["column_name"]):
        confidence = MAPPING_CONFIDENCE.lexicon_match
    else:
        confidence = MAPPING_CONFIDENCE.weak_match
    conn.execute(
        """
        insert into semantic_mapping (ontology_id, mapping_type, source_ref, target_ref, confidence, status, evidence)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ontology_id,
            "column_to_attribute",
            f"table:{table['table_name']}.column:{column['column_name']}",
            f"business_object:{object_id}.attribute:{attribute_id}",
            confidence,
            "pending",
            f"由{blueprint.name}、字段名、字段类型和样例值自动生成",
        ),
    )


def _create_generic_rules(conn: sqlite3.Connection, ontology_id: int) -> None:
    rows = conn.execute(
        """
        select bo.code as object_code, bo.name as object_name, ba.code as attribute_code, ba.name as attribute_name, ba.data_type
        from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        where bo.ontology_id = ?
        order by bo.code, ba.code
        """,
        (ontology_id,),
    ).fetchall()
    amount_markers = ("amount", "price", "cost", "quantity")
    for row in rows:
        if row["data_type"] not in ("integer", "number"):
            continue
        if not any(marker in row["attribute_code"] for marker in amount_markers):
            continue
        code = f"{row['object_code']}_{row['attribute_code']}_non_negative"
        _insert_rule(
            conn,
            ontology_id,
            code,
            f"{row['object_name']}{row['attribute_name']}不能为负",
            "validation",
            row["object_code"],
            f"{row['attribute_code']} >= 0",
            "blocking",
            f"{row['object_name']}的{row['attribute_name']}不能为负。",
        )


def _create_blueprint_rules(conn: sqlite3.Connection, ontology_id: int, blueprint: IndustryBlueprint) -> None:
    existing_scopes = {
        row["code"]
        for row in conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchall()
    }
    for template in blueprint.rule_templates:
        if template.scope_object_code in existing_scopes:
            _insert_rule(
                conn,
                ontology_id,
                template.code,
                template.name,
                template.rule_type,
                template.scope_object_code,
                template.expression,
                template.severity,
                template.natural_language,
            )


def _insert_rule(
    conn: sqlite3.Connection,
    ontology_id: int,
    code: str,
    name: str,
    rule_type: str,
    scope: str,
    expression: str,
    severity: str,
    natural_language: str,
) -> None:
    # Generated rules bypass the governance write path, so validate here too:
    # the kernel fails closed, and an unparseable generated rule would block
    # every instance of the object it scopes to.
    validation = validate_rule_expression(expression)
    if not validation["valid"]:
        raise ValueError(f"生成的规则表达式不可执行 ({code}): {validation['error']}")
    conn.execute(
        """
        insert into business_rule (
            ontology_id, code, name, rule_type, scope_object_code, expression, severity, natural_language
        )
        values (?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(ontology_id, code) do update set
            name = excluded.name,
            rule_type = excluded.rule_type,
            scope_object_code = excluded.scope_object_code,
            expression = excluded.expression,
            severity = excluded.severity,
            natural_language = excluded.natural_language
        """,
        (ontology_id, code, name, rule_type, scope, expression, severity, natural_language),
    )


def _to_code(value: str) -> str:
    value = re.sub(r"[^0-9a-zA-Z_]+", "_", value.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value.lower()


def _humanize(value: str) -> str:
    return value.replace("_", " ").title()


def _map_data_type(sql_type: str) -> str:
    normalized = sql_type.lower()
    if "int" in normalized:
        return "integer"
    if "real" in normalized or "numeric" in normalized or "decimal" in normalized:
        return "number"
    if "date" in normalized or "time" in normalized:
        return "date"
    return "text"


def _ontology_base_uri(ontology: dict[str, Any]) -> str:
    """The versioned base IRI for one ontology.

    Keyed on **name** rather than row id. `unique(name, version)` is what makes an
    ontology identifiable in this schema, and `derive` deliberately carries the name
    forward while allocating a new row -- so an id-based IRI changes when nothing about
    the concept did.

    That matters because these IRIs are what an external consumer references. With the
    id in the path, deriving 0.2.0 from 0.1.0 moved every class to a new namespace, and
    a consumer's stored reference pointed at a version that would never be updated
    again. Nothing failed loudly: their queries simply returned the old model forever.

    The version stays in the path on purpose. Two versions of an ontology can disagree
    about what a class means, so a consumer that pinned 0.1.0 must keep resolving 0.1.0
    -- collapsing the version would silently change the meaning of an existing
    reference, which is the failure the version is there to prevent.
    """
    base = SEMANTIC_ASSET_NAMING.ontology_base.rstrip("/")
    return f"{base}/{ontology_slug(str(ontology['name']))}/v/{_uri_part(str(ontology['version']))}/"


def _uri_part(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_.-]+", "-", value.strip())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "item"


def ontology_slug(name: str) -> str:
    """An ontology name as an IRI path segment, preserving non-ASCII by encoding it.

    `_uri_part` replaces every non-ASCII run with `-` and falls back to `item` when
    nothing survives. For an object *code* that is fine -- codes come from column names
    and are ASCII. For an ontology *name* it is not: this codebase is Chinese, so
    「合同管理本体」and「客户管理本体」both collapsed to `item`, and every Chinese-named
    ontology in a deployment shared one namespace. Two unrelated models would then export
    classes with identical IRIs, and merging their graphs would silently conflate them.

    Percent-encoding instead, which is what IRIs are for. `quote` is used with an empty
    safe set so `/` inside a name cannot introduce a path segment -- a name containing a
    slash would otherwise change the shape of every IRI derived from it.
    """
    encoded = quote(name.strip(), safe="")
    return encoded or "unnamed"


def _ttl_literal(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


def _ttl_iri(base: str, *segments: str) -> str:
    """An absolute IRI in angle brackets, for use as a Turtle subject or object.

    Written in full rather than as a prefixed name (`bp:object/contract`) because a
    prefixed name's local part cannot contain `/` in Turtle: the parser stops at the
    slash and the whole statement is a syntax error.

    This export emitted prefixed names with slashes since it shipped, which meant **no
    RDF parser could read the Turtle output** the README promises. The tests did not
    catch it because they asserted the output *contained* certain substrings, and an
    invalid document contains them just as well as a valid one. `tests/test_metadata_flow.py`
    now parses the result with a real RDF library instead.
    """
    path = "/".join(_uri_part(segment) for segment in segments)
    return f"<{base}{path}>"


def _ttl_bool(value: object) -> str:
    return "true" if bool(value) else "false"


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _ontology_summary_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row["domain"],
        "version": row["version"],
        "status": row["status"],
        "publishedAt": row["published_at"],
        "published_at": row["published_at"],
        "createdAt": row["created_at"],
        "created_at": row["created_at"],
    }


def _business_object_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "ontologyId": row["ontology_id"],
        "ontology_id": row["ontology_id"],
        "code": row["code"],
        "name": row["name"],
        "description": row["description"],
        "sourceTable": row["table_name"],
        "source_table": row["table_name"],
        "table_name": row["table_name"],
    }


def _business_attribute_row(row: sqlite3.Row) -> dict[str, Any]:
    # Attributes predate the derived/unit columns, and callers may pass a row from a
    # narrower query, so both are read defensively. Empty means "a plain mapped
    # column with no declared unit" -- the prior behaviour.
    def _get(name: str) -> str:
        try:
            return row[name] or ""
        except (KeyError, IndexError, TypeError):
            return ""

    derived_expression = _get("derived_expression")
    unit = _get("unit")
    return {
        "id": row["id"],
        "objectId": row["object_id"],
        "object_id": row["object_id"],
        "objectCode": row["object_code"],
        "code": row["code"],
        "name": row["name"],
        "dataType": row["data_type"],
        "data_type": row["data_type"],
        "required": bool(row["required"]),
        "sourceColumn": row["column_name"],
        "source_column": row["column_name"],
        # A derived attribute is an ordinary attribute to every consumer; only the
        # provenance differs, which is what these two fields state.
        "derived": bool(derived_expression),
        "derivedExpression": derived_expression,
        "derived_expression": derived_expression,
        "unit": unit,
        "unitName": _unit_label(unit),
        "description": "",
    }


def _unit_label(code: str) -> str:
    """Human-readable unit name, falling back to the code for unknown units.

    A unit that was registered by a deployment and later removed should still render
    as something, rather than making the whole ontology view fail.
    """
    if not code:
        return ""
    try:
        return get_unit(code).name
    except UnitError:
        return code


def _business_relation_row(row: sqlite3.Row) -> dict[str, Any]:
    # Relations predate the semantic columns, and a caller may hand in a row from a
    # narrower query, so each is read defensively with the weakest default.
    def _get(name: str, fallback: Any) -> Any:
        try:
            value = row[name]
        except (KeyError, IndexError, TypeError):
            return fallback
        return fallback if value is None else value

    cardinality = _get("cardinality", "many_to_one")
    kind = _get("relation_kind", row["relation_type"])
    optional = bool(_get("optional", 1))
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "type": row["relation_type"],
        "relationType": row["relation_type"],
        "relation_type": row["relation_type"],
        "cardinality": cardinality,
        "cardinalityLabel": CARDINALITY_LABELS.get(cardinality, cardinality),
        "relationKind": kind,
        "relation_kind": kind,
        "relationKindLabel": KIND_LABELS.get(kind, kind),
        "optional": optional,
        "inferenceReason": _get("inference_reason", ""),
        "inference_reason": _get("inference_reason", ""),
        "junctionTable": _get("junction_table", ""),
        "junction_table": _get("junction_table", ""),
        "junctionSourceColumn": _get("junction_source_column", ""),
        "junctionTargetColumn": _get("junction_target_column", ""),
        "sourceObjectId": row["source_object_id"],
        "source_object_id": row["source_object_id"],
        "targetObjectId": row["target_object_id"],
        "target_object_id": row["target_object_id"],
        "sourceCode": row["source_code"],
        "source_code": row["source_code"],
        "targetCode": row["target_code"],
        "target_code": row["target_code"],
        "sourceForeignKey": row["source_foreign_key"],
        "source_foreign_key": row["source_foreign_key"],
    }


def mapping_target_codes(conn: sqlite3.Connection, ontology_id: int) -> tuple[dict[int, str], dict[int, str]]:
    """`({object.id: code}, {attribute.id: code})` for one ontology.

    `target_ref` carries ids (`business_object:1.attribute:3`), and the field the UI reads is
    named `targetObjectCode`. Resolving them is the difference between a review table that
    says "contract / amount" and one that says "1 / 3" -- and an id under a name that
    promises a code is a lie the type system cannot catch, because both are strings.

    Two maps, not one: object ids and attribute ids are separate sequences that both start
    at 1, so a single dict resolves `business_object:1` to whichever attribute happened to
    be inserted second. Merging them was my first version, and it labelled every
    table-to-object mapping with the code of attribute 1.
    """
    objects: dict[int, str] = {}
    for row in conn.execute("select id, code from business_object where ontology_id = ?", (ontology_id,)).fetchall():
        objects[int(row["id"])] = row["code"]
    attributes: dict[int, str] = {}
    for row in conn.execute(
        """
        select ba.id, ba.code from business_attribute ba
        join business_object bo on bo.id = ba.object_id
        where bo.ontology_id = ?
        """,
        (ontology_id,),
    ).fetchall():
        attributes[int(row["id"])] = row["code"]
    return objects, attributes


def semantic_mapping_row(
    row: sqlite3.Row, codes: tuple[dict[int, str], dict[int, str]] | None = None
) -> dict[str, Any]:
    """One mapping row, decoded for a reader.

    Public because the mapping review endpoint needs exactly this shape and was
    returning raw `dict(row)` instead -- so the review page, whose whole job is
    confirming the 32 mappings that block publication, rendered five blank columns
    out of seven. The serializer existed the whole time, four hundred lines away in
    this module; the endpoint simply did not call it.

    `codes` maps the object and attribute ids inside `target_ref` to their codes. Without
    it the id is returned under `targetObjectId` and `targetObjectCode` stays empty: an
    empty cell is a gap the reader can see, an id under a code's name is not.
    """
    source_table, source_column = _parse_source_ref(row["source_ref"])
    target_object, target_attribute = _parse_target_ref(row["target_ref"])
    object_codes, attribute_codes = codes or ({}, {})
    return {
        "id": row["id"],
        "ontologyId": row["ontology_id"],
        "ontology_id": row["ontology_id"],
        "mappingType": row["mapping_type"],
        "mapping_type": row["mapping_type"],
        "sourceRef": row["source_ref"],
        "source_ref": row["source_ref"],
        "targetRef": row["target_ref"],
        "target_ref": row["target_ref"],
        "sourceTable": source_table,
        "sourceColumn": source_column,
        "targetObjectId": _as_id(target_object),
        "targetAttributeId": _as_id(target_attribute),
        "targetObjectCode": object_codes.get(_as_id(target_object), "") or target_object,
        "targetAttributeCode": attribute_codes.get(_as_id(target_attribute)) if _as_id(target_attribute) else None,
        "confidence": row["confidence"],
        "status": row["status"],
        "evidence": row["evidence"],
        "reviewer": row["reviewer"],
        "reviewedAt": row["reviewed_at"],
        "createdAt": row["created_at"],
    }


def business_rule_row(row: sqlite3.Row) -> dict[str, Any]:
    """One rule row, decoded for a reader.

    Public for the same reason `semantic_mapping_row` is: the rule list endpoint needs
    exactly this shape and was returning `dict(row)` instead, so the table's 类型 / 适用对象 /
    业务说明 columns rendered blank against `rule_type` / `scope_object_code` /
    `natural_language`.
    """
    return {
        "id": row["id"],
        "ontologyId": row["ontology_id"],
        "ontology_id": row["ontology_id"],
        "code": row["code"],
        "name": row["name"],
        "description": row["natural_language"],
        "ruleType": row["rule_type"],
        "rule_type": row["rule_type"],
        "scopeObjectCode": row["scope_object_code"],
        "scope_object_code": row["scope_object_code"],
        "expression": row["expression"],
        "severity": row["severity"],
        "naturalLanguage": row["natural_language"],
        "natural_language": row["natural_language"],
        "status": row["status"],
        "enabled": row["status"] == "published",
    }


def _parse_source_ref(source_ref: str) -> tuple[str, str | None]:
    if not source_ref.startswith("table:"):
        return source_ref, None
    value = source_ref.removeprefix("table:")
    if ".column:" in value:
        table, column = value.split(".column:", 1)
        return table, column
    return value, None


def _as_id(value: str | None) -> int:
    """The id inside a decoded ref, or 0 when the ref held something else."""
    try:
        return int(value) if value else 0
    except ValueError:
        return 0


def _parse_target_ref(target_ref: str) -> tuple[str, str | None]:
    object_match = re.search(r"business_object:(\d+)", target_ref)
    attribute_match = re.search(r"attribute:(\d+)", target_ref)
    return (
        object_match.group(1) if object_match else target_ref,
        attribute_match.group(1) if attribute_match else None,
    )
