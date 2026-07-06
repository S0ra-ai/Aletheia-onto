from __future__ import annotations

from pathlib import Path
import importlib
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.automation import preflight_operation
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import check_data_source_connection, list_source_apis, register_data_source, register_source_api, scan_data_source
from ontology_platform.model_client import OpenRouterClient, OpenRouterConfig
from ontology_platform.ontology import explain_instance, generate_ontology_draft
from ontology_platform.sample_data import create_contract_sample_db, create_equipment_sample_db
from ontology_platform.semantic_kernel import assess_instance


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


def test_api_module_imports_on_supported_python() -> None:
    api = importlib.import_module("ontology_platform.api")
    assert api.app.title == "本体改造研发平台"
