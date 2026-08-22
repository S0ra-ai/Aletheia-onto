"""Workbench aggregation and knowledge graph projection.

Both are read-only projections over existing tables. The property worth pinning
down is that they *agree* with the underlying data: a workbench that reports a
different number than the screen it summarises is worse than no workbench.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.governance import upsert_business_rule
from ontology_platform.graph_view import build_ontology_graph
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.sample_data import create_contract_sample_db
from ontology_platform.workbench import build_workbench


@pytest.fixture
def modelled(tmp_path: Path):
    platform_db = tmp_path / "platform.sqlite3"
    business_db = tmp_path / "business.sqlite3"
    initialize_platform_db(platform_db)
    create_contract_sample_db(business_db)
    source = register_data_source(platform_db, "合同系统", "sqlite", str(business_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)
    return {
        "platform_db": platform_db,
        "source_id": source.id,
        "ontology_id": ontology["ontology"]["id"],
    }


# -- Workbench --


def test_empty_platform_reports_the_first_blocking_step(tmp_path: Path) -> None:
    """With nothing connected, the top item must be "connect a data source"."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    result = build_workbench(platform_db)
    assert result["dataSources"]["total"] == 0
    codes = [item["code"] for item in result["actionItems"]]
    assert codes[0] == "no_data_source"
    assert result["actionItems"][0]["severity"] == "blocker"


def test_workbench_counts_match_the_database(modelled) -> None:
    """The projection must not disagree with the tables it summarises."""
    result = build_workbench(modelled["platform_db"])
    with connect(modelled["platform_db"]) as conn:
        objects = conn.execute("select count(*) as c from business_object").fetchone()["c"]
        tables = conn.execute("select count(*) as c from source_table").fetchone()["c"]
        pending = conn.execute("select count(*) as c from semantic_mapping where status = 'pending'").fetchone()["c"]
    assert result["ontologies"]["objects"] == objects
    assert result["dataSources"]["tables"] == tables
    assert result["governance"]["pendingMappings"] == pending


def test_pending_mappings_are_reported_as_a_release_blocker(modelled) -> None:
    result = build_workbench(modelled["platform_db"])
    codes = [item["code"] for item in result["actionItems"]]
    assert "pending_mappings" in codes
    item = next(i for i in result["actionItems"] if i["code"] == "pending_mappings")
    assert item["severity"] == "blocker"
    assert item["route"] == "/mapping"


def test_objects_without_rules_are_surfaced(modelled) -> None:
    """An object with no rule produces no verdict, which users mistake for a bug."""
    result = build_workbench(modelled["platform_db"])
    assert result["rules"]["objectsWithoutRules"] > 0
    codes = [item["code"] for item in result["actionItems"]]
    assert "no_rules" in codes or "objects_without_rules" in codes


def test_action_items_are_ordered_blockers_first(modelled) -> None:
    result = build_workbench(modelled["platform_db"])
    severities = [item["severity"] for item in result["actionItems"]]
    ranked = ["blocker", "warning", "info"]
    positions = [ranked.index(s) for s in severities]
    assert positions == sorted(positions), severities


def test_every_action_item_names_a_route(modelled) -> None:
    """An item nobody can navigate to is not actionable."""
    for item in build_workbench(modelled["platform_db"])["actionItems"]:
        assert item["route"].startswith("/")
        assert item["title"]
        assert item["detail"]


def test_decision_limit_is_clamped(modelled) -> None:
    result = build_workbench(modelled["platform_db"], decision_limit=9999)
    assert len(result["decisions"]["recent"]) <= 50


# -- Knowledge graph --


def test_graph_nodes_and_edges_come_from_the_ontology(modelled) -> None:
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    assert graph["stats"]["nodeCount"] == len(graph["nodes"])
    assert graph["stats"]["edgeCount"] == len(graph["edges"])
    codes = {node["code"] for node in graph["nodes"]}
    # Every edge must reference nodes that exist, or the view would draw
    # dangling lines.
    for edge in graph["edges"]:
        assert edge["source"] in codes
        assert edge["target"] in codes


def test_edges_carry_the_foreign_key_that_justifies_them(modelled) -> None:
    """relation_type is always "references", so the FK is the real explanation."""
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    assert graph["edges"], "样例数据应至少产生一条关系"
    assert any(edge["foreignKey"] for edge in graph["edges"])


def test_degree_matches_the_edge_list(modelled) -> None:
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    expected: dict[str, int] = {}
    for edge in graph["edges"]:
        expected[edge["source"]] = expected.get(edge["source"], 0) + 1
        expected[edge["target"]] = expected.get(edge["target"], 0) + 1
    for node in graph["nodes"]:
        assert node["degree"] == expected.get(node["code"], 0), node["code"]


def test_objects_without_rules_are_flagged_in_the_graph(modelled) -> None:
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    assert graph["stats"]["objectsWithoutRules"]

    target = graph["stats"]["objectsWithoutRules"][0]
    upsert_business_rule(
        modelled["platform_db"],
        modelled["ontology_id"],
        code="some_rule",
        name="示例规则",
        rule_type="validation",
        scope_object_code=target,
        expression="id != null",
        severity="warning",
        natural_language="标识必须存在。",
        actor="test",
    )
    after = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    assert target not in after["stats"]["objectsWithoutRules"]
    node = next(n for n in after["nodes"] if n["code"] == target)
    assert node["ruleCount"] == 1


def test_isolated_objects_are_reported(modelled) -> None:
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    for code in graph["stats"]["isolatedObjects"]:
        node = next(n for n in graph["nodes"] if n["code"] == code)
        assert node["degree"] == 0


def test_graph_states_the_relation_expressiveness_limitation(modelled) -> None:
    """The view must not imply richer semantics than the model supports."""
    graph = build_ontology_graph(modelled["platform_db"], modelled["ontology_id"])
    assert "references" in graph["notes"]["limitation"]


def test_unknown_ontology_raises(modelled) -> None:
    with pytest.raises(ValueError, match="本体不存在"):
        build_ontology_graph(modelled["platform_db"], 999999)
