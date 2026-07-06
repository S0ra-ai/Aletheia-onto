from __future__ import annotations

import json
import sqlite3
from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
import ontology_platform.automation as automation_module
from ontology_platform.automation import execute_operation, preflight_operation
from ontology_platform.coverage import build_semantic_coverage
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.decisions import list_decisions
from ontology_platform.governance import (
    bulk_review_semantic_mappings,
    derive_ontology_version,
    list_business_rules,
    list_semantic_mappings,
    publish_ontology,
    review_semantic_mapping,
    upsert_business_rule,
)
from ontology_platform.industry_blueprints import infer_industry_blueprint, list_industry_blueprints, upsert_industry_blueprint
from ontology_platform.kernel_package import build_kernel_package, export_kernel_package
from ontology_platform.metadata import analyze_schema_drift, assess_data_source_readiness, check_data_source_connection, import_openapi_operations, list_data_sources, list_source_apis, register_data_source, register_source_api, scan_data_source
from ontology_platform.model_client import OpenRouterClient, OpenRouterConfig, generate_blueprint_draft, get_model_config, reset_model_config, update_model_config
from ontology_platform.onboarding import run_onboarding_pipeline
from ontology_platform.operation_bindings import assess_operation_bindings
from ontology_platform.ontology import export_ontology_asset, explain_instance, generate_ontology_draft, list_ontologies
from ontology_platform.release_readiness import assess_ontology_release_readiness
from ontology_platform.sample_data import create_contract_sample_db, create_equipment_sample_db
from ontology_platform.semantic_kernel import assess_decision_consistency, assess_instance, list_instance_ids


def test_metadata_to_ontology_flow(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan = scan_data_source(platform_db, source.id)

    assert len(scan["tables"]) == 4

    ontology = generate_ontology_draft(platform_db, source.id)
    object_codes = {item["code"] for item in ontology["objects"]}
    assert {"contract", "customer", "payment_plan", "invoice"}.issubset(object_codes)
    assert len(ontology["relations"]) >= 3
    assert any(rule["code"] == "blacklist_customer_warning" for rule in ontology["rules"])

    explanation = explain_instance(platform_db, ontology["id"], "contract", "1")
    assert explanation["object"]["name"] == "合同"
    values = {item["attributeCode"]: item["value"] for item in explanation["attributes"]}
    assert values["contract_no"] == "HT-2026-001"
    assert values["amount"] == 1200000

    assessment = assess_instance(platform_db, ontology["id"], "contract", "3")
    assert assessment["decision"]["status"] == "review"
    failed_rules = {item["ruleCode"] for item in assessment["ruleResults"] if not item["passed"]}
    assert {"blacklist_customer_warning", "payment_plan_amount_match"}.issubset(failed_rules)

    preflight = preflight_operation(platform_db, ontology["id"], source.id, "submit_contract", "3")
    assert preflight["allowed"] is False
    assert preflight["nextAction"] == "route_to_human_review"


def test_operation_execution_respects_semantic_preflight(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    ready = execute_operation(
        platform_db,
        ontology["id"],
        source.id,
        "submit_contract",
        "1",
        payload={"comment": "自动提交"},
        actor="测试用户",
    )
    assert ready["status"] == "ready_for_execution"
    assert ready["executed"] is False
    assert ready["preflight"]["allowed"] is True
    assert ready["preflight"]["decision"]["decisionId"].startswith("DR-")
    assert ready["decisionRecord"]["decisionId"].startswith("DR-")
    assert ready["execution"]["path"] == "/contracts/1/submit"
    assert ready["execution"]["payload"] == {"comment": "自动提交"}

    blocked = execute_operation(platform_db, ontology["id"], source.id, "submit_contract", "3", actor="测试用户")
    assert blocked["status"] == "blocked_by_semantic_kernel"
    assert blocked["executed"] is False
    assert blocked["preflight"]["allowed"] is False
    assert blocked["decisionRecord"]["decisionType"] == "operation_execution"

    with connect(platform_db) as conn:
        audit_count = conn.execute(
            "select count(*) from audit_log where action = 'execute_operation'"
        ).fetchone()[0]
    assert audit_count == 2

    decisions = list_decisions(platform_db, 10)
    decision_types = [item["decisionType"] for item in decisions]
    assert decision_types.count("instance_assessment") == 2
    assert decision_types.count("operation_preflight") == 2
    assert decision_types.count("operation_execution") == 2


def test_real_operation_execution_uses_business_api_base_url(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(
        platform_db,
        "合同管理样例系统",
        "sqlite",
        str(legacy_db),
        domain="合同管理",
        system_category="database+api",
        api_base_url="https://legacy.example/api",
    )
    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")
    calls: list[dict[str, object]] = []

    def fake_invoke(base_url: str, execution_plan: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        calls.append({"baseUrl": base_url, "plan": execution_plan, "timeout": timeout_seconds})
        return {"statusCode": 200, "body": {"accepted": True}}

    original_invoke = automation_module._invoke_http_operation
    automation_module._invoke_http_operation = fake_invoke
    try:
        result = execute_operation(
            platform_db,
            ontology["id"],
            source.id,
            "submit_contract",
            "1",
            payload={"comment": "自动提交"},
            actor="测试用户",
            dry_run=False,
            timeout_seconds=7,
        )
    finally:
        automation_module._invoke_http_operation = original_invoke

    assert result["status"] == "executed"
    assert result["executed"] is True
    assert calls[0]["baseUrl"] == "https://legacy.example/api"
    assert calls[0]["timeout"] == 7
    assert calls[0]["plan"]["path"] == "/contracts/1/submit"
    assert result["execution"]["remote"]["body"] == {"accepted": True}


def test_decision_consistency_batch_assesses_samples_and_reports_rule_distribution(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    instance_ids = list_instance_ids(platform_db, ontology["id"], "contract", 2)
    assert [str(item) for item in instance_ids] == ["1", "2"]

    report = assess_decision_consistency(platform_db, ontology["id"], "contract", limit=3)

    assert report["objectCode"] == "contract"
    assert report["sampleSize"] == 3
    assert report["assessed"] == 3
    assert report["summary"]["approved"] == 2
    assert report["summary"]["review"] == 1
    assert report["status"] == "mixed"
    assert {item["instanceId"] for item in report["items"]} == {"1", "2", "3"}
    assert report["ruleFailures"][0]["ruleCode"] in {"blacklist_customer_warning", "payment_plan_amount_match"}
    assert report["nextActions"]

    explicit = assess_decision_consistency(platform_db, ontology["id"], "contract", ["1", "missing"], 10)
    assert explicit["assessed"] == 1
    assert explicit["errorCount"] == 1
    assert explicit["status"] == "incomplete"

    with connect(platform_db) as conn:
        audit_count = conn.execute(
            "select count(*) from audit_log where action = 'assess_decision_consistency'"
        ).fetchone()[0]
    assert audit_count == 2


def test_data_source_readiness_identifies_onboarding_gaps(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")

    initial = assess_data_source_readiness(platform_db, source.id)
    assert initial["status"] == "blocked"
    assert initial["summary"]["tables"] == 0
    assert {"metadata_scan", "ontology", "business_apis"}.issubset({item["code"] for item in initial["gaps"]})

    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")
    reviewed = assess_data_source_readiness(platform_db, source.id)

    assert reviewed["score"] >= 65
    assert reviewed["status"] == "partial"
    assert reviewed["summary"]["tables"] == 4
    assert reviewed["summary"]["apis"] == 1
    assert reviewed["summary"]["ontologies"] == 1
    assert reviewed["summary"]["pendingMappings"] > 0
    assert any(item["code"] == "mapping_governance" for item in reviewed["gaps"])

    bulk_review_semantic_mappings(platform_db, ontology["id"], "confirmed", "业务专家", "接入准备度验证")
    ready = assess_data_source_readiness(platform_db, source.id)
    assert ready["score"] == 100
    assert ready["status"] == "ready"
    assert ready["gaps"] == []


def test_onboarding_pipeline_registers_scans_generates_ontology_and_reports_readiness(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)

    result = run_onboarding_pipeline(
        platform_db,
        "合同管理一键接入",
        "sqlite",
        str(legacy_db),
        domain="合同管理",
        system_category="database+api",
        blueprint_id="contract-management",
    )

    assert result["connection"]["reachable"] is True
    assert result["scan"]["tables"]
    assert result["ontology"]["blueprint"]["id"] == "contract-management"
    assert result["readiness"]["summary"]["tables"] == 4
    assert result["status"] == "partial"
    assert [step["code"] for step in result["steps"]] == [
        "register_data_source",
        "test_connection",
        "scan_metadata",
        "generate_ontology",
        "assess_readiness",
    ]


def test_onboarding_pipeline_stops_when_connection_fails(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    result = run_onboarding_pipeline(
        platform_db,
        "不存在的传统系统",
        "sqlite",
        str(tmp_path / "missing.sqlite3"),
        domain="通用业务",
    )

    assert result["status"] == "blocked"
    assert result["connection"]["reachable"] is False
    assert result["scan"] is None
    assert result["ontology"] is None
    assert [step["code"] for step in result["steps"]] == ["register_data_source", "test_connection"]


def test_openapi_import_registers_business_operations(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同 API 系统", "sqlite", str(legacy_db), domain="合同管理", system_category="database+api")
    spec = {
        "openapi": "3.0.0",
        "paths": {
            "/contracts/{id}/submit": {
                "post": {
                    "operationId": "submit_contract",
                    "summary": "提交合同审批",
                    "x-semantic-action": "contract.submit_for_approval",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {"comment": {"type": "string"}}}
                            }
                        }
                    },
                    "responses": {"200": {"content": {"application/json": {"schema": {"type": "object"}}}}},
                }
            },
            "/contracts/{id}/archive": {
                "post": {
                    "summary": "归档合同",
                    "responses": {"202": {"description": "accepted"}},
                }
            },
        },
    }

    result = import_openapi_operations(platform_db, source.id, spec)
    apis = list_source_apis(platform_db, source.id)

    assert result["count"] == 2
    assert {api["operation_code"] for api in apis} == {"submit_contract", "post_contracts_id_archive"}
    submit = next(api for api in apis if api["operation_code"] == "submit_contract")
    archive = next(api for api in apis if api["operation_code"] == "post_contracts_id_archive")
    assert submit["semantic_action"] == "contract.submit_for_approval"
    assert json.loads(submit["request_schema"])["properties"]["comment"]["type"] == "string"
    assert archive["semantic_action"].startswith("archive.")

    readiness = assess_data_source_readiness(platform_db, source.id)
    assert readiness["summary"]["apis"] == 2


def test_kernel_package_exports_installable_semantic_kernel_manifest(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理语义内核系统", "sqlite", str(legacy_db), domain="合同管理", system_category="database+api")
    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    package = build_kernel_package(platform_db, source.id, "https://kernel.example/api")
    asset = export_kernel_package(platform_db, source.id, "https://kernel.example/api")

    assert package["packageType"] == "ontology-semantic-kernel"
    assert package["dataSource"]["id"] == source.id
    assert package["readiness"]["summary"]["tables"] == 4
    assert package["ontologies"][0]["id"] == ontology["id"]
    assert any(item["code"] == "contract" for item in package["ontologies"][0]["objects"])
    assert any(rule["code"] == "blacklist_customer_warning" for rule in package["ontologies"][0]["rules"])
    assert package["operations"][0]["operationCode"] == "submit_contract"
    assert package["operations"][0]["requiresPreflight"] is True
    assert package["runtimeEndpoints"]["execute"] == "https://kernel.example/api/automation/operations/{operationCode}/execute"
    assert package["governanceGates"]["executionRequiresApprovedDecision"] is True
    assert asset["filename"] == f"semantic-kernel-datasource-{source.id}.json"
    assert json.loads(asset["content"])["packageType"] == "ontology-semantic-kernel"


def test_semantic_coverage_reports_object_rule_mapping_and_operation_readiness(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")

    not_modeled = build_semantic_coverage(platform_db, source.id)
    assert not_modeled["status"] == "not_modeled"
    assert not_modeled["score"] == 0

    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    pending = build_semantic_coverage(platform_db, source.id)
    contract_pending = next(item for item in pending["objects"] if item["objectCode"] == "contract")
    assert pending["status"] in {"partial", "blocked"}
    assert contract_pending["pendingMappings"] > 0
    assert contract_pending["ruleCount"] > 0
    assert contract_pending["operationCount"] == 1
    assert contract_pending["automationReady"] is False

    bulk_review_semantic_mappings(platform_db, ontology["id"], "confirmed", "业务专家", "语义覆盖度验证")

    ready = build_semantic_coverage(platform_db, source.id)
    contract_ready = next(item for item in ready["objects"] if item["objectCode"] == "contract")
    assert ready["score"] > pending["score"]
    assert ready["summary"]["confirmedMappings"] > 0
    assert ready["summary"]["semanticOperations"] == 1
    assert ready["summary"]["fullyCoveredObjects"] >= 1
    assert contract_ready["automationReady"] is True
    assert any(item["operationCode"] == "submit_contract" for item in contract_ready["operations"])


def test_operation_binding_assessment_validates_semantic_actions_against_ontology_objects(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    register_source_api(platform_db, source.id, "submit_contract", "提交合同审批", "POST", "/contracts/{id}/submit", "contract.submit_for_approval")
    register_source_api(platform_db, source.id, "archive_case", "归档案件", "POST", "/cases/{id}/archive", "case.archive")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")
    bulk_review_semantic_mappings(platform_db, ontology["id"], "confirmed", "业务专家", "API 绑定验证")

    bindings = assess_operation_bindings(platform_db, source.id)
    submit = next(item for item in bindings["items"] if item["operationCode"] == "submit_contract")
    archive = next(item for item in bindings["items"] if item["operationCode"] == "archive_case")

    assert bindings["status"] == "partial"
    assert bindings["summary"]["operations"] == 2
    assert bindings["summary"]["readyOperations"] == 1
    assert bindings["summary"]["unboundOperations"] == 1
    assert submit["status"] == "ready"
    assert submit["automationReady"] is True
    assert archive["status"] == "unbound"
    assert "未绑定到当前数据源本体对象" in archive["gaps"][0]


def test_industry_blueprints_seed_ontology_names_mappings_and_rules(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_equipment.sqlite3"

    blueprints = list_industry_blueprints()
    assert {item["id"] for item in blueprints}.issuperset({"contract-management", "equipment-maintenance", "generic-enterprise"})
    assert infer_industry_blueprint(["equipment", "work_order"]).id == "equipment-maintenance"

    initialize_platform_db(platform_db)
    create_equipment_sample_db(legacy_db)
    source = register_data_source(platform_db, "设备运维生产系统", "sqlite", str(legacy_db), domain="设备运维")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="equipment-maintenance")

    assert ontology["blueprint"]["id"] == "equipment-maintenance"
    assert any(item["code"] == "equipment" and item["name"] == "设备" for item in ontology["objects"])
    assert any(item["code"] == "criticality" and item["name"] == "重要等级" for item in ontology["attributes"])
    assert any(rule["code"] == "critical_equipment_open_fault" for rule in ontology["rules"])
    assert any("设备运维蓝图" in mapping["evidence"] and mapping["confidence"] >= 0.92 for mapping in ontology["mappings"])

    try:
        generate_ontology_draft(platform_db, source.id, name="不存在蓝图本体", blueprint_id="missing-blueprint")
    except ValueError as error:
        assert "行业蓝图不存在" in str(error)
    else:
        raise AssertionError("不存在的行业蓝图应被拒绝")


def test_custom_industry_blueprint_can_be_imported_and_used_for_generation(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_equipment.sqlite3"

    initialize_platform_db(platform_db)
    create_equipment_sample_db(legacy_db)
    blueprint = upsert_industry_blueprint(
        platform_db,
        {
            "id": "lab-asset",
            "name": "实验室资产蓝图",
            "domain": "实验室资产",
            "description": "覆盖实验室设备资产管理。",
            "objectHints": {"equipment": "实验设备"},
            "attributeHints": {"equipment_code": "资产编号", "criticality": "资产等级"},
            "rules": [
                {
                    "code": "lab_asset_code_required",
                    "name": "资产编号必填",
                    "rule_type": "validation",
                    "scope_object_code": "equipment",
                    "expression": "equipment_code != null",
                    "severity": "blocking",
                    "natural_language": "实验设备必须具备资产编号。",
                }
            ],
            "tableKeywords": ["equipment"],
            "capabilityTags": ["asset-governance"],
        },
    )
    assert blueprint["source"] == "custom"
    assert any(item["id"] == "lab-asset" for item in list_industry_blueprints(platform_db))
    assert infer_industry_blueprint(["equipment"], platform_db=platform_db).id == "lab-asset"

    source = register_data_source(platform_db, "实验室资产系统", "sqlite", str(legacy_db), domain="实验室资产")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="lab-asset")

    assert ontology["blueprint"]["id"] == "lab-asset"
    assert any(item["code"] == "equipment" and item["name"] == "实验设备" for item in ontology["objects"])
    assert any(item["code"] == "equipment_code" and item["name"] == "资产编号" for item in ontology["attributes"])
    assert any(rule["code"] == "lab_asset_code_required" for rule in ontology["rules"])


def test_mapping_review_and_publish_governance_flow(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)

    mappings = list_semantic_mappings(platform_db, ontology["id"])
    assert mappings["items"]
    assert {item["status"] for item in mappings["items"]} == {"pending"}

    initial_release = assess_ontology_release_readiness(platform_db, ontology["id"])
    assert initial_release["status"] == "blocked"
    assert any(item["code"] == "pending_mappings" and not item["passed"] for item in initial_release["gates"])

    first_mapping_id = mappings["items"][0]["id"]
    reviewed = review_semantic_mapping(platform_db, first_mapping_id, "confirmed", "业务专家", "表对象映射正确")
    assert reviewed["status"] == "confirmed"
    assert reviewed["reviewer"] == "业务专家"

    try:
        publish_ontology(platform_db, ontology["id"], "架构师")
    except ValueError as error:
        assert "待审核" in str(error)
    else:
        raise AssertionError("存在待审核映射时不应发布本体")

    bulk = bulk_review_semantic_mappings(platform_db, ontology["id"], "confirmed", "业务专家", "MVP 批量确认")
    assert bulk["reviewedCount"] == len(mappings["items"]) - 1

    reviewed_release = assess_ontology_release_readiness(platform_db, ontology["id"])
    assert reviewed_release["status"] in {"ready", "review"}
    assert reviewed_release["summary"]["confirmedMappings"] == len(mappings["items"])
    assert reviewed_release["summary"]["blockers"] == 0
    assert any(item["code"] == "data_source_1_schema_drift" and item["passed"] for item in reviewed_release["gates"])

    custom_rule = upsert_business_rule(
        platform_db,
        ontology["id"],
        "contract_title_required",
        "合同标题不能为空",
        "validation",
        "contract",
        "title != null",
        "blocking",
        "合同标题不能为空。",
        "规则管理员",
    )
    assert custom_rule["code"] == "contract_title_required"
    assert any(rule["code"] == "contract_title_required" for rule in list_business_rules(platform_db, ontology["id"])["items"])

    published = publish_ontology(platform_db, ontology["id"], "架构师")
    assert published["status"] == "published"
    assert published["mappingCounts"]["confirmed"] == len(mappings["items"])

    try:
        generate_ontology_draft(platform_db, source.id)
    except ValueError as error:
        assert "本体版本已发布" in str(error)
    else:
        raise AssertionError("已发布本体版本不应被重新生成草案覆盖")

    try:
        review_semantic_mapping(platform_db, first_mapping_id, "rejected", "业务专家", "发布后尝试修改")
    except ValueError as error:
        assert "已发布本体" in str(error)
    else:
        raise AssertionError("发布后的语义映射不应允许直接修改")

    try:
        upsert_business_rule(
            platform_db,
            ontology["id"],
            "contract_title_required",
            "合同标题不能为空",
            "validation",
            "contract",
            "title != null",
            "blocking",
            "合同标题不能为空。",
            "规则管理员",
        )
    except ValueError as error:
        assert "已发布本体" in str(error)
    else:
        raise AssertionError("发布后的规则不应允许直接修改")

    derived = derive_ontology_version(platform_db, ontology["id"], "0.2.0", "架构师")
    assert derived["status"] == "draft"
    assert derived["version"] == "0.2.0"
    assert derived["sourceOntologyId"] == ontology["id"]
    assert derived["mappingCount"] == len(mappings["items"])

    derived_mappings = list_semantic_mappings(platform_db, derived["id"])
    assert {item["status"] for item in derived_mappings["items"]} == {"pending"}
    assert all("需重新审核" in item["evidence"] for item in derived_mappings["items"])

    derived_rule = upsert_business_rule(
        platform_db,
        derived["id"],
        "contract_title_required",
        "合同标题不能为空",
        "validation",
        "contract",
        "title != null",
        "blocking",
        "合同标题不能为空。",
        "规则管理员",
    )
    assert derived_rule["code"] == "contract_title_required"

    try:
        derive_ontology_version(platform_db, derived["id"], "0.3.0", "架构师")
    except ValueError as error:
        assert "已发布本体" in str(error)
    else:
        raise AssertionError("不应从未发布草案派生新版本")


def test_scan_records_column_profile(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)

    with connect(platform_db) as conn:
        status = conn.execute(
            """
            select sc.*
            from source_column sc
            join source_table st on st.id = sc.source_table_id
            where st.table_name = 'contract' and sc.column_name = 'status'
            """
        ).fetchone()

    assert status is not None
    assert status["enum_candidate"] == 1
    assert status["distinct_count"] == 3


def test_schema_drift_analysis_compares_live_database_with_scanned_baseline(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")

    not_scanned = analyze_schema_drift(platform_db, source.id)
    assert not_scanned["status"] == "not_scanned"
    assert not_scanned["nextActions"]

    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id, blueprint_id="contract-management")

    stable = analyze_schema_drift(platform_db, source.id)
    assert stable["status"] == "no_drift"
    assert stable["summary"]["changedTables"] == 0

    with sqlite3.connect(legacy_db) as conn:
        conn.execute("alter table contract add column risk_level text")
        conn.execute(
            """
            create table contract_attachment (
                id integer primary key,
                contract_id integer not null,
                file_name text not null,
                foreign key(contract_id) references contract(id)
            )
            """
        )

    drift = analyze_schema_drift(platform_db, source.id)

    assert drift["status"] == "drift_detected"
    assert drift["summary"]["addedTables"] == 1
    assert drift["summary"]["changedTables"] == 1
    assert drift["summary"]["addedColumns"] == 1
    assert drift["summary"]["impactedObjects"] >= 1
    assert {item["tableName"] for item in drift["addedTables"]} == {"contract_attachment"}
    contract_change = next(item for item in drift["changedTables"] if item["tableName"] == "contract")
    assert [item["columnName"] for item in contract_change["addedColumns"]] == ["risk_level"]
    assert any(item["ontologyId"] == ontology["id"] and item["code"] == "contract" for item in drift["impacts"]["objects"])
    assert any("重新扫描" in action or "本体" in action for action in drift["nextActions"])


def test_data_source_connection_checks_sqlite_file(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")

    registered = check_data_source_connection(platform_db, data_source_id=source.id)
    missing = check_data_source_connection(platform_db, source_type="sqlite", connection_uri=str(tmp_path / "missing.sqlite3"))

    assert registered["reachable"] is True
    assert registered["status"] == "ok"
    assert missing["reachable"] is False
    assert missing["status"] == "not_found"


def test_platform_lists_data_sources_and_ontologies_for_control_plane(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)

    data_sources = list_data_sources(platform_db)
    ontologies = list_ontologies(platform_db)

    assert len(data_sources) == 1
    assert data_sources[0]["id"] == source.id
    assert data_sources[0]["name"] == "合同管理样例系统"
    assert data_sources[0]["domain"] == "合同管理"
    assert data_sources[0]["systemCategory"] == "database"
    assert data_sources[0]["system_category"] == "database"
    assert data_sources[0]["sourceType"] == "sqlite"
    assert data_sources[0]["source_type"] == "sqlite"
    assert data_sources[0]["connectionUri"] == str(legacy_db)
    assert data_sources[0]["connection_uri"] == str(legacy_db)
    assert data_sources[0]["apiBaseUrl"] == ""
    assert data_sources[0]["api_base_url"] == ""
    assert data_sources[0]["capabilities"] == ["metadata_scan", "semantic_mapping"]
    assert data_sources[0]["createdAt"]
    assert ontologies[0]["id"] == ontology["id"]
    assert ontologies[0]["name"] == ontology["name"]
    assert ontologies[0]["domain"] == "合同管理"
    assert ontologies[0]["version"] == "0.1.0"
    assert ontologies[0]["status"] == "draft"


def test_ontology_exports_jsonld_and_turtle_assets(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology = generate_ontology_draft(platform_db, source.id)

    jsonld = export_ontology_asset(platform_db, ontology["id"], "jsonld")
    document = json.loads(jsonld["content"])
    graph_types = {node["@type"] for node in document["@graph"]}

    assert jsonld["mediaType"] == "application/ld+json"
    assert jsonld["filename"].endswith(".jsonld")
    assert "ont:Ontology" in graph_types
    assert "ont:BusinessObject" in graph_types
    assert "ont:BusinessAttribute" in graph_types
    assert "ont:BusinessRule" in graph_types
    assert any(node.get("code") == "contract" for node in document["@graph"])

    turtle = export_ontology_asset(platform_db, ontology["id"], "turtle")
    assert turtle["mediaType"] == "text/turtle"
    assert turtle["filename"].endswith(".ttl")
    assert "@prefix ont:" in turtle["content"]
    assert "ont:BusinessObject" in turtle["content"]
    assert "bp:object/contract" in turtle["content"]

    try:
        export_ontology_asset(platform_db, ontology["id"], "xml")
    except ValueError as error:
        assert "jsonld" in str(error)
    else:
        raise AssertionError("不支持的本体导出格式应被拒绝")


def test_model_config_persists_masks_and_resets(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    initial = get_model_config(platform_db)
    assert initial["provider"] == "openrouter"
    assert initial["hasApiKey"] is False

    saved = update_model_config(
        platform_db,
        {
            "apiKey": "or-test-secret-key",
            "model": "openai/test-model",
            "baseUrl": "https://openrouter.ai/api/v1/",
            "httpReferer": "https://example.com/app",
            "appTitle": "Ontology Platform Test",
            "serviceTier": "auto",
            "timeoutSeconds": 12,
        },
    )
    assert saved["success"] is True

    persisted = get_model_config(platform_db)
    assert persisted["configured"] is True
    assert persisted["hasApiKey"] is True
    assert persisted["apiKey"] == "or-tes...-key"
    assert persisted["model"] == "openai/test-model"
    assert persisted["baseUrl"] == "https://openrouter.ai/api/v1"
    assert persisted["httpReferer"] == "https://example.com/app"
    assert persisted["appTitle"] == "Ontology Platform Test"
    assert persisted["timeoutSeconds"] == 12.0

    update_model_config(platform_db, {"apiKey": "", "model": "openai/another-model"})
    retained_key = get_model_config(platform_db)
    assert retained_key["apiKey"] == "or-tes...-key"
    assert retained_key["model"] == "openai/another-model"

    reset = reset_model_config(platform_db)
    assert reset["success"] is True
    assert get_model_config(platform_db)["hasApiKey"] is False


def test_legacy_model_config_table_migrates_to_single_row_schema(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        conn.execute("drop table model_config")
        conn.execute(
            """
            create table model_config (
                id integer primary key autoincrement,
                config_key text not null unique,
                config_value text not null,
                description text not null default '',
                updated_at text not null default current_timestamp
            )
            """
        )
        conn.executemany(
            "insert into model_config (config_key, config_value) values (?, ?)",
            [
                ("api_key", "or-legacy-secret-key"),
                ("model", "deepseek/deepseek-v4-flash"),
                ("base_url", "https://openrouter.ai/api/v1"),
                ("http_referer", "https://legacy.example"),
                ("app_title", "Legacy Ontology Platform"),
                ("service_tier", "auto"),
                ("timeout_seconds", "15"),
            ],
        )

    initialize_platform_db(platform_db)
    migrated = get_model_config(platform_db)

    assert migrated["hasApiKey"] is True
    assert migrated["apiKey"] == "or-leg...-key"
    assert migrated["model"] == "deepseek/deepseek-v4-flash"
    assert migrated["httpReferer"] == "https://legacy.example"
    assert migrated["appTitle"] == "Legacy Ontology Platform"
    assert migrated["timeoutSeconds"] == 15.0


def test_database_adapter_registry_supports_common_enterprise_databases(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    sqlite_adapter = get_adapter("sqlite")
    postgres_adapter = get_adapter("postgresql")
    mysql_adapter = get_adapter("mysql")

    assert sqlite_adapter.source_type == "sqlite"
    assert postgres_adapter.source_type == "postgresql"
    assert mysql_adapter.source_type == "mysql"

    postgres = register_data_source(
        platform_db,
        "PostgreSQL 生产系统占位",
        "postgresql",
        "postgresql://user:pass@127.0.0.1:5432/app",
        domain="通用业务",
    )
    mysql = register_data_source(
        platform_db,
        "MySQL 生产系统占位",
        "mysql",
        "mysql://user:pass@127.0.0.1:3306/app",
        domain="通用业务",
    )

    assert postgres.source_type == "postgresql"
    assert mysql.source_type == "mysql"


def test_postgresql_scan_reports_missing_driver_as_actionable_error(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    source = register_data_source(
        platform_db,
        "PostgreSQL 生产系统占位",
        "postgresql",
        "postgresql://user:pass@127.0.0.1:5432/app",
        domain="通用业务",
    )

    try:
        scan_data_source(platform_db, source.id)
    except ValueError as error:
        assert "PostgreSQL 接入需要安装 psycopg" in str(error) or "connection" in str(error).lower()
    else:
        raise AssertionError("测试环境没有真实 PostgreSQL 服务时不应扫描成功")


def test_postgresql_connection_test_reports_actionable_status(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"

    initialize_platform_db(platform_db)
    result = check_data_source_connection(
        platform_db,
        source_type="postgresql",
        connection_uri="postgresql://user:pass@127.0.0.1:1/app",
    )

    assert result["reachable"] is False
    assert result["status"] in {"driver_missing", "connection_error"}
    assert result["message"]


def test_equipment_domain_generates_industry_rules_and_assessment(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_equipment.sqlite3"

    initialize_platform_db(platform_db)
    create_equipment_sample_db(legacy_db)
    source = register_data_source(platform_db, "设备运维样例系统", "sqlite", str(legacy_db), domain="设备运维", system_category="database+api")
    api = register_source_api(platform_db, source.id, "close_work_order", "关闭工单", "POST", "/work-orders/{id}/close", "work_order.close")
    scan = scan_data_source(platform_db, source.id)

    assert len(scan["tables"]) == 4
    assert api.operation_code == "close_work_order"
    assert list_source_apis(platform_db, source.id)[0]["semantic_action"] == "work_order.close"

    ontology = generate_ontology_draft(platform_db, source.id)
    object_codes = {item["code"] for item in ontology["objects"]}
    assert {"equipment", "work_order", "inspection_record", "spare_part"}.issubset(object_codes)
    assert any(rule["code"] == "critical_equipment_open_fault" for rule in ontology["rules"])

    assessment = assess_instance(platform_db, ontology["id"], "equipment", "1")
    assert assessment["decision"]["status"] == "review"
    failed_rules = {item["ruleCode"] for item in assessment["ruleResults"] if not item["passed"]}
    assert "critical_equipment_open_fault" in failed_rules


def test_openrouter_client_uses_subscription_key_shape() -> None:
    calls: list[dict[str, object]] = []

    def fake_transport(url: str, headers: dict[str, str], payload: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {
            "model": "openai/test-model",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    client = OpenRouterClient(
        OpenRouterConfig(
            api_key="or-test-key",
            model="openai/test-model",
            base_url="https://openrouter.ai/api/v1",
            http_referer="https://example.com",
            app_title="Ontology Platform",
            service_tier="auto",
            timeout_seconds=10,
        ),
        transport=fake_transport,
    )

    result = client.chat([{"role": "user", "content": "ping"}], session_id="session-1")

    assert result.content == "ok"
    assert calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    headers = calls[0]["headers"]
    payload = calls[0]["payload"]
    assert headers["Authorization"] == "Bearer or-test-key"
    assert headers["HTTP-Referer"] == "https://example.com"
    assert headers["X-OpenRouter-Title"] == "Ontology Platform"
    assert payload["model"] == "openai/test-model"
    assert payload["service_tier"] == "auto"
    assert payload["session_id"] == "session-1"


def test_blueprint_draft_uses_local_fallback_and_openrouter_shape(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"

    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    source = register_data_source(platform_db, "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan_data_source(platform_db, source.id)

    local = generate_blueprint_draft(platform_db, source.id, OpenRouterClient(OpenRouterConfig("", "test", "https://openrouter.ai/api/v1", "", "Ontology Platform", "auto", 10)))
    assert local["usedRemoteModel"] is False
    assert local["blueprint"]["domain"] == "合同管理"
    assert "contract" in local["blueprint"]["objectHints"]

    calls: list[dict[str, object]] = []

    def fake_transport(url: str, headers: dict[str, str], payload: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        calls.append({"url": url, "headers": headers, "payload": payload, "timeout": timeout_seconds})
        return {
            "model": "openai/test-model",
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "id": 123,
                                "name": "AI 合同蓝图",
                                "domain": "合同管理",
                                "description": "AI 生成",
                                "objectHints": {"contract": "合同"},
                                "attributeHints": {"contract.contract_no": "合同编号"},
                                "rules": [],
                                "tableKeywords": ["contract"],
                                "capabilityTags": ["ai-generated"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    remote = generate_blueprint_draft(
        platform_db,
        source.id,
        OpenRouterClient(
            OpenRouterConfig("or-test-key", "openai/test-model", "https://openrouter.ai/api/v1", "", "Ontology Platform", "auto", 10),
            transport=fake_transport,
        ),
    )
    assert remote["usedRemoteModel"] is True
    assert remote["blueprint"]["id"] == "123"
    assert remote["blueprint"]["attributeHints"]["contract_no"] == "合同编号"
    assert calls[0]["payload"]["service_tier"] == "auto"


def test_api_module_imports_on_supported_python() -> None:
    api = importlib.import_module("ontology_platform.api")
    assert api.app.title == "本体改造研发平台"
