from __future__ import annotations

from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .config import clamp_page_size
from .database import connect
from .metadata import scan_data_source
from .ontology import generate_ontology_draft


def initialize_knowledge_base(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    scan = scan_data_source(platform_db, data_source_id)
    existing = [item for item in list_knowledge_bases(platform_db) if item["dataSourceId"] == data_source_id]
    ontology = None
    if not existing:
        ontology = generate_ontology_draft(platform_db, data_source_id)
    chain = build_reasoning_chain(platform_db, data_source_id)
    return {"status": "initialized", "scan": {"tables": len(scan["tables"])}, "ontology": ontology, "reasoningChain": chain}


def browse_source_table(platform_db: Path | str, data_source_id: int, table_name: str, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = clamp_page_size(limit)
    offset = max(0, int(offset))
    with connect(platform_db) as conn:
        source = conn.execute("select source_type, connection_uri from data_source where id = ?", (data_source_id,)).fetchone()
        table = conn.execute(
            "select id from source_table where data_source_id = ? and table_name = ?", (data_source_id, table_name)
        ).fetchone()
        if source is None:
            raise ValueError("数据源不存在")
        if table is None:
            raise ValueError("数据表未经扫描或不属于该数据源")
        source_data = dict(source)
    adapter = get_adapter(source_data["source_type"])
    with adapter.runtime(source_data["connection_uri"]) as runtime:
        rows, total = runtime.browse_rows(table_name, limit, offset)
    columns = list(rows[0].keys()) if rows else _scanned_columns(platform_db, data_source_id, table_name)
    return {
        "dataSourceId": data_source_id,
        "tableName": table_name,
        "columns": columns,
        "rows": rows,
        "page": {"limit": limit, "offset": offset, "total": total, "hasMore": offset + len(rows) < total},
    }


def list_knowledge_bases(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """select ds.id as data_source_id, ds.name, ds.source_type, ds.domain,
                      o.id as ontology_id, o.name as ontology_name, o.version, o.status
               from data_source ds
               join source_table st on st.data_source_id = ds.id
               join business_object bo on bo.source_table_id = st.id
               join ontology o on o.id = bo.ontology_id
               where o.id = (select max(o2.id) from ontology o2 join business_object bo2 on bo2.ontology_id = o2.id join source_table st2 on st2.id = bo2.source_table_id where st2.data_source_id = ds.id)
               group by ds.id, ds.name, ds.source_type, ds.domain, o.id, o.name, o.version, o.status
               order by ds.id desc"""
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            objects = conn.execute("select code, name from business_object where ontology_id = ? order by id", (item["ontology_id"],)).fetchall()
            items.append({
                "dataSourceId": item["data_source_id"], "name": item["name"], "sourceType": item["source_type"],
                "domain": item["domain"], "ontologyId": item["ontology_id"], "ontologyName": item["ontology_name"],
                "version": item["version"], "status": item["status"],
                "objects": [{"code": obj["code"], "name": obj["name"]} for obj in objects],
                "objectCodes": [obj["code"] for obj in objects],
            })
        return items


def build_reasoning_chain(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    bases = [item for item in list_knowledge_bases(platform_db) if item["dataSourceId"] == data_source_id]
    if not bases:
        return {"dataSourceId": data_source_id, "initialized": False, "objects": [], "relations": [], "rules": [], "steps": []}
    base = bases[0]
    ontology_id = base["ontologyId"]
    with connect(platform_db) as conn:
        relations = conn.execute(
            """select br.code, br.name, br.relation_type, source.code as source_code, target.code as target_code
               from business_relation br
               join business_object source on source.id = br.source_object_id
               join business_object target on target.id = br.target_object_id
               where br.ontology_id = ? order by br.id""", (ontology_id,)
        ).fetchall()
        rules = conn.execute(
            "select code, name, rule_type, scope_object_code, expression, severity, natural_language, status from business_rule where ontology_id = ? order by priority desc, id",
            (ontology_id,),
        ).fetchall()
    relation_items = [{"code": row["code"], "name": row["name"], "relationType": row["relation_type"], "sourceObject": row["source_code"], "targetObject": row["target_code"]} for row in relations]
    rule_items = [{"code": row["code"], "name": row["name"], "ruleType": row["rule_type"], "scopeObjectCode": row["scope_object_code"], "expression": row["expression"], "severity": row["severity"], "naturalLanguage": row["natural_language"], "status": row["status"]} for row in rules]
    steps = [{"type": "source_resolution", "label": "根据问题定位数据源与业务对象"}]
    if relation_items:
        steps.append({"type": "relation_traversal", "label": f"沿 {len(relation_items)} 条本体关系装载关联对象"})
    if rule_items:
        steps.append({"type": "rule_evaluation", "label": f"执行 {len(rule_items)} 条版本化业务规则"})
    steps.append({"type": "evidence_explanation", "label": "输出原始数据、关系路径、命中规则和结论"})
    return {**base, "initialized": True, "objects": base["objects"], "relations": relation_items, "rules": rule_items, "steps": steps}


def _scanned_columns(platform_db: Path | str, data_source_id: int, table_name: str) -> list[str]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """select sc.column_name from source_column sc join source_table st on st.id = sc.source_table_id
               where st.data_source_id = ? and st.table_name = ? order by sc.ordinal""", (data_source_id, table_name)
        ).fetchall()
        return [row["column_name"] for row in rows]
