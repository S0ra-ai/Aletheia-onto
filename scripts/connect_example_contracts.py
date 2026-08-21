from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import DEFAULT_PLATFORM_DB, connect, initialize_platform_db
from ontology_platform.knowledge_base import list_knowledge_bases
from ontology_platform.metadata import register_data_source, register_source_api, scan_data_source
from ontology_platform.ontology import generate_ontology_draft


SOURCE_NAME = "示例 MySQL+Word 合同项目"


def main() -> None:
    database_uri = os.getenv(
        "EXAMPLE_CONTRACT_DATABASE_URI",
        "mysql://root@127.0.0.1:3306/contract_platform?charset=utf8mb4",
    )
    api_base_url = os.getenv("EXAMPLE_CONTRACT_API_URL", "http://127.0.0.1:8010")

    initialize_platform_db(DEFAULT_PLATFORM_DB)
    source = register_data_source(
        DEFAULT_PLATFORM_DB,
        SOURCE_NAME,
        "mysql",
        database_uri,
        domain="合同管理",
        system_category="database+api",
        capabilities=["metadata_scan", "semantic_mapping", "contract_search", "word_download"],
        api_base_url=api_base_url,
    )
    scan = scan_data_source(DEFAULT_PLATFORM_DB, source.id)
    register_source_api(DEFAULT_PLATFORM_DB, source.id, "list_contracts", "查询合同列表", "GET", "/api/contracts", "contract.list")
    register_source_api(DEFAULT_PLATFORM_DB, source.id, "search_contracts", "搜索合同", "GET", "/api/contracts/search", "contract.search")
    register_source_api(DEFAULT_PLATFORM_DB, source.id, "get_contract", "查看合同详情", "GET", "/api/contracts/{id}", "contract.read")
    register_source_api(DEFAULT_PLATFORM_DB, source.id, "download_contract_word", "下载合同Word文件", "GET", "/api/contracts/{id}/word", "contract.download")

    bases = [item for item in list_knowledge_bases(DEFAULT_PLATFORM_DB) if item["dataSourceId"] == source.id]
    ontology = bases[0] if bases else generate_ontology_draft(
        DEFAULT_PLATFORM_DB,
        source.id,
        name="示例合同管理本体",
        domain="合同管理",
        blueprint_id="contract-management",
    )
    with connect(DEFAULT_PLATFORM_DB) as conn:
        contract_object = conn.execute(
            "select code from business_object where ontology_id = ? and source_table_id in "
            "(select id from source_table where data_source_id = ? and table_name = 'contracts')",
            (ontology.get("ontologyId") or ontology.get("id"), source.id),
        ).fetchone()
    if contract_object is None or contract_object["code"] != "contract":
        raise RuntimeError("合同表未正确映射为 contract 业务对象")
    print(f"[ok] 已接入 {SOURCE_NAME}: {len(scan['tables'])} 张表，本体 #{ontology.get('ontologyId') or ontology.get('id')}")


if __name__ == "__main__":
    main()
