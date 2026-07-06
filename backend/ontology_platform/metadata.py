from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters import SourceColumnInfo, SourceForeignKeyInfo, SourceTableInfo, get_adapter, test_connection
from .database import connect


@dataclass(frozen=True)
class DataSource:
    id: int
    name: str
    domain: str
    system_category: str
    source_type: str
    connection_uri: str
    capabilities: list[str]


@dataclass(frozen=True)
class SourceApi:
    id: int
    data_source_id: int
    operation_code: str
    name: str
    method: str
    path: str
    semantic_action: str


def register_data_source(
    platform_db: Path | str,
    name: str,
    source_type: str,
    connection_uri: str,
    domain: str = "",
    system_category: str = "database",
    capabilities: list[str] | None = None,
) -> DataSource:
    get_adapter(source_type)

    capability_values = capabilities if capabilities is not None else ["metadata_scan", "semantic_mapping"]
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into data_source (name, domain, system_category, source_type, connection_uri, capabilities)
            values (?, ?, ?, ?, ?, ?)
            on conflict(name) do update set
                domain = excluded.domain,
                system_category = excluded.system_category,
                source_type = excluded.source_type,
                connection_uri = excluded.connection_uri,
                capabilities = excluded.capabilities
            """,
            (name, domain, system_category, source_type, connection_uri, json.dumps(capability_values, ensure_ascii=False)),
        )
        row = conn.execute(
            "select id, name, domain, system_category, source_type, connection_uri, capabilities from data_source where name = ?",
            (name,),
        ).fetchone()
        return _row_to_data_source(row)


def list_data_sources(platform_db: Path | str) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select id, name, domain, system_category, source_type, connection_uri,
                   capabilities, created_at
            from data_source
            order by id
            """
        ).fetchall()
        return [_data_source_dict(row) for row in rows]


def register_source_api(
    platform_db: Path | str,
    data_source_id: int,
    operation_code: str,
    name: str,
    method: str,
    path: str,
    semantic_action: str = "",
    request_schema: dict[str, Any] | None = None,
    response_schema: dict[str, Any] | None = None,
) -> SourceApi:
    with connect(platform_db) as conn:
        source = conn.execute("select id from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        conn.execute(
            """
            insert into source_api (
                data_source_id, operation_code, name, method, path,
                semantic_action, request_schema, response_schema
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(data_source_id, operation_code) do update set
                name = excluded.name,
                method = excluded.method,
                path = excluded.path,
                semantic_action = excluded.semantic_action,
                request_schema = excluded.request_schema,
                response_schema = excluded.response_schema
            """,
            (
                data_source_id,
                operation_code,
                name,
                method.upper(),
                path,
                semantic_action,
                json.dumps(request_schema or {}, ensure_ascii=False),
                json.dumps(response_schema or {}, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "select * from source_api where data_source_id = ? and operation_code = ?",
            (data_source_id, operation_code),
        ).fetchone()
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            ("system", "register_source_api", "data_source", str(data_source_id), json.dumps({"operationCode": operation_code}, ensure_ascii=False)),
        )
        return _row_to_source_api(row)


def list_source_apis(platform_db: Path | str, data_source_id: int) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            "select * from source_api where data_source_id = ? order by operation_code",
            (data_source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def assess_data_source_readiness(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        tables = conn.execute("select * from source_table where data_source_id = ?", (data_source_id,)).fetchall()
        table_ids = [row["id"] for row in tables]
        columns = conn.execute(
            """
            select sc.*
            from source_column sc
            join source_table st on st.id = sc.source_table_id
            where st.data_source_id = ?
            """,
            (data_source_id,),
        ).fetchall()
        foreign_keys = conn.execute(
            """
            select fk.*
            from source_foreign_key fk
            join source_table st on st.id = fk.source_table_id
            where st.data_source_id = ?
            """,
            (data_source_id,),
        ).fetchall()
        apis = conn.execute("select * from source_api where data_source_id = ?", (data_source_id,)).fetchall()
        ontology_rows = conn.execute(
            """
            select distinct o.id, o.status
            from ontology o
            join business_object bo on bo.ontology_id = o.id
            join source_table st on st.id = bo.source_table_id
            where st.data_source_id = ?
            """,
            (data_source_id,),
        ).fetchall()
        mapping_counts = conn.execute(
            """
            select sm.status, count(*) as total
            from semantic_mapping sm
            join business_object bo on bo.ontology_id = sm.ontology_id
            join source_table st on st.id = bo.source_table_id
            where st.data_source_id = ?
            group by sm.status
            """,
            (data_source_id,),
        ).fetchall()

    checks = [
        _readiness_check(
            "connection",
            "连接配置",
            True,
            "已登记数据源连接配置。",
            "登记数据源连接地址和类型。",
            10,
        ),
        _readiness_check(
            "metadata_scan",
            "元数据扫描",
            len(tables) > 0 and len(columns) > 0,
            f"已扫描 {len(tables)} 张表、{len(columns)} 个字段。",
            "执行元数据扫描，获取表、字段、主键和外键。",
            20,
        ),
        _readiness_check(
            "primary_keys",
            "实例定位",
            bool(tables) and all(row["primary_key"] for row in tables),
            f"{sum(1 for row in tables if row['primary_key'])}/{len(tables)} 张表具备主键。",
            "为缺少主键的表配置实例标识，否则无法稳定解释单个业务对象实例。",
            15,
        ),
        _readiness_check(
            "relations",
            "关系识别",
            len(foreign_keys) > 0 or len(tables) <= 1,
            f"识别到 {len(foreign_keys)} 条外键关系。",
            "补充外键或关系映射，形成业务对象之间的语义关联。",
            10,
        ),
        _readiness_check(
            "ontology",
            "本体草案",
            len(ontology_rows) > 0,
            f"已有 {len(ontology_rows)} 个关联本体版本。",
            "基于扫描结果和行业蓝图生成本体草案。",
            15,
        ),
        _readiness_check(
            "mapping_governance",
            "映射治理",
            _mapping_count(mapping_counts, "confirmed") > 0,
            f"已确认 {_mapping_count(mapping_counts, 'confirmed')} 条映射，待审核 {_mapping_count(mapping_counts, 'pending')} 条。",
            "组织业务专家审核语义映射，至少确认关键对象和关键字段。",
            15,
        ),
        _readiness_check(
            "business_apis",
            "业务 API",
            len(apis) > 0 and all(row["semantic_action"] for row in apis),
            f"已登记 {len(apis)} 个业务 API，其中 {sum(1 for row in apis if row['semantic_action'])} 个具备语义动作。",
            "登记传统业务系统 API，并为每个操作绑定语义动作。",
            15,
        ),
    ]
    gaps = [item for item in checks if not item["passed"]]
    score = sum(item["weight"] for item in checks if item["passed"])
    status = "ready" if not gaps else "partial" if score >= 45 else "blocked"
    return {
        "dataSourceId": data_source_id,
        "name": source["name"],
        "domain": source["domain"],
        "score": score,
        "status": status,
        "summary": {
            "tables": len(tables),
            "columns": len(columns),
            "foreignKeys": len(foreign_keys),
            "apis": len(apis),
            "ontologies": len(ontology_rows),
            "confirmedMappings": _mapping_count(mapping_counts, "confirmed"),
            "pendingMappings": _mapping_count(mapping_counts, "pending"),
        },
        "checks": checks,
        "gaps": gaps,
        "nextActions": [item["remediation"] for item in gaps],
    }


def check_data_source_connection(
    platform_db: Path | str,
    source_type: str | None = None,
    connection_uri: str | None = None,
    data_source_id: int | None = None,
) -> dict[str, Any]:
    if data_source_id is not None:
        with connect(platform_db) as conn:
            source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
            if source is None:
                raise ValueError(f"数据源不存在: {data_source_id}")
            result = test_connection(source["source_type"], source["connection_uri"])
            result["dataSourceId"] = data_source_id
            result["name"] = source["name"]
            return result

    if not source_type or not connection_uri:
        raise ValueError("测试未登记数据源时必须提供 sourceType 和 connectionUri")
    return test_connection(source_type, connection_uri)


def scan_data_source(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as platform:
        source = platform.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        adapter = get_adapter(source["source_type"])
        try:
            tables = adapter.scan(source["connection_uri"])
        except Exception as error:
            raise ValueError(f"数据源扫描失败: {error}") from error

        _delete_derived_drafts(platform, data_source_id)
        platform.execute("delete from source_foreign_key where source_table_id in (select id from source_table where data_source_id = ?)", (data_source_id,))
        platform.execute("delete from source_column where source_table_id in (select id from source_table where data_source_id = ?)", (data_source_id,))
        platform.execute("delete from source_table where data_source_id = ?", (data_source_id,))

        scanned_tables = []
        for table in tables:
            table_id = _store_table(platform, data_source_id, table)
            _store_columns(platform, table_id, table.columns)
            _store_foreign_keys(platform, table_id, table.foreign_keys)
            scanned_tables.append(
                {
                    "table": table.name,
                    "columns": len(table.columns),
                    "foreignKeys": len(table.foreign_keys),
                }
            )

        platform.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            ("system", "scan_metadata", "data_source", str(data_source_id), json.dumps(scanned_tables, ensure_ascii=False)),
        )
        return {"dataSourceId": data_source_id, "tables": scanned_tables}


def _row_to_data_source(row: sqlite3.Row) -> DataSource:
    return DataSource(
        id=row["id"],
        name=row["name"],
        domain=row["domain"],
        system_category=row["system_category"],
        source_type=row["source_type"],
        connection_uri=row["connection_uri"],
        capabilities=json.loads(row["capabilities"] or "[]"),
    )


def _data_source_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row["domain"],
        "systemCategory": row["system_category"],
        "system_category": row["system_category"],
        "sourceType": row["source_type"],
        "source_type": row["source_type"],
        "connectionUri": row["connection_uri"],
        "connection_uri": row["connection_uri"],
        "capabilities": json.loads(row["capabilities"] or "[]"),
        "createdAt": row["created_at"],
        "created_at": row["created_at"],
    }


def _readiness_check(code: str, name: str, passed: bool, evidence: str, remediation: str, weight: int) -> dict[str, Any]:
    return {
        "code": code,
        "name": name,
        "passed": passed,
        "evidence": evidence,
        "remediation": remediation,
        "weight": weight,
    }


def _mapping_count(rows: list[sqlite3.Row], status: str) -> int:
    for row in rows:
        if row["status"] == status:
            return int(row["total"])
    return 0


def _row_to_source_api(row: sqlite3.Row) -> SourceApi:
    return SourceApi(
        id=row["id"],
        data_source_id=row["data_source_id"],
        operation_code=row["operation_code"],
        name=row["name"],
        method=row["method"],
        path=row["path"],
        semantic_action=row["semantic_action"],
    )


def _delete_derived_drafts(platform: sqlite3.Connection, data_source_id: int) -> None:
    ontology_rows = platform.execute(
        """
        select distinct bo.ontology_id
        from business_object bo
        join source_table st on st.id = bo.source_table_id
        where st.data_source_id = ?
        """,
        (data_source_id,),
    ).fetchall()
    ontology_ids = [row["ontology_id"] for row in ontology_rows]
    for ontology_id in ontology_ids:
        rule_ids = [
            row["id"]
            for row in platform.execute("select id from business_rule where ontology_id = ?", (ontology_id,)).fetchall()
        ]
        for rule_id in rule_ids:
            platform.execute("delete from explanation_trace where inference_result_id in (select id from inference_result where rule_id = ?)", (rule_id,))
            platform.execute("delete from inference_result where rule_id = ?", (rule_id,))
        platform.execute("delete from business_rule where ontology_id = ?", (ontology_id,))
        platform.execute("delete from semantic_mapping where ontology_id = ?", (ontology_id,))
        platform.execute("delete from business_relation where ontology_id = ?", (ontology_id,))
        platform.execute("delete from business_attribute where object_id in (select id from business_object where ontology_id = ?)", (ontology_id,))
        platform.execute("delete from business_object where ontology_id = ?", (ontology_id,))
        platform.execute("delete from ontology where id = ? and status = 'draft'", (ontology_id,))


def _store_table(platform: sqlite3.Connection, data_source_id: int, table: SourceTableInfo) -> int:
    platform.execute(
        """
        insert into source_table (data_source_id, table_name, row_count, primary_key)
        values (?, ?, ?, ?)
        """,
        (data_source_id, table.name, table.row_count, table.primary_key),
    )
    return int(platform.execute("select last_insert_rowid()").fetchone()[0])


def _store_columns(platform: sqlite3.Connection, table_id: int, columns: list[SourceColumnInfo]) -> None:
    for column in columns:
        platform.execute(
            """
            insert into source_column (
                source_table_id, column_name, data_type, nullable, ordinal,
                is_primary_key, sample_values, null_ratio, distinct_count, enum_candidate
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_id,
                column.name,
                column.data_type,
                1 if column.nullable else 0,
                column.ordinal,
                1 if column.is_primary_key else 0,
                json.dumps(column.profile.samples, ensure_ascii=False),
                column.profile.null_ratio,
                column.profile.distinct_count,
                1 if column.profile.enum_candidate else 0,
            ),
        )


def _store_foreign_keys(platform: sqlite3.Connection, table_id: int, foreign_keys: list[SourceForeignKeyInfo]) -> None:
    for foreign_key in foreign_keys:
        platform.execute(
            """
            insert into source_foreign_key (source_table_id, column_name, target_table, target_column)
            values (?, ?, ?, ?)
            """,
            (table_id, foreign_key.column_name, foreign_key.target_table, foreign_key.target_column),
        )
