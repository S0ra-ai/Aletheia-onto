"""Credential exposure tests.

A data source row holds the production database password and the model config
holds an API key. These tests assert those secrets never travel back out
through a normal read path.
"""

from __future__ import annotations

import json
from pathlib import Path

from ontology_platform.credentials import mask_secret, redact_connection_uri, redact_headers
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import list_data_sources, register_data_source
from ontology_platform.model_client import get_model_config, update_model_config
from ontology_platform.onboarding import run_onboarding_pipeline
from ontology_platform.sample_data import create_contract_sample_db

SECRET = "sup3rs3cret"


def test_redact_connection_uri_removes_password_but_keeps_target() -> None:
    redacted = redact_connection_uri(f"mysql://root:{SECRET}@10.0.0.5:3306/contracts")
    assert SECRET not in redacted
    assert redacted == "mysql://root:***@10.0.0.5:3306/contracts"


def test_redact_connection_uri_preserves_uris_without_credentials() -> None:
    assert redact_connection_uri("postgresql://10.0.0.5:5432/db") == "postgresql://10.0.0.5:5432/db"
    assert redact_connection_uri("/var/data/legacy.sqlite3") == "/var/data/legacy.sqlite3"
    assert redact_connection_uri("") == ""
    assert redact_connection_uri(None) == ""


def test_redact_headers_masks_credential_carrying_names() -> None:
    redacted = redact_headers({"Authorization": f"Bearer {SECRET}", "X-Api-Key": SECRET, "X-Tenant": "demo"})
    assert redacted["Authorization"] == "***"
    assert redacted["X-Api-Key"] == "***"
    assert redacted["X-Tenant"] == "demo"


def test_mask_secret_keeps_identifiable_prefix() -> None:
    assert mask_secret("or-abcdef123456789") == "or-abc...6789"
    assert mask_secret("short") == "***"
    assert mask_secret("") == ""


def test_listed_data_sources_do_not_leak_database_password(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    register_data_source(
        platform_db,
        "生产合同库",
        "mysql",
        f"mysql://app_user:{SECRET}@db.internal:3306/contracts",
        domain="合同管理",
    )

    listed = list_data_sources(platform_db)
    payload = json.dumps(listed, ensure_ascii=False)
    assert SECRET not in payload
    assert listed[0]["connectionUri"] == "mysql://app_user:***@db.internal:3306/contracts"
    assert listed[0]["connectionUriRedacted"] is True

    # The platform still needs the real credential internally to connect.
    with connect(platform_db) as conn:
        stored = conn.execute("select connection_uri from data_source").fetchone()["connection_uri"]
    assert SECRET in stored


def test_registered_data_source_response_is_redacted(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(
        platform_db,
        "生产设备库",
        "postgresql",
        f"postgresql://svc:{SECRET}@pg.internal:5432/equipment",
        domain="设备运维",
    )
    assert SECRET not in json.dumps(source.public_dict(), ensure_ascii=False)
    # The dataclass keeps the usable credential for internal callers.
    assert SECRET in source.connection_uri


def test_onboarding_result_does_not_leak_credentials(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    legacy_db = tmp_path / "legacy_contracts.sqlite3"
    initialize_platform_db(platform_db)
    create_contract_sample_db(legacy_db)
    result = run_onboarding_pipeline(
        platform_db,
        "合同管理样例系统",
        "sqlite",
        str(legacy_db),
        domain="合同管理",
    )
    assert result["dataSource"]["connectionUriRedacted"] is False
    assert "connection_uri" in result["dataSource"]


def test_model_config_never_returns_the_raw_api_key(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    update_model_config(platform_db, {"apiKey": f"or-{SECRET}-tail", "model": "openai/test"})
    config = get_model_config(platform_db)
    assert SECRET not in json.dumps(config, ensure_ascii=False)
    assert config["hasApiKey"] is True
