from __future__ import annotations

from datetime import date
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.knowledge_base import browse_source_table, build_reasoning_chain, initialize_knowledge_base, list_knowledge_bases
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.natural_language import query_natural_language
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.sample_data import create_contract_sample_db
from ontology_platform.semantic_kernel import SemanticRuntime, assess_instance


def _initialized_source(tmp_path: Path):
    platform_db = tmp_path / "platform.sqlite3"
    source_db = tmp_path / "business.sqlite3"
    initialize_platform_db(platform_db)
    create_contract_sample_db(source_db)
    source = register_data_source(platform_db, "业务知识库", "sqlite", str(source_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    return platform_db, source, ontology


def test_user_can_browse_registered_database_rows(tmp_path: Path) -> None:
    platform_db, source, _ = _initialized_source(tmp_path)

    result = browse_source_table(platform_db, source.id, "contract", limit=2, offset=0)

    assert result["dataSourceId"] == source.id
    assert result["tableName"] == "contract"
    assert result["columns"][0]
    assert len(result["rows"]) == 2
    assert result["rows"][0]["contract_no"].startswith("HT-")
    assert result["page"]["hasMore"] is True


def test_uploaded_rules_appear_in_data_source_reasoning_chain(tmp_path: Path) -> None:
    platform_db, source, ontology = _initialized_source(tmp_path)
    upsert_business_rule(
        platform_db, ontology["id"], "custom_contract_review", "自定义合同复核", "risk",
        "contract", "amount > 500000", "warning", "金额超过 50 万元需要复核。", actor="tester",
    )

    chain = build_reasoning_chain(platform_db, source.id)

    assert chain["initialized"] is True
    assert any(node["code"] == "contract" for node in chain["objects"])
    assert any(rule["code"] == "custom_contract_review" for rule in chain["rules"])
    assert any(step["type"] == "rule_evaluation" for step in chain["steps"])


def test_chat_candidates_only_include_initialized_data_sources(tmp_path: Path) -> None:
    platform_db, source, _ = _initialized_source(tmp_path)
    empty_db = tmp_path / "empty.sqlite3"
    create_contract_sample_db(empty_db)
    register_data_source(platform_db, "未初始化数据源", "sqlite", str(empty_db))

    items = list_knowledge_bases(platform_db)

    assert [item["dataSourceId"] for item in items] == [source.id]
    assert "contract" in items[0]["objectCodes"]


def test_chat_can_answer_knowledge_base_rule_questions(tmp_path: Path) -> None:
    platform_db, source, ontology = _initialized_source(tmp_path)
    upsert_business_rule(
        platform_db, ontology["id"], "manual_review", "人工复核规则", "risk", "contract",
        "amount > 500000", "warning", "大额业务需要人工复核。", actor="tester",
    )

    result = query_natural_language(
        platform_db, "这个数据源的合同有哪些规则？",
        data_source_id=source.id, object_code="contract", use_model=False,
    )

    assert result["intent"] == "knowledge_overview"
    assert "人工复核规则" in result["answer"]
    assert result["resolved"]["dataSourceId"] == source.id
    assert "scopeObjectCode" not in result["answer"]
    assert "->" not in result["answer"]


def test_plural_contract_table_uses_canonical_contract_object_code(tmp_path: Path) -> None:
    import sqlite3

    platform_db = tmp_path / "platform.sqlite3"
    source_db = tmp_path / "plural-contracts.sqlite3"
    with sqlite3.connect(source_db) as conn:
        conn.execute("create table contracts (id integer primary key, contract_no text, total_amount real, status text)")
        conn.execute("insert into contracts values (1, 'CG-2024-001', 120000, 'active')")
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "复数表合同库", "sqlite", str(source_db), domain="合同管理")
    scan_data_source(platform_db, source.id)

    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    assert any(item["code"] == "contract" and item["sourceTable"] == "contracts" for item in ontology["objects"])


def test_local_fallback_answer_uses_business_language(tmp_path: Path) -> None:
    platform_db, source, ontology = _initialized_source(tmp_path)

    result = query_natural_language(
        platform_db, "合同 1 是否合规？", ontology["id"], source.id, use_model=False,
    )

    assert "本体内核" not in result["answer"]
    assert "当前研判为" not in result["answer"]


def test_assessment_serializes_date_values_from_external_sources(tmp_path: Path, monkeypatch) -> None:
    platform_db, source, ontology = _initialized_source(tmp_path)

    def fake_runtime(platform, ontology_id: int, object_code: str, instance_id: str) -> SemanticRuntime:
        record = {
            "id": 1,
            "contract_no": "CG-2024-001",
            "title": "测试合同",
            "amount": 120000,
            "status": "effective",
            "signed_date": date(2024, 1, 15),
        }
        return SemanticRuntime(
            ontology_id=ontology_id,
            ontology_version=ontology["version"],
            object_code=object_code,
            object_name="合同",
            source_table="contract",
            primary_key="id",
            instance_id=instance_id,
            data_source_id=source.id,
            data_source_uri=source.connection_uri,
            record=record,
            context=dict(record),
            related={},
        )

    monkeypatch.setattr("ontology_platform.semantic_kernel.build_runtime", fake_runtime)

    result = assess_instance(platform_db, ontology["id"], "contract", "1")

    assert result["semanticKernel"]["instanceId"] == "1"
    assert result["ruleResults"]


def test_initializing_same_domain_sources_uses_distinct_ontology_names(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    for index in (1, 2):
        source_db = tmp_path / f"contracts-{index}.sqlite3"
        create_contract_sample_db(source_db)
        source = register_data_source(platform_db, f"合同系统{index}", "sqlite", str(source_db), domain="合同管理")
        initialize_knowledge_base(platform_db, source.id)

    names = {item["ontologyName"] for item in list_knowledge_bases(platform_db)}
    assert names == {"合同系统1本体", "合同系统2本体"}
