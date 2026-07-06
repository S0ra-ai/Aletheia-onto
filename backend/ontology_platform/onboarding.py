from __future__ import annotations

from pathlib import Path
from typing import Any

from .metadata import (
    assess_data_source_readiness,
    check_business_api_gateway,
    check_data_source_connection,
    import_openapi_operations,
    import_openapi_operations_from_url,
    register_data_source,
    scan_data_source,
)
from .ontology import generate_ontology_draft


def run_onboarding_pipeline(
    platform_db: Path | str,
    name: str,
    source_type: str,
    connection_uri: str,
    domain: str = "",
    system_category: str = "database",
    capabilities: list[str] | None = None,
    api_base_url: str = "",
    api_headers: dict[str, str] | None = None,
    blueprint_id: str | None = None,
    ontology_name: str | None = None,
    generate_ontology: bool = True,
    openapi_url: str = "",
    openapi_spec: dict[str, Any] | None = None,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []
    source = register_data_source(platform_db, name, source_type, connection_uri, domain, system_category, capabilities, api_base_url, api_headers)
    steps.append(_step("register_data_source", "completed", f"数据源已登记: {source.id}", {"dataSourceId": source.id}))

    connection = check_data_source_connection(platform_db, data_source_id=source.id)
    steps.append(_step("test_connection", "completed" if connection["reachable"] else "failed", connection["message"], connection))
    if not connection["reachable"]:
        readiness = assess_data_source_readiness(platform_db, source.id)
        return {
            "dataSource": source.__dict__,
            "connection": connection,
            "apiGateway": None,
            "scan": None,
            "ontology": None,
            "readiness": readiness,
            "steps": steps,
            "status": "blocked",
        }

    api_gateway = None
    if api_base_url or "api" in system_category.lower():
        api_gateway = check_business_api_gateway(platform_db, source.id)
        gateway_status = "completed" if api_gateway["reachable"] else "failed"
        steps.append(_step("test_api_gateway", gateway_status, api_gateway["message"], api_gateway))
    else:
        steps.append(_step("test_api_gateway", "skipped", "系统分类未声明 API 能力，已跳过业务网关测试。", {}))

    scan = scan_data_source(platform_db, source.id)
    steps.append(_step("scan_metadata", "completed", f"已扫描 {len(scan['tables'])} 张表。", scan))

    api_import = None
    if openapi_url:
        api_import = import_openapi_operations_from_url(platform_db, source.id, openapi_url)
        steps.append(_step("import_openapi", "completed", f"已从 URL 导入 {api_import['count']} 个业务 API。", api_import))
    elif openapi_spec:
        api_import = import_openapi_operations(platform_db, source.id, openapi_spec)
        steps.append(_step("import_openapi", "completed", f"已导入 {api_import['count']} 个业务 API。", api_import))
    else:
        steps.append(_step("import_openapi", "skipped", "未提供 OpenAPI 文档，已跳过业务 API 导入。", {}))

    ontology = None
    if generate_ontology:
        ontology = generate_ontology_draft(platform_db, source.id, ontology_name, domain or source.domain, blueprint_id)
        steps.append(
            _step(
                "generate_ontology",
                "completed",
                f"已生成本体草案: {ontology['name']} v{ontology['version']}",
                {"ontologyId": ontology["id"], "blueprintId": ontology.get("blueprint", {}).get("id")},
            )
        )
    else:
        steps.append(_step("generate_ontology", "skipped", "已按请求跳过本体草案生成。", {}))

    readiness = assess_data_source_readiness(platform_db, source.id)
    steps.append(_step("assess_readiness", "completed", f"接入准备度 {readiness['score']} 分，状态 {readiness['status']}。", readiness["summary"]))
    return {
        "dataSource": source.__dict__,
        "connection": connection,
        "apiGateway": api_gateway,
        "scan": scan,
        "apiImport": api_import,
        "ontology": ontology,
        "readiness": readiness,
        "steps": steps,
        "status": readiness["status"],
    }


def _step(code: str, status: str, message: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "status": status, "message": message, "detail": detail}
