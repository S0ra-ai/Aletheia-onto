from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from ontology_platform.database import DEFAULT_PLATFORM_DB, initialize_platform_db
from ontology_platform.metadata import register_data_source, register_source_api, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.sample_data import DEFAULT_SAMPLE_DB, create_contract_sample_db
from ontology_platform.semantic_kernel import assess_instance


def main() -> None:
    initialize_platform_db(DEFAULT_PLATFORM_DB)
    sample_path = create_contract_sample_db(DEFAULT_SAMPLE_DB)
    source = register_data_source(DEFAULT_PLATFORM_DB, "合同管理样例系统", "sqlite", str(sample_path), domain="合同管理", system_category="database+api")
    register_source_api(
        DEFAULT_PLATFORM_DB,
        source.id,
        "submit_contract",
        "提交合同审批",
        "POST",
        "/contracts/{id}/submit",
        "contract.submit_for_approval",
    )
    scan = scan_data_source(DEFAULT_PLATFORM_DB, source.id)
    ontology = generate_ontology_draft(DEFAULT_PLATFORM_DB, source.id)
    assessment = assess_instance(DEFAULT_PLATFORM_DB, ontology["id"], "contract", "1")

    print("已创建合同管理样例库:", sample_path)
    print("已注册数据源:", source)
    print("元数据扫描结果:", scan)
    print("本体草案:", {"id": ontology["id"], "objects": len(ontology["objects"]), "relations": len(ontology["relations"]), "rules": len(ontology["rules"])})
    print("合同 1 语义研判:", assessment["decision"])


if __name__ == "__main__":
    main()
