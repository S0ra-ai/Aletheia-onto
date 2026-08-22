"""Document knowledge layer: citations anchored to the ontology.

The target is the product's core claim, end to end:

    「订单 A123 不满足退款条件，因签收已超 15 天（规则 refund_window_check），
      依据《售后政策》第 3.2 条。」

The first two clauses already worked. These tests prove the third now does, and
that it stays *attributable* rather than merely similar -- an unanchored passage
must never appear as judgement evidence.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.knowledge_documents import (
    ingest_document,
    init_knowledge_schema,
    list_documents,
    list_entries,
    load_confirmed_entries,
    review_knowledge_entry,
    split_into_chunks,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.natural_language import query_natural_language
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.retrieval import (
    bm25_rank,
    hashed_embedding,
    register_retrieval_backend,
    retrieve,
    supported_retrieval_backends,
    tokenize,
)

POLICY_TEXT = """售后政策

第1条 适用范围
本政策适用于平台全部零售订单。

第3.2条 退款时限
客户应在签收后 15 天内提出退款申请；签收已超过 15 天的订单不予受理退款。

第4.1条 发票处理
发票一经开具不可撤销，如需换开须先作废原发票。
"""


# -- Chunking --


def test_clause_numbers_become_citations() -> None:
    """A citation is only useful if it points at something a person can find."""
    parsed = split_into_chunks(POLICY_TEXT, title="售后政策")
    citations = [chunk.citation for chunk in parsed.chunks]
    assert "第3.2条" in citations, citations
    assert "第4.1条" in citations, citations


def test_refund_clause_text_stays_with_its_citation() -> None:
    parsed = split_into_chunks(POLICY_TEXT, title="售后政策")
    clause = next(c for c in parsed.chunks if c.citation == "第3.2条")
    assert "15 天" in clause.text
    assert "不予受理" in clause.text
    # Must not bleed into the neighbouring clause.
    assert "发票" not in clause.text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("第 5 条 违约责任\n任何一方违约应赔偿损失。", "第5条"),
        ("3.1 交付时间\n卖方应于三十日内交付。", "3.1"),
        ("一、总则\n本合同经双方签字生效。", "第一条"),
        ("Article 7 Termination\nEither party may terminate with notice.", "Article 7"),
    ],
)
def test_multiple_numbering_conventions_are_recognised(text, expected) -> None:
    """Structural numbering patterns, not business vocabulary (ADR-0003)."""
    parsed = split_into_chunks(text)
    assert any(chunk.citation == expected for chunk in parsed.chunks), [c.citation for c in parsed.chunks]


def test_unnumbered_document_falls_back_to_positional_citations() -> None:
    text = "这是第一段内容，描述了平台的基本服务承诺条款。\n这是第二段内容，说明了退换货的一般处理原则。"
    parsed = split_into_chunks(text)
    assert parsed.chunks
    assert all("段" in chunk.citation for chunk in parsed.chunks)
    assert any("未识别到条款编号" in warning for warning in parsed.warnings)


def test_empty_document_is_reported_not_silently_accepted() -> None:
    parsed = split_into_chunks("   \n\n  ")
    assert parsed.chunks == []
    assert parsed.warnings


# -- Tokenization and ranking --


def test_cjk_is_tokenized_into_bigrams() -> None:
    """Chinese has no delimiters, so 「退款」 must match 「退款条件」."""
    tokens = tokenize("退款条件")
    assert "退款" in tokens
    assert "款条" in tokens


def test_ascii_terms_are_kept_whole_and_lowercased() -> None:
    assert "refund_window_check" in tokenize("Refund_Window_Check")


def test_bm25_ranks_the_relevant_clause_first() -> None:
    entries = [
        {"id": 1, "content": "发票一经开具不可撤销。", "citation": "第4.1条", "tokenSummary": {}},
        {
            "id": 2,
            "content": "客户应在签收后 15 天内提出退款申请；超过 15 天不予受理。",
            "citation": "第3.2条",
            "tokenSummary": {},
        },
    ]
    hits = bm25_rank("退款 超过 15 天", entries, limit=2)
    assert hits, "应至少命中一条"
    assert hits[0].citation == "第3.2条"


def test_irrelevant_entries_score_zero_and_are_dropped() -> None:
    entries = [{"id": 1, "content": "本政策适用于零售订单。", "citation": "第1条", "tokenSummary": {}}]
    assert bm25_rank("发票 换开 流程", entries) == []


def test_embedding_is_deterministic() -> None:
    """Reproducibility matters for tests and screenshots."""
    assert hashed_embedding("退款条件") == hashed_embedding("退款条件")
    assert hashed_embedding("退款条件") != hashed_embedding("发票处理")


def test_retrieval_backends_are_registered_and_replaceable() -> None:
    assert "bm25" in supported_retrieval_backends()
    saved = dict(__import__("ontology_platform.retrieval", fromlist=["x"]).RETRIEVAL_REGISTRY.snapshot())
    try:
        register_retrieval_backend("stub", lambda q, entries, limit: [])
        assert "stub" in supported_retrieval_backends()
        assert retrieve("anything", [{"id": 1, "content": "x"}], backend="stub") == []
    finally:
        __import__("ontology_platform.retrieval", fromlist=["x"]).RETRIEVAL_REGISTRY.restore(saved)


# -- Ingest, governance, retrieval --


@pytest.fixture
def ontology_with_rule(tmp_path: Path):
    platform_db = tmp_path / "platform.sqlite3"
    business_db = tmp_path / "business.sqlite3"
    initialize_platform_db(platform_db)

    conn = sqlite3.connect(business_db)
    conn.executescript(
        """
        create table sales_order (
            id integer primary key,
            order_no text not null,
            received_days integer not null
        );
        insert into sales_order values (1, 'A123', 24);
        """
    )
    conn.commit()
    conn.close()

    source = register_data_source(platform_db, "订单系统", "sqlite", str(business_db), domain="订单管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    ontology_id = ontology["ontology"]["id"]

    with connect(platform_db) as conn2:
        init_knowledge_schema(conn2)

    upsert_business_rule(
        platform_db,
        ontology_id,
        code="refund_window_check",
        name="退款时限检查",
        rule_type="validation",
        scope_object_code="sales_order",
        expression="received_days <= 15",
        severity="blocking",
        natural_language="签收后 15 天内才可退款。",
        actor="test",
    )
    return {"platform_db": platform_db, "ontology_id": ontology_id, "source_id": source.id}


def test_ingest_creates_pending_entries(ontology_with_rule) -> None:
    """Nothing becomes judgement evidence without review."""
    result = ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
        object_code="sales_order",
    )
    assert result["chunkCount"] >= 3
    assert result["status"] == "pending"
    entries = list_entries(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"])
    assert entries
    assert all(entry["status"] == "pending" for entry in entries)


def test_pending_entries_are_not_retrievable(ontology_with_rule) -> None:
    ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
        object_code="sales_order",
    )
    with connect(ontology_with_rule["platform_db"]) as conn:
        assert load_confirmed_entries(conn, ontology_with_rule["ontology_id"]) == []


def test_confirming_requires_an_anchor(ontology_with_rule) -> None:
    """A confirmed entry with no anchor would be free-floating text."""
    ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
    )
    entry = list_entries(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"])[0]
    with pytest.raises(ValueError, match="必须指定锚定"):
        review_knowledge_entry(ontology_with_rule["platform_db"], entry["id"], "confirmed", reviewer="tester")


def test_review_can_correct_the_anchor(ontology_with_rule) -> None:
    ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
    )
    entries = list_entries(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"])
    clause = next(e for e in entries if e["citation"] == "第3.2条")
    review_knowledge_entry(
        ontology_with_rule["platform_db"],
        clause["id"],
        "confirmed",
        object_code="sales_order",
        rule_code="refund_window_check",
        reviewer="tester",
    )
    with connect(ontology_with_rule["platform_db"]) as conn:
        confirmed = load_confirmed_entries(conn, ontology_with_rule["ontology_id"])
    assert len(confirmed) == 1
    assert confirmed[0]["ruleCode"] == "refund_window_check"


def test_duplicate_upload_is_refused(ontology_with_rule) -> None:
    args = (
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
    )
    ingest_document(*args)
    with pytest.raises(ValueError, match="已导入"):
        ingest_document(*args)


def test_anchor_narrows_candidates_before_ranking(ontology_with_rule) -> None:
    """The ordering in ADR-0009: anchor first, similarity second."""
    ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
    )
    entries = list_entries(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"])
    for entry in entries:
        rule = "refund_window_check" if entry["citation"] == "第3.2条" else ""
        review_knowledge_entry(
            ontology_with_rule["platform_db"],
            entry["id"],
            "confirmed",
            object_code="sales_order",
            rule_code=rule,
            reviewer="tester",
        )

    with connect(ontology_with_rule["platform_db"]) as conn:
        rule_only = load_confirmed_entries(conn, ontology_with_rule["ontology_id"], rule_codes=["refund_window_check"])
    assert len(rule_only) == 1
    assert rule_only[0]["citation"] == "第3.2条"


def test_document_status_follows_its_entries(ontology_with_rule) -> None:
    result = ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
    )
    for entry in list_entries(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"]):
        review_knowledge_entry(
            ontology_with_rule["platform_db"],
            entry["id"],
            "confirmed",
            object_code="sales_order",
            reviewer="tester",
        )
    documents = list_documents(ontology_with_rule["platform_db"], ontology_with_rule["ontology_id"])
    document = next(d for d in documents if d["id"] == result["documentId"])
    assert document["status"] == "confirmed"
    assert document["pendingCount"] == 0


# -- The moat sentence, end to end --


def test_verdict_cites_the_clause_behind_the_failed_rule(ontology_with_rule) -> None:
    """All three clauses of the product claim in one answer."""
    platform_db = ontology_with_rule["platform_db"]
    ontology_id = ontology_with_rule["ontology_id"]

    ingest_document(platform_db, ontology_id, "售后政策", POLICY_TEXT)
    for entry in list_entries(platform_db, ontology_id):
        review_knowledge_entry(
            platform_db,
            entry["id"],
            "confirmed",
            object_code="sales_order",
            rule_code="refund_window_check" if entry["citation"] == "第3.2条" else "",
            reviewer="tester",
        )

    result = query_natural_language(
        platform_db,
        "Sales Order 1 是否满足退款条件？",
        ontology_id,
        ontology_with_rule["source_id"],
        use_model=False,
    )
    answer = result["answer"]

    # Verdict, from the rule engine.
    assert "还不适合直接通过" in answer, answer
    # Governing rule, by code.
    assert "refund_window_check" in answer, answer
    # Textual authority, by citation.
    assert "第3.2条" in answer, answer
    assert "售后政策" in answer, answer
    # And the structured evidence carries it for auditing.
    citations = result["evidence"].get("citations", [])
    assert citations and citations[0]["citation"] == "第3.2条", citations


def test_verdict_still_works_without_any_knowledge_entries(ontology_with_rule) -> None:
    """A deployment with no documents must still get its verdict."""
    result = query_natural_language(
        ontology_with_rule["platform_db"],
        "Sales Order 1 是否满足退款条件？",
        ontology_with_rule["ontology_id"],
        ontology_with_rule["source_id"],
        use_model=False,
    )
    assert "还不适合直接通过" in result["answer"]
    assert "citations" not in result["evidence"]


def test_unconfirmed_clause_is_never_cited(ontology_with_rule) -> None:
    """The governance guarantee: pending text cannot become evidence."""
    ingest_document(
        ontology_with_rule["platform_db"],
        ontology_with_rule["ontology_id"],
        "售后政策",
        POLICY_TEXT,
        object_code="sales_order",
        rule_code="refund_window_check",
    )
    result = query_natural_language(
        ontology_with_rule["platform_db"],
        "Sales Order 1 是否满足退款条件？",
        ontology_with_rule["ontology_id"],
        ontology_with_rule["source_id"],
        use_model=False,
    )
    assert "第3.2条" not in result["answer"]
    assert "citations" not in result["evidence"]


def test_published_ontology_rejects_new_documents(ontology_with_rule) -> None:
    from ontology_platform.governance import list_semantic_mappings, publish_ontology, review_semantic_mapping

    platform_db = ontology_with_rule["platform_db"]
    ontology_id = ontology_with_rule["ontology_id"]
    for mapping in list_semantic_mappings(platform_db, ontology_id)["items"]:
        review_semantic_mapping(platform_db, mapping["id"], "confirmed", "tester", "")
    publish_ontology(platform_db, ontology_id, "tester", force=True)

    with pytest.raises(ValueError, match="已发布"):
        ingest_document(platform_db, ontology_id, "新政策", POLICY_TEXT)


# -- API surface --


def test_knowledge_endpoints_require_the_right_capabilities() -> None:
    """Ingesting is authoring; confirming evidence is a governance review."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("POST", "/ontologies/1/knowledge/documents") == "platform:write"
    assert required_capability("POST", "/knowledge/entries/5/review") == "governance:review"
    assert required_capability("GET", "/ontologies/1/knowledge/entries") == "platform:read"


def test_knowledge_schema_is_created_at_startup(tmp_path: Path) -> None:
    """The tables are optional, so startup must create them explicitly."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        init_knowledge_schema(conn)
        # Idempotent: startup runs on every boot.
        init_knowledge_schema(conn)
        tables = {row["name"] for row in conn.execute("select name from sqlite_master where type = 'table'").fetchall()}
    assert {"knowledge_document", "knowledge_entry"} <= tables
