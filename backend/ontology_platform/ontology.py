from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from .adapters import get_adapter
from .database import connect


NAME_HINTS = {
    "customer": "客户",
    "contract": "合同",
    "payment_plan": "付款计划",
    "invoice": "发票",
    "equipment": "设备",
    "work_order": "工单",
    "inspection_record": "点检记录",
    "spare_part": "备件",
}

ATTRIBUTE_HINTS = {
    "id": "标识",
    "customer_name": "客户名称",
    "credit_status": "信用状态",
    "industry": "行业",
    "contract_no": "合同编号",
    "customer_id": "客户",
    "title": "标题",
    "amount": "金额",
    "status": "状态",
    "signed_date": "签订日期",
    "effective_date": "生效日期",
    "end_date": "结束日期",
    "plan_no": "付款计划编号",
    "due_date": "到期日期",
    "planned_amount": "计划金额",
    "paid_amount": "已付金额",
    "paid_date": "付款日期",
    "invoice_no": "发票编号",
    "invoice_amount": "发票金额",
    "issued_date": "开票日期",
    "created_at": "创建时间",
    "equipment_code": "设备编号",
    "equipment_name": "设备名称",
    "location": "位置",
    "criticality": "重要等级",
    "work_order_no": "工单编号",
    "equipment_id": "设备",
    "fault_description": "故障描述",
    "reported_at": "报修时间",
    "closed_at": "关闭时间",
    "inspection_date": "点检日期",
    "result": "结果",
    "part_code": "备件编号",
    "part_name": "备件名称",
    "stock_quantity": "库存数量",
    "minimum_quantity": "最低库存",
}


def generate_ontology_draft(platform_db: Path | str, data_source_id: int, name: str | None = None, domain: str | None = None) -> dict[str, Any]:
    with connect(platform_db) as conn:
        data_source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if data_source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        resolved_domain = domain or data_source["domain"] or "通用业务"
        resolved_name = name or f"{resolved_domain}本体"
        ontology_id = _create_ontology(conn, resolved_name, resolved_domain)
        tables = conn.execute("select * from source_table where data_source_id = ? order by table_name", (data_source_id,)).fetchall()
        object_ids: dict[int, int] = {}

        for table in tables:
            object_id = _create_business_object(conn, ontology_id, table)
            object_ids[table["id"]] = object_id
            _create_table_mapping(conn, ontology_id, table, object_id)
            columns = conn.execute("select * from source_column where source_table_id = ? order by ordinal", (table["id"],)).fetchall()
            for column in columns:
                attribute_id = _create_attribute(conn, object_id, column)
                _create_column_mapping(conn, ontology_id, table, column, object_id, attribute_id)

        foreign_keys = conn.execute(
            """
            select fk.*, st.table_name as source_table_name
            from source_foreign_key fk
            join source_table st on st.id = fk.source_table_id
            where st.data_source_id = ?
            """,
            (data_source_id,),
        ).fetchall()
        for foreign_key in foreign_keys:
            _create_relation_from_foreign_key(conn, ontology_id, foreign_key)

        _create_generic_rules(conn, ontology_id)
        _create_domain_rules(conn, ontology_id)
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            ("system", "generate_ontology_draft", "ontology", str(ontology_id), json.dumps({"dataSourceId": data_source_id}, ensure_ascii=False)),
        )
        return summarize_ontology(conn, ontology_id)


def explain_instance(platform_db: Path | str, ontology_id: int, object_code: str, instance_id: str) -> dict[str, Any]:
    with connect(platform_db) as platform:
        ontology = platform.execute("select * from ontology where id = ?", (ontology_id,)).fetchone()
        if ontology is None:
            raise ValueError(f"本体不存在: {ontology_id}")
        business_object = platform.execute(
            "select * from business_object where ontology_id = ? and code = ?",
            (ontology_id, object_code),
        ).fetchone()
        if business_object is None:
            raise ValueError(f"业务对象不存在: {object_code}")
        source_table = platform.execute("select * from source_table where id = ?", (business_object["source_table_id"],)).fetchone()
        data_source = platform.execute("select ds.* from data_source ds join source_table st on st.data_source_id = ds.id where st.id = ?", (source_table["id"],)).fetchone()
        primary_key = source_table["primary_key"] or "id"
        if "," in primary_key:
            raise ValueError("当前原型不支持复合主键实例解释")

        adapter = get_adapter(data_source["source_type"])
        with adapter.runtime(data_source["connection_uri"]) as runtime:
            record = runtime.fetch_one(source_table["table_name"], primary_key, instance_id)
            if record is None:
                raise ValueError(f"实例不存在: {object_code}/{instance_id}")

        attributes = platform.execute(
            """
            select ba.code, ba.name, sc.column_name
            from business_attribute ba
            join source_column sc on sc.id = ba.source_column_id
            where ba.object_id = ?
            order by ba.id
            """,
            (business_object["id"],),
        ).fetchall()

        values = [
            {
                "attributeCode": attr["code"],
                "attributeName": attr["name"],
                "sourceColumn": attr["column_name"],
                "value": record[attr["column_name"]],
            }
            for attr in attributes
        ]
        return {
            "ontology": {"id": ontology["id"], "name": ontology["name"], "version": ontology["version"]},
            "object": {"code": business_object["code"], "name": business_object["name"]},
            "objectCode": business_object["code"],
            "instanceId": instance_id,
            "source": {"table": source_table["table_name"], "primaryKey": primary_key, "instanceId": instance_id},
            "attributes": values,
            "explanation": f"{business_object['name']}实例 {instance_id} 已映射到传统表 {source_table['table_name']}。",
        }


def list_ontologies(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select id, name, domain, version, status, published_at, created_at
            from ontology
            order by id
            """
        ).fetchall()
        return [_ontology_summary_row(row) for row in rows]


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
               ba.required, sc.column_name, bo.code as object_code
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
        "mappings": [_semantic_mapping_row(row) for row in mappings],
        "rules": [_business_rule_row(row) for row in rules],
    }


def export_ontology_asset(platform_db: Path | str, ontology_id: int, export_format: str = "jsonld") -> dict[str, str]:
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
    attribute_by_id = {item["id"]: item for item in detail["attributes"]}
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
            "ont": "https://ontology-platform.local/vocab#",
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
        "@prefix ont: <https://ontology-platform.local/vocab#> .",
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
                f"bp:object/{_uri_part(item['code'])} a ont:BusinessObject ;",
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
                f"bp:object/{_uri_part(item['objectCode'])}/attribute/{_uri_part(item['code'])} a ont:BusinessAttribute ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:dataType {_ttl_literal(item['dataType'])} ;",
                f"  ont:required {_ttl_bool(item['required'])} ;",
                f"  ont:sourceColumn {_ttl_literal(item['sourceColumn'])} ;",
                f"  ont:belongsTo bp:object/{_uri_part(item['objectCode'])} .",
                "",
            ]
        )
    for item in detail["relations"]:
        lines.extend(
            [
                f"bp:relation/{_uri_part(item['code'])} a ont:BusinessRelation ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:relationType {_ttl_literal(item['relationType'])} ;",
                f"  ont:sourceObject bp:object/{_uri_part(item['sourceCode'])} ;",
                f"  ont:targetObject bp:object/{_uri_part(item['targetCode'])} ;",
                f"  ont:sourceForeignKey {_ttl_literal(item['sourceForeignKey'])} .",
                "",
            ]
        )
    for item in detail["rules"]:
        lines.extend(
            [
                f"bp:rule/{_uri_part(item['code'])} a ont:BusinessRule ;",
                f"  ont:code {_ttl_literal(item['code'])} ;",
                f"  ont:name {_ttl_literal(item['name'])} ;",
                f"  ont:ruleType {_ttl_literal(item['ruleType'])} ;",
                f"  ont:scopeObject bp:object/{_uri_part(item['scopeObjectCode'])} ;",
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
                f"bp:mapping/{item['id']} a ont:SemanticMapping ;",
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


def _create_ontology(conn: sqlite3.Connection, name: str, domain: str) -> int:
    existing = conn.execute("select id, status from ontology where name = ? and version = '0.1.0'", (name,)).fetchone()
    if existing:
        if existing["status"] == "published":
            raise ValueError(f"本体版本已发布，不能重新生成草案: {name} 0.1.0。请派生新版本。")
        ontology_id = int(existing["id"])
        conn.execute("delete from business_rule where ontology_id = ?", (ontology_id,))
        conn.execute("delete from semantic_mapping where ontology_id = ?", (ontology_id,))
        conn.execute("delete from business_relation where ontology_id = ?", (ontology_id,))
        conn.execute("delete from business_attribute where object_id in (select id from business_object where ontology_id = ?)", (ontology_id,))
        conn.execute("delete from business_object where ontology_id = ?", (ontology_id,))
        return ontology_id

    conn.execute(
        "insert into ontology (name, domain, version, status) values (?, ?, ?, ?)",
        (name, domain, "0.1.0", "draft"),
    )
    return int(conn.execute("select last_insert_rowid()").fetchone()[0])


def _create_business_object(conn: sqlite3.Connection, ontology_id: int, table: sqlite3.Row) -> int:
    code = _to_code(table["table_name"])
    name = NAME_HINTS.get(table["table_name"], _humanize(table["table_name"]))
    conn.execute(
        """
        insert into business_object (ontology_id, code, name, description, source_table_id)
        values (?, ?, ?, ?, ?)
        """,
        (ontology_id, code, name, f"由传统表 {table['table_name']} 生成的业务对象候选。", table["id"]),
    )
    return int(conn.execute("select last_insert_rowid()").fetchone()[0])


def _create_attribute(conn: sqlite3.Connection, object_id: int, column: sqlite3.Row) -> int:
    code = _to_code(column["column_name"])
    name = ATTRIBUTE_HINTS.get(column["column_name"], _humanize(column["column_name"]))
    conn.execute(
        """
        insert into business_attribute (object_id, code, name, data_type, required, source_column_id)
        values (?, ?, ?, ?, ?, ?)
        """,
        (object_id, code, name, _map_data_type(column["data_type"]), 0 if column["nullable"] else 1, column["id"]),
    )
    return int(conn.execute("select last_insert_rowid()").fetchone()[0])


def _create_relation_from_foreign_key(conn: sqlite3.Connection, ontology_id: int, foreign_key: sqlite3.Row) -> None:
    source_object = conn.execute(
        """
        select bo.* from business_object bo
        join source_table st on st.id = bo.source_table_id
        where bo.ontology_id = ? and st.table_name = ?
        """,
        (ontology_id, foreign_key["source_table_name"]),
    ).fetchone()
    target_object = conn.execute(
        """
        select bo.* from business_object bo
        join source_table st on st.id = bo.source_table_id
        where bo.ontology_id = ? and st.table_name = ?
        """,
        (ontology_id, foreign_key["target_table"]),
    ).fetchone()
    if source_object is None or target_object is None:
        return

    code = f"{source_object['code']}_references_{target_object['code']}"
    name = f"{source_object['name']}关联{target_object['name']}"
    conn.execute(
        """
        insert into business_relation (
            ontology_id, source_object_id, target_object_id, code, name, relation_type, source_foreign_key_id
        )
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (ontology_id, source_object["id"], target_object["id"], code, name, "references", foreign_key["id"]),
    )


def _create_table_mapping(conn: sqlite3.Connection, ontology_id: int, table: sqlite3.Row, object_id: int) -> None:
    conn.execute(
        """
        insert into semantic_mapping (ontology_id, mapping_type, source_ref, target_ref, confidence, status, evidence)
        values (?, ?, ?, ?, ?, ?, ?)
        """,
        (ontology_id, "table_to_object", f"table:{table['table_name']}", f"business_object:{object_id}", 0.85, "pending", "由表名和主键结构自动生成"),
    )


def _create_column_mapping(conn: sqlite3.Connection, ontology_id: int, table: sqlite3.Row, column: sqlite3.Row, object_id: int, attribute_id: int) -> None:
    confidence = 0.9 if column["column_name"] in ATTRIBUTE_HINTS else 0.7
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
            "由字段名、字段类型和样例值自动生成",
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


def _create_domain_rules(conn: sqlite3.Connection, ontology_id: int) -> None:
    object_codes = {
        row["code"]
        for row in conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchall()
    }
    if {"contract", "customer"}.issubset(object_codes):
        _create_contract_rules(conn, ontology_id)
    if {"equipment", "work_order"}.issubset(object_codes):
        _create_equipment_rules(conn, ontology_id)


def _create_contract_rules(conn: sqlite3.Connection, ontology_id: int) -> None:
    rules = (
        ("contract_amount_positive", "合同金额必须大于 0", "validation", "contract", "amount > 0", "blocking", "合同金额必须大于 0。"),
        ("effective_contract_signed", "已生效合同必须有签订日期", "validation", "contract", "status != 'effective' or signed_date != null", "blocking", "当合同状态为已生效时，签订日期不能为空。"),
        ("blacklist_customer_warning", "黑名单客户合同风险", "risk", "contract", "customer.credit_status != 'blacklist'", "warning", "客户为黑名单时，新签或存量合同需要风险复核。"),
        ("payment_plan_amount_match", "付款计划总额应等于合同金额", "validation", "contract", "sum(payment_plan.planned_amount) == amount", "warning", "付款计划总额应等于合同金额。"),
        ("overdue_payment_warning", "逾期付款风险", "risk", "payment_plan", "status != 'overdue'", "warning", "付款计划已逾期，需提示履约风险。"),
    )
    for code, name, rule_type, scope, expression, severity, natural_language in rules:
        _insert_rule(conn, ontology_id, code, name, rule_type, scope, expression, severity, natural_language)


def _create_equipment_rules(conn: sqlite3.Connection, ontology_id: int) -> None:
    rules = (
        ("critical_equipment_open_fault", "重要设备存在未关闭工单风险", "risk", "equipment", "criticality != 'high' or count(work_order.status == 'open') == 0", "warning", "重要设备存在未关闭工单时，需要优先处理。"),
        ("closed_work_order_has_closed_at", "已关闭工单必须有关闭时间", "validation", "work_order", "status != 'closed' or closed_at != null", "blocking", "工单关闭时必须记录关闭时间。"),
        ("spare_part_stock_floor", "备件库存不能低于最低库存", "risk", "spare_part", "stock_quantity >= minimum_quantity", "warning", "备件库存低于最低库存时，需要补货。"),
    )
    existing_scopes = {
        row["code"]
        for row in conn.execute("select code from business_object where ontology_id = ?", (ontology_id,)).fetchall()
    }
    for code, name, rule_type, scope, expression, severity, natural_language in rules:
        if scope in existing_scopes:
            _insert_rule(conn, ontology_id, code, name, rule_type, scope, expression, severity, natural_language)


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
    return f"https://ontology-platform.local/ontology/{ontology['id']}/v/{_uri_part(str(ontology['version']))}/"


def _uri_part(value: str) -> str:
    normalized = re.sub(r"[^0-9a-zA-Z_.-]+", "-", value.strip())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "item"


def _ttl_literal(value: object) -> str:
    return json.dumps("" if value is None else str(value), ensure_ascii=False)


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
        "description": "",
    }


def _business_relation_row(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "code": row["code"],
        "name": row["name"],
        "type": row["relation_type"],
        "relationType": row["relation_type"],
        "relation_type": row["relation_type"],
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


def _semantic_mapping_row(row: sqlite3.Row) -> dict[str, Any]:
    source_table, source_column = _parse_source_ref(row["source_ref"])
    target_object, target_attribute = _parse_target_ref(row["target_ref"])
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
        "targetObjectCode": target_object,
        "targetAttributeCode": target_attribute,
        "confidence": row["confidence"],
        "status": row["status"],
        "evidence": row["evidence"],
        "reviewer": row["reviewer"],
        "reviewedAt": row["reviewed_at"],
        "createdAt": row["created_at"],
    }


def _business_rule_row(row: sqlite3.Row) -> dict[str, Any]:
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


def _parse_target_ref(target_ref: str) -> tuple[str, str | None]:
    object_match = re.search(r"business_object:(\d+)", target_ref)
    attribute_match = re.search(r"attribute:(\d+)", target_ref)
    return (
        object_match.group(1) if object_match else target_ref,
        attribute_match.group(1) if attribute_match else None,
    )
