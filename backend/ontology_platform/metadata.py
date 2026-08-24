from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .adapters import SourceColumnInfo, SourceForeignKeyInfo, SourceTableInfo, get_adapter, test_connection
from .context import PlatformDb
from .credentials import redact_connection_uri
from .database import connect, last_insert_id


@dataclass(frozen=True)
class DataSource:
    id: int
    name: str
    domain: str
    system_category: str
    source_type: str
    connection_uri: str
    api_base_url: str
    capabilities: list[str]

    def public_dict(self) -> dict[str, Any]:
        """Serialize for API responses with the credential removed."""
        redacted = redact_connection_uri(self.connection_uri)
        return {
            "id": self.id,
            "name": self.name,
            "domain": self.domain,
            "system_category": self.system_category,
            "systemCategory": self.system_category,
            "source_type": self.source_type,
            "sourceType": self.source_type,
            "connection_uri": redacted,
            "connectionUri": redacted,
            "connectionUriRedacted": redacted != self.connection_uri,
            "api_base_url": self.api_base_url,
            "apiBaseUrl": self.api_base_url,
            "capabilities": list(self.capabilities),
        }


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
    platform_db: PlatformDb,
    name: str,
    source_type: str,
    connection_uri: str,
    domain: str = "",
    system_category: str = "database",
    capabilities: list[str] | None = None,
    api_base_url: str = "",
    api_headers: dict[str, str] | None = None,
) -> DataSource:
    get_adapter(source_type)

    capability_values = capabilities if capabilities is not None else ["metadata_scan", "semantic_mapping"]
    header_values = _normalize_api_headers(api_headers)
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into data_source (name, domain, system_category, source_type, connection_uri, api_base_url, api_headers, capabilities)
            values (?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(name) do update set
                domain = excluded.domain,
                system_category = excluded.system_category,
                source_type = excluded.source_type,
                connection_uri = excluded.connection_uri,
                api_base_url = excluded.api_base_url,
                api_headers = excluded.api_headers,
                capabilities = excluded.capabilities
            """,
            (
                name,
                domain,
                system_category,
                source_type,
                connection_uri,
                api_base_url,
                json.dumps(header_values, ensure_ascii=False),
                json.dumps(capability_values, ensure_ascii=False),
            ),
        )
        row = conn.execute(
            "select id, name, domain, system_category, source_type, connection_uri, api_base_url, capabilities from data_source where name = ?",
            (name,),
        ).fetchone()
        return _row_to_data_source(row)


def list_data_sources(platform_db: PlatformDb) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            """
            select id, name, domain, system_category, source_type, connection_uri, api_base_url, api_headers,
                   capabilities, created_at
            from data_source
            order by id
            """
        ).fetchall()
        return [_data_source_dict(row) for row in rows]


def register_source_api(
    platform_db: PlatformDb,
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
            (
                "system",
                "register_source_api",
                "data_source",
                str(data_source_id),
                json.dumps({"operationCode": operation_code}, ensure_ascii=False),
            ),
        )
        return _row_to_source_api(row)


def list_source_apis(platform_db: PlatformDb, data_source_id: int) -> list[dict[str, Any]]:
    with connect(platform_db) as conn:
        rows = conn.execute(
            "select * from source_api where data_source_id = ? order by operation_code",
            (data_source_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def import_openapi_operations(platform_db: PlatformDb, data_source_id: int, spec: dict[str, Any]) -> dict[str, Any]:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI 文档缺少 paths 对象")
    imported = []
    skipped = []
    for path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            method_upper = method.upper()
            if method_upper not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                continue
            if not isinstance(operation, dict):
                skipped.append({"path": path, "method": method_upper, "reason": "operation 不是对象"})
                continue
            operation_code = _operation_code(path, method_upper, operation)
            source_api = register_source_api(
                platform_db,
                data_source_id,
                operation_code,
                operation.get("summary") or operation.get("description") or operation_code,
                method_upper,
                path,
                operation.get("x-semantic-action") or _semantic_action(operation_code, path),
                _request_schema(operation),
                _response_schema(operation),
            )
            imported.append(source_api.__dict__)
    with connect(platform_db) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                "system",
                "import_openapi_operations",
                "data_source",
                str(data_source_id),
                json.dumps({"imported": len(imported), "skipped": len(skipped)}, ensure_ascii=False),
            ),
        )
    return {"imported": imported, "skipped": skipped, "count": len(imported)}


def import_openapi_operations_from_url(
    platform_db: PlatformDb,
    data_source_id: int,
    url: str,
    timeout_seconds: float = 10,
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        headers = _load_api_headers(source["api_headers"])

    if not _is_http_url(url):
        raise ValueError("OpenAPI URL 必须是 HTTP/HTTPS 地址")
    request = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise ValueError(f"OpenAPI 文档读取失败: HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise ValueError(f"OpenAPI 文档读取失败: {error.reason}") from error
    try:
        spec = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError("OpenAPI URL 返回内容不是有效 JSON") from error
    result = import_openapi_operations(platform_db, data_source_id, spec)
    result["sourceUrl"] = url
    return result


def assess_data_source_readiness(platform_db: PlatformDb, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        tables = conn.execute("select * from source_table where data_source_id = ?", (data_source_id,)).fetchall()
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

    system_category = source["system_category"] or "database"
    requires_api_gateway = "api" in system_category.lower()
    api_base_url = (source["api_base_url"] or "").strip()
    api_gateway_ready = not requires_api_gateway or _is_http_url(api_base_url)
    if api_base_url:
        api_gateway_evidence = f"业务 API 基址已配置为 {api_base_url}。"
    elif requires_api_gateway:
        api_gateway_evidence = "系统分类声明了 API 能力，但尚未配置业务 API 基址。"
    else:
        api_gateway_evidence = "系统分类未声明 API 能力，业务 API 基址不是必填项。"

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
            "api_gateway",
            "业务 API 网关",
            api_gateway_ready,
            api_gateway_evidence,
            "为数据库+API 或 API 类传统系统配置 HTTP/HTTPS 业务 API 基址。",
            10,
        ),
        _readiness_check(
            "business_apis",
            "业务 API",
            len(apis) > 0 and all(row["semantic_action"] for row in apis),
            f"已登记 {len(apis)} 个业务 API，其中 {sum(1 for row in apis if row['semantic_action'])} 个具备语义动作。",
            "登记传统业务系统 API，并为每个操作绑定语义动作。",
            5,
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
            "apiBaseUrlConfigured": bool(api_base_url),
            "requiresApiGateway": requires_api_gateway,
            "ontologies": len(ontology_rows),
            "confirmedMappings": _mapping_count(mapping_counts, "confirmed"),
            "pendingMappings": _mapping_count(mapping_counts, "pending"),
        },
        "checks": checks,
        "gaps": gaps,
        "nextActions": [item["remediation"] for item in gaps],
    }


def check_data_source_connection(
    platform_db: PlatformDb,
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


def check_business_api_gateway(
    platform_db: PlatformDb, data_source_id: int, timeout_seconds: float = 3
) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        api_base_url = (source["api_base_url"] or "").strip()

    result: dict[str, Any] = {
        "dataSourceId": data_source_id,
        "name": source["name"],
        "apiBaseUrl": api_base_url,
        "configured": bool(api_base_url),
        "reachable": False,
        "status": "not_configured",
        "statusCode": None,
        "message": "尚未配置业务 API 基址。",
    }
    if not api_base_url:
        return result
    if not _is_http_url(api_base_url):
        return {
            **result,
            "status": "invalid_url",
            "message": "业务 API 基址必须是 HTTP/HTTPS 地址。",
        }

    request = urllib.request.Request(api_base_url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            status_code = int(response.status)
        return {
            **result,
            "reachable": status_code < 500,
            "status": "ok" if status_code < 500 else "server_error",
            "statusCode": status_code,
            "message": f"业务 API 网关返回 HTTP {status_code}。",
        }
    except urllib.error.HTTPError as error:
        status_code = int(error.code)
        return {
            **result,
            "reachable": status_code < 500,
            "status": "http_error" if status_code < 500 else "server_error",
            "statusCode": status_code,
            "message": f"业务 API 网关返回 HTTP {status_code}。",
        }
    except Exception as error:
        return {
            **result,
            "status": "connection_error",
            "message": f"业务 API 网关不可达: {error}",
        }


def scan_data_source(platform_db: PlatformDb, data_source_id: int) -> dict[str, Any]:
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
        platform.execute(
            "delete from source_foreign_key where source_table_id in (select id from source_table where data_source_id = ?)",
            (data_source_id,),
        )
        platform.execute(
            "delete from source_column where source_table_id in (select id from source_table where data_source_id = ?)",
            (data_source_id,),
        )
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
            (
                "system",
                "scan_metadata",
                "data_source",
                str(data_source_id),
                json.dumps(scanned_tables, ensure_ascii=False),
            ),
        )
        return {"dataSourceId": data_source_id, "tables": scanned_tables}


def analyze_schema_drift(platform_db: PlatformDb, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as platform:
        source = platform.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")

        stored_tables = _stored_schema(platform, data_source_id)
        if not stored_tables:
            return {
                "dataSourceId": data_source_id,
                "status": "not_scanned",
                "summary": _drift_summary(),
                "addedTables": [],
                "removedTables": [],
                "changedTables": [],
                "impacts": {"objects": [], "mappings": [], "rules": []},
                "nextActions": ["先执行元数据扫描，建立传统系统结构基线。"],
            }

        adapter = get_adapter(source["source_type"])
        try:
            live_tables = adapter.scan(source["connection_uri"])
        except Exception as error:
            raise ValueError(f"结构漂移分析失败: {error}") from error

        live_schema = {table.name: table for table in live_tables}
        added_tables = [
            _table_snapshot(table) for name, table in sorted(live_schema.items()) if name not in stored_tables
        ]
        removed_tables = [
            _stored_table_snapshot(table) for name, table in sorted(stored_tables.items()) if name not in live_schema
        ]
        changed_tables = [
            change
            for name in sorted(set(stored_tables).intersection(live_schema))
            if (change := _compare_table(stored_tables[name], live_schema[name]))
        ]

        affected_tables = {item["tableName"] for item in removed_tables}
        affected_tables.update(item["tableName"] for item in changed_tables)
        affected_columns = {
            (change["tableName"], column["columnName"])
            for change in changed_tables
            for group in ("removedColumns", "changedColumns")
            for column in change[group]
        }
        impacts = _schema_drift_impacts(platform, data_source_id, affected_tables, affected_columns)
        summary = _drift_summary(
            added_tables=len(added_tables),
            removed_tables=len(removed_tables),
            changed_tables=len(changed_tables),
            added_columns=sum(len(item["addedColumns"]) for item in changed_tables),
            removed_columns=sum(len(item["removedColumns"]) for item in changed_tables),
            changed_columns=sum(len(item["changedColumns"]) for item in changed_tables),
            impacted_objects=len(impacts["objects"]),
            impacted_mappings=len(impacts["mappings"]),
            impacted_rules=len(impacts["rules"]),
        )
        has_drift = any(summary[key] for key in ("addedTables", "removedTables", "changedTables"))

        return {
            "dataSourceId": data_source_id,
            "status": "drift_detected" if has_drift else "no_drift",
            "summary": summary,
            "addedTables": added_tables,
            "removedTables": removed_tables,
            "changedTables": changed_tables,
            "impacts": impacts,
            "nextActions": _schema_drift_next_actions(summary, impacts),
        }


def _row_to_data_source(row: sqlite3.Row) -> DataSource:
    return DataSource(
        id=row["id"],
        name=row["name"],
        domain=row["domain"],
        system_category=row["system_category"],
        source_type=row["source_type"],
        connection_uri=row["connection_uri"],
        api_base_url=row["api_base_url"],
        capabilities=json.loads(row["capabilities"] or "[]"),
    )


def _data_source_dict(row: sqlite3.Row) -> dict[str, Any]:
    redacted = redact_connection_uri(row["connection_uri"])
    return {
        "id": row["id"],
        "name": row["name"],
        "domain": row["domain"],
        "systemCategory": row["system_category"],
        "system_category": row["system_category"],
        "sourceType": row["source_type"],
        "source_type": row["source_type"],
        # Never return the raw credential: a data source row carries the
        # production database password.
        "connectionUri": redacted,
        "connection_uri": redacted,
        "connectionUriRedacted": redacted != row["connection_uri"],
        "apiBaseUrl": row["api_base_url"],
        "api_base_url": row["api_base_url"],
        "apiHeadersConfigured": bool(_load_api_headers(row["api_headers"])),
        "apiHeaderNames": sorted(_load_api_headers(row["api_headers"]).keys()),
        "capabilities": json.loads(row["capabilities"] or "[]"),
        "createdAt": row["created_at"],
        "created_at": row["created_at"],
    }


def _readiness_check(
    code: str, name: str, passed: bool, evidence: str, remediation: str, weight: int
) -> dict[str, Any]:
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


def _is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def _load_api_headers(value: str | None) -> dict[str, str]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {
        str(key): str(header_value)
        for key, header_value in parsed.items()
        if str(key).strip() and header_value is not None
    }


def _normalize_api_headers(headers: dict[str, str] | None) -> dict[str, str]:
    if not headers:
        return {}
    return {str(key).strip(): str(value) for key, value in headers.items() if str(key).strip() and value is not None}


def _stored_schema(platform: sqlite3.Connection, data_source_id: int) -> dict[str, dict[str, Any]]:
    tables = platform.execute(
        "select * from source_table where data_source_id = ? order by table_name",
        (data_source_id,),
    ).fetchall()
    result: dict[str, dict[str, Any]] = {}
    for table in tables:
        columns = platform.execute(
            "select * from source_column where source_table_id = ? order by ordinal",
            (table["id"],),
        ).fetchall()
        result[table["table_name"]] = {"table": table, "columns": {column["column_name"]: column for column in columns}}
    return result


def _table_snapshot(table: SourceTableInfo) -> dict[str, Any]:
    return {
        "tableName": table.name,
        "rowCount": table.row_count,
        "primaryKey": table.primary_key,
        "columns": [_column_snapshot(column) for column in table.columns],
    }


def _stored_table_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    table = item["table"]
    return {
        "tableName": table["table_name"],
        "rowCount": table["row_count"],
        "primaryKey": table["primary_key"],
        "columns": [_stored_column_snapshot(column) for column in item["columns"].values()],
    }


def _column_snapshot(column: SourceColumnInfo) -> dict[str, Any]:
    return {
        "columnName": column.name,
        "dataType": column.data_type,
        "nullable": column.nullable,
        "isPrimaryKey": column.is_primary_key,
        "ordinal": column.ordinal,
    }


def _stored_column_snapshot(column: sqlite3.Row) -> dict[str, Any]:
    return {
        "columnName": column["column_name"],
        "dataType": column["data_type"],
        "nullable": bool(column["nullable"]),
        "isPrimaryKey": bool(column["is_primary_key"]),
        "ordinal": column["ordinal"],
    }


def _compare_table(stored: dict[str, Any], live: SourceTableInfo) -> dict[str, Any] | None:
    stored_table = stored["table"]
    stored_columns = stored["columns"]
    live_columns = {column.name: column for column in live.columns}
    added_columns = [
        _column_snapshot(column) for name, column in sorted(live_columns.items()) if name not in stored_columns
    ]
    removed_columns = [
        _stored_column_snapshot(column) for name, column in sorted(stored_columns.items()) if name not in live_columns
    ]
    changed_columns = [
        change
        for name in sorted(set(stored_columns).intersection(live_columns))
        if (change := _compare_column(stored_columns[name], live_columns[name]))
    ]
    primary_key_changed = (stored_table["primary_key"] or "") != (live.primary_key or "")
    row_count_changed = stored_table["row_count"] != live.row_count
    if not (added_columns or removed_columns or changed_columns or primary_key_changed or row_count_changed):
        return None
    return {
        "tableName": live.name,
        "primaryKeyChanged": primary_key_changed,
        "oldPrimaryKey": stored_table["primary_key"],
        "newPrimaryKey": live.primary_key,
        "rowCountChanged": row_count_changed,
        "oldRowCount": stored_table["row_count"],
        "newRowCount": live.row_count,
        "addedColumns": added_columns,
        "removedColumns": removed_columns,
        "changedColumns": changed_columns,
    }


def _compare_column(stored: sqlite3.Row, live: SourceColumnInfo) -> dict[str, Any] | None:
    changes: dict[str, dict[str, Any]] = {}
    comparisons = {
        "dataType": (stored["data_type"], live.data_type),
        "nullable": (bool(stored["nullable"]), live.nullable),
        "isPrimaryKey": (bool(stored["is_primary_key"]), live.is_primary_key),
    }
    for field, (old_value, new_value) in comparisons.items():
        if old_value != new_value:
            changes[field] = {"old": old_value, "new": new_value}
    if not changes:
        return None
    return {
        "columnName": live.name,
        "changes": changes,
        "old": _stored_column_snapshot(stored),
        "new": _column_snapshot(live),
    }


def _schema_drift_impacts(
    platform: sqlite3.Connection,
    data_source_id: int,
    affected_tables: set[str],
    affected_columns: set[tuple[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    if not affected_tables:
        return {"objects": [], "mappings": [], "rules": []}

    objects = platform.execute(
        """
        select bo.id, bo.ontology_id, bo.code, bo.name, st.table_name
        from business_object bo
        join source_table st on st.id = bo.source_table_id
        where st.data_source_id = ?
        order by bo.id
        """,
        (data_source_id,),
    ).fetchall()
    impacted_objects = [
        {
            "id": row["id"],
            "ontologyId": row["ontology_id"],
            "code": row["code"],
            "name": row["name"],
            "sourceTable": row["table_name"],
            "impactReason": "source_table_changed",
        }
        for row in objects
        if row["table_name"] in affected_tables
    ]

    mappings = platform.execute(
        """
        select distinct sm.id, sm.ontology_id, sm.mapping_type, sm.source_ref, sm.target_ref, sm.status
        from semantic_mapping sm
        join business_object bo on bo.ontology_id = sm.ontology_id
        join source_table st on st.id = bo.source_table_id
        where st.data_source_id = ?
        order by sm.id
        """,
        (data_source_id,),
    ).fetchall()
    impacted_mappings = []
    for row in mappings:
        table_name, column_name = _parse_mapping_source_ref(row["source_ref"])
        if table_name in affected_tables and (
            column_name is None or not affected_columns or (table_name, column_name) in affected_columns
        ):
            impacted_mappings.append(
                {
                    "id": row["id"],
                    "ontologyId": row["ontology_id"],
                    "mappingType": row["mapping_type"],
                    "sourceRef": row["source_ref"],
                    "targetRef": row["target_ref"],
                    "status": row["status"],
                    "impactReason": "source_mapping_changed",
                }
            )

    impacted_object_codes = {item["code"] for item in impacted_objects}
    column_names = {column for _, column in affected_columns}
    rules = platform.execute(
        """
        select br.id, br.ontology_id, br.code, br.name, br.scope_object_code, br.expression, br.status
        from business_rule br
        join business_object bo on bo.ontology_id = br.ontology_id
        join source_table st on st.id = bo.source_table_id
        where st.data_source_id = ?
        order by br.id
        """,
        (data_source_id,),
    ).fetchall()
    impacted_rules = []
    seen_rule_ids: set[int] = set()
    for row in rules:
        reason = ""
        if row["scope_object_code"] in impacted_object_codes:
            reason = "scope_object_changed"
        elif any(column and column in row["expression"] for column in column_names):
            reason = "rule_expression_references_changed_column"
        if reason and row["id"] not in seen_rule_ids:
            impacted_rules.append(
                {
                    "id": row["id"],
                    "ontologyId": row["ontology_id"],
                    "code": row["code"],
                    "name": row["name"],
                    "scopeObjectCode": row["scope_object_code"],
                    "status": row["status"],
                    "impactReason": reason,
                }
            )
            seen_rule_ids.add(row["id"])

    return {"objects": impacted_objects, "mappings": impacted_mappings, "rules": impacted_rules}


def _parse_mapping_source_ref(source_ref: str) -> tuple[str, str | None]:
    if not source_ref.startswith("table:"):
        return source_ref, None
    value = source_ref.removeprefix("table:")
    if ".column:" not in value:
        return value, None
    table_name, column_name = value.split(".column:", 1)
    return table_name, column_name


def _drift_summary(
    added_tables: int = 0,
    removed_tables: int = 0,
    changed_tables: int = 0,
    added_columns: int = 0,
    removed_columns: int = 0,
    changed_columns: int = 0,
    impacted_objects: int = 0,
    impacted_mappings: int = 0,
    impacted_rules: int = 0,
) -> dict[str, int]:
    return {
        "addedTables": added_tables,
        "removedTables": removed_tables,
        "changedTables": changed_tables,
        "addedColumns": added_columns,
        "removedColumns": removed_columns,
        "changedColumns": changed_columns,
        "impactedObjects": impacted_objects,
        "impactedMappings": impacted_mappings,
        "impactedRules": impacted_rules,
    }


def _schema_drift_next_actions(summary: dict[str, int], impacts: dict[str, list[dict[str, Any]]]) -> list[str]:
    if not any(summary.values()):
        return ["当前业务系统结构与最近一次扫描基线一致。"]
    actions = ["评估漂移影响后再执行重新扫描，避免直接覆盖可追溯基线。"]
    if summary["removedTables"] or summary["removedColumns"] or summary["changedColumns"]:
        actions.append("对受影响对象、映射和规则发起业务专家复核。")
    if impacts["objects"] or impacts["mappings"] or impacts["rules"]:
        actions.append("派生新本体版本并重新确认关键语义映射。")
    if summary["addedTables"] or summary["addedColumns"]:
        actions.append("将新增表字段纳入行业蓝图或本体草案增量建模。")
    return actions


def _operation_code(path: str, method: str, operation: dict[str, Any]) -> str:
    raw = operation.get("operationId")
    if not raw:
        raw = f"{method.lower()}_{path.strip('/') or 'root'}"
    value = "".join(char if char.isalnum() else "_" for char in str(raw))
    return "_".join(part for part in value.lower().split("_") if part)


def _semantic_action(operation_code: str, path: str) -> str:
    path_parts = [
        part.strip("{}").replace("-", "_") for part in path.strip("/").split("/") if part and not part.startswith("{")
    ]
    object_code = path_parts[-1] if path_parts else operation_code.split("_", 1)[0]
    object_code = object_code[:-1] if object_code.endswith("s") else object_code
    action = operation_code
    for prefix in ("get_", "post_", "put_", "patch_", "delete_"):
        if action.startswith(prefix):
            action = action.removeprefix(prefix)
            break
    return f"{object_code}.{action}"


def _request_schema(operation: dict[str, Any]) -> dict[str, Any]:
    request_body = operation.get("requestBody") or {}
    content = request_body.get("content") if isinstance(request_body, dict) else None
    if isinstance(content, dict):
        for media_type in ("application/json", "application/*+json"):
            schema = content.get(media_type, {}).get("schema") if isinstance(content.get(media_type), dict) else None
            if schema:
                return schema
    parameters = operation.get("parameters")
    if isinstance(parameters, list):
        return {"parameters": parameters}
    return {}


def _response_schema(operation: dict[str, Any]) -> dict[str, Any]:
    responses = operation.get("responses")
    if not isinstance(responses, dict):
        return {}
    for status in ("200", "201", "202", "default"):
        response = responses.get(status)
        if not isinstance(response, dict):
            continue
        content = response.get("content")
        if not isinstance(content, dict):
            continue
        json_media = content.get("application/json")
        if isinstance(json_media, dict) and isinstance(json_media.get("schema"), dict):
            return json_media["schema"]
    return {}


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
            platform.execute(
                "delete from explanation_trace where inference_result_id in (select id from inference_result where rule_id = ?)",
                (rule_id,),
            )
            platform.execute("delete from inference_result where rule_id = ?", (rule_id,))
        platform.execute("delete from business_rule where ontology_id = ?", (ontology_id,))
        platform.execute("delete from semantic_mapping where ontology_id = ?", (ontology_id,))
        platform.execute("delete from business_relation where ontology_id = ?", (ontology_id,))
        platform.execute(
            "delete from business_attribute where object_id in (select id from business_object where ontology_id = ?)",
            (ontology_id,),
        )
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
    return last_insert_id(platform)


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
                json.dumps(column.profile.samples, ensure_ascii=False, default=str),
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
