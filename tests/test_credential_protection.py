"""Credential exposure tests.

A data source row holds the production database password and the model config
holds an API key. These tests assert those secrets never travel back out
through a normal read path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from ontology_platform.credentials import mask_secret, redact_connection_uri, redact_headers
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.metadata import list_data_sources, register_data_source
from ontology_platform.model_client import get_model_config, reset_model_config, update_model_config
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


def test_resetting_the_model_config_records_what_it_destroyed(tmp_path: Path) -> None:
    """The audit row has to survive the reset, and has to say what stopped existing.

    Two things were wrong with it. `actor` was the literal `"system"` while the route sits
    behind `CAP_ADMIN`, so the one row that records a destructive administrative action named
    nobody who could have done it. And `detail` was `{}`, so an administrator reading the log
    afterwards could not tell whether a key had just been destroyed or whether there had never
    been one -- the difference between "we need to re-enter the key" and "the model has been
    broken for a week".

    The key's *value* is still never written: this table is read by more people than a
    credential store, and an audit log that quoted the secret would be a worse leak than the
    one it documents.
    """
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    update_model_config(
        platform_db,
        {"apiKey": f"or-{SECRET}-tail", "model": "openai/gpt-4o", "baseUrl": "https://relay.example.com/v1"},
    )

    reset_model_config(platform_db, actor="alice")

    with connect(platform_db) as conn:
        row = conn.execute(
            "select actor, detail from audit_log where action = 'reset_model_config' order by id desc"
        ).fetchone()
    assert row is not None, "重置没有留下任何审计记录"
    assert row["actor"] == "alice", f"审计把管理员的操作记成了「{row['actor']}」"
    assert SECRET not in row["detail"], f"审计记录里出现了密钥本身：{row['detail']}"

    detail = json.loads(row["detail"])
    assert detail["hasApiKey"] is True, "审计没有说明这次重置删掉了一把密钥"
    assert detail["model"] == "openai/gpt-4o"
    assert detail["baseUrl"] == "https://relay.example.com/v1"

    # And the reset really reset: the stored row is gone, so reads fall back to the
    # environment rather than to half of the discarded configuration.
    assert get_model_config(platform_db)["source"] != "database"


def test_resetting_an_unconfigured_platform_says_so(tmp_path: Path) -> None:
    """`detail` has to distinguish "a key was destroyed" from "there was nothing to destroy".

    The resolved configuration cannot answer this: with `ONTOLOGY_MODEL_API_KEY` set in the
    environment, a deployment that never saved anything still reports a key. Read from the
    stored row instead.
    """
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)

    reset_model_config(platform_db, actor="alice")

    with connect(platform_db) as conn:
        row = conn.execute(
            "select detail from audit_log where action = 'reset_model_config' order by id desc"
        ).fetchone()
    detail = json.loads(row["detail"])
    assert detail["hasApiKey"] is False
    assert detail["hadStoredConfig"] is False


# -- The way in: keeping the secret out of the database entirely --


def test_a_reference_resolves_at_the_point_of_use(monkeypatch) -> None:
    """`env:NAME` and `file:/path`, and nothing else.

    The documented mitigation for "the platform database is the credential store" was "prefer
    environment variables". That advice was only actionable for OpenRouter and DeepSeek, whose
    variables the model layer knew by name; a custom provider's key -- Azure, a relay, a local
    gateway -- had nowhere to go but the row. A reference is the general form.
    """
    from ontology_platform.credentials import is_reference, resolve_secret

    monkeypatch.setenv("CREDENTIAL_TEST_DSN", "postgresql://u:p@h/db")
    assert resolve_secret("env:CREDENTIAL_TEST_DSN") == "postgresql://u:p@h/db"

    # Not a reference: returned untouched, which is what every ordinary value relies on.
    assert resolve_secret("sqlite:///tmp/x.db") == "sqlite:///tmp/x.db"
    assert resolve_secret("") == ""
    assert resolve_secret(None) == ""

    assert is_reference("env:X") is True
    assert is_reference("file:/run/secrets/x") is True
    # Case-sensitive: a connection URI always contains `://`, so `env:` cannot collide with a
    # scheme, and half-recognising `ENV:` would send a typo down the wrong branch.
    assert is_reference("ENV:X") is False
    assert is_reference("postgresql://h/db") is False


def test_a_reference_that_points_at_nothing_is_an_error_rather_than_empty(monkeypatch, tmp_path) -> None:
    """An empty credential fails as "the password is wrong", which is the wrong diagnosis.

    The reader has to work out that the platform never had it. Raising says which variable or
    which file, at the moment the connection is attempted, which is the moment it can be fixed.
    """
    from ontology_platform.credentials import UnresolvedSecret, resolve_secret

    monkeypatch.delenv("CREDENTIAL_TEST_MISSING", raising=False)
    with pytest.raises(UnresolvedSecret, match="CREDENTIAL_TEST_MISSING"):
        resolve_secret("env:CREDENTIAL_TEST_MISSING")

    with pytest.raises(UnresolvedSecret, match="读不到"):
        resolve_secret(f"file:{tmp_path / 'not-there'}")


def test_a_secret_file_loses_its_trailing_newline(tmp_path) -> None:
    """Every tool that writes a secret file writes a newline, and `echo` writes one too.

    A password with a trailing newline fails to authenticate against most systems, and the
    failure looks like a wrong password rather than like a stray byte.
    """
    from ontology_platform.credentials import resolve_secret

    path = tmp_path / "key"
    path.write_text("sk-abc123\n")
    assert resolve_secret(f"file:{path}") == "sk-abc123"


def test_the_adapter_connects_with_a_resolved_reference(tmp_path, monkeypatch) -> None:
    """End to end through `get_adapter`, which is the only place every caller goes through.

    Resolved there rather than in each adapter's `runtime`: there are five implementations and
    eight call sites in this package alone, and a per-site approach is the one that misses the
    next adapter somebody registers.
    """
    from ontology_platform.adapters import get_adapter
    from ontology_platform.database import initialize_platform_db
    from ontology_platform.sample_data import create_contract_sample_db

    sample = tmp_path / "legacy.sqlite3"
    create_contract_sample_db(sample)
    initialize_platform_db(tmp_path / "platform.sqlite3")

    monkeypatch.setenv("CREDENTIAL_TEST_SOURCE", str(sample))
    adapter = get_adapter("sqlite")

    # The reference resolves, so this reaches the file and reports what is in it.
    resolved = adapter.test_connection("env:CREDENTIAL_TEST_SOURCE")
    assert resolved["reachable"] is True, resolved

    # The path itself still works, unchanged.
    assert adapter.test_connection(str(sample))["reachable"] is True

    # And a reference pointing nowhere fails loudly instead of reporting an unreachable source,
    # which would read as "your database is down" and send the reader to the wrong system.
    monkeypatch.delenv("CREDENTIAL_TEST_SOURCE", raising=False)
    from ontology_platform.credentials import UnresolvedSecret

    with pytest.raises(UnresolvedSecret):
        adapter.test_connection("env:CREDENTIAL_TEST_SOURCE")
