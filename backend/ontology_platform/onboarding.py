from __future__ import annotations

from pathlib import Path
from typing import Any

from .metadata import assess_data_source_readiness, check_data_source_connection, register_data_source, scan_data_source
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
            "scan": None,
            "ontology": None,
            "readiness": readiness,
            "steps": steps,
            "status": "blocked",
        }

    scan = scan_data_source(platform_db, source.id)
    steps.append(_step("scan_metadata", "completed", f"已扫描 {len(scan['tables'])} 张表。", scan))

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
        "scan": scan,
        "ontology": ontology,
        "readiness": readiness,
        "steps": steps,
        "status": readiness["status"],
    }


def _step(code: str, status: str, message: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"code": code, "status": status, "message": message, "detail": detail}
