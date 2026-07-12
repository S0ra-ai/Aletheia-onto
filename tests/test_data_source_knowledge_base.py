from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.knowledge_base import browse_source_table, build_reasoning_chain, list_knowledge_bases
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.natural_language import query_natural_language
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.sample_data import create_contract_sample_db


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
