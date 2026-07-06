from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .metadata import assess_data_source_readiness, list_source_apis
from .database import connect
from .ontology import summarize_ontology


def build_kernel_package(platform_db: Path | str, data_source_id: int, base_url: str = "/") -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        ontology_ids = [
            row["ontology_id"]
            for row in conn.execute(
                """
                select distinct bo.ontology_id
                from business_object bo
                join source_table st on st.id = bo.source_table_id
                where st.data_source_id = ?
                order by bo.ontology_id
                """,
                (data_source_id,),
            ).fetchall()
        ]
        ontologies = [summarize_ontology(conn, ontology_id) for ontology_id in ontology_ids]

    readiness = assess_data_source_readiness(platform_db, data_source_id)
    apis = list_source_apis(platform_db, data_source_id)
    normalized_base = base_url.rstrip("/")
    package = {
        "packageType": "ontology-semantic-kernel",
        "version": "0.1.0",
        "dataSource": {
            "id": source["id"],
            "name": source["name"],
            "domain": source["domain"],
            "systemCategory": source["system_category"],
            "sourceType": source["source_type"],
            "apiBaseUrl": source["api_base_url"],
            "capabilities": json.loads(source["capabilities"] or "[]"),
        },
        "readiness": readiness,
        "ontologies": [_compact_ontology(item) for item in ontologies],
        "operations": [_operation_descriptor(api) for api in apis],
        "runtimeEndpoints": {
            "explain": f"{normalized_base}/semantic/objects/{{objectCode}}/instances/{{instanceId}}/explain?ontologyId={{ontologyId}}",
            "assess": f"{normalized_base}/semantic/objects/{{objectCode}}/instances/{{instanceId}}/assess?ontologyId={{ontologyId}}",
            "preflight": f"{normalized_base}/automation/operations/{{operationCode}}/preflight",
            "execute": f"{normalized_base}/automation/operations/{{operationCode}}/execute",
            "decisions": f"{normalized_base}/governance/decisions",
        },
        "governanceGates": {
            "publishRequiresConfirmedMappings": True,
            "executionRequiresApprovedDecision": True,
            "decisionRecordsEnabled": True,
            "readinessStatus": readiness["status"],
            "blockingGaps": [gap["code"] for gap in readiness["gaps"]],
        },
    }
    return package


def export_kernel_package(platform_db: Path | str, data_source_id: int, base_url: str = "/") -> dict[str, str]:
    package = build_kernel_package(platform_db, data_source_id, base_url)
    return {
        "filename": f"semantic-kernel-datasource-{data_source_id}.json",
        "mediaType": "application/json",
        "content": json.dumps(package, ensure_ascii=False, indent=2),
    }


def _compact_ontology(ontology: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ontology["id"],
        "name": ontology["name"],
        "domain": ontology["domain"],
        "version": ontology["version"],
        "status": ontology["status"],
        "objects": [
            {
                "code": item["code"],
                "name": item["name"],
                "sourceTable": item["sourceTable"],
            }
            for item in ontology["objects"]
        ],
        "relations": [
            {
                "code": item["code"],
                "name": item["name"],
                "sourceCode": item["sourceCode"],
                "targetCode": item["targetCode"],
                "type": item["type"],
            }
            for item in ontology["relations"]
        ],
        "rules": [
            {
                "code": item["code"],
                "name": item["name"],
                "scopeObjectCode": item["scopeObjectCode"],
                "severity": item["severity"],
                "expression": item["expression"],
            }
            for item in ontology["rules"]
        ],
        "mappingCounts": _mapping_counts(ontology["mappings"]),
    }


def _operation_descriptor(api: dict[str, Any]) -> dict[str, Any]:
    return {
        "operationCode": api["operation_code"],
        "name": api["name"],
        "method": api["method"],
        "path": api["path"],
        "semanticAction": api["semantic_action"],
        "requiresPreflight": True,
        "requestSchema": json.loads(api["request_schema"] or "{}"),
        "responseSchema": json.loads(api["response_schema"] or "{}"),
    }


def _mapping_counts(mappings: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"pending": 0, "confirmed": 0, "rejected": 0}
    for mapping in mappings:
        status = mapping["status"]
        counts[status] = counts.get(status, 0) + 1
    return counts
