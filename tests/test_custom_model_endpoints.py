"""Custom model endpoint compatibility.

`base_url` alone does not make an arbitrary OpenAI-compatible endpoint work.
Relay gateways, self-hosted vLLM, Azure OpenAI and domestic providers differ in
how they authenticate and which extra body fields they tolerate -- and an unknown
field is frequently a hard 400 rather than being ignored.

Each case here corresponds to a real deployment shape rather than a hypothetical.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.database import initialize_platform_db
from ontology_platform.model_client import (
    AUTH_STYLES,
    OpenRouterClient,
    OpenRouterConfig,
    get_model_config,
    update_model_config,
)


def _config(**overrides) -> OpenRouterConfig:
    base = {
        "api_key": "test-key",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
        "http_referer": "",
        "app_title": "Aletheia",
        "service_tier": "",
        "timeout_seconds": 10.0,
    }
    base.update(overrides)
    return OpenRouterConfig(**base)


def _capture(config: OpenRouterConfig, session_id: str | None = None):
    calls = []

    def transport(url, headers, payload, timeout):
        calls.append({"url": url, "headers": headers, "payload": payload})
        return {"choices": [{"message": {"content": "ok"}}], "model": config.model}

    client = OpenRouterClient(config=config, transport=transport)
    client.chat([{"role": "user", "content": "ping"}], session_id=session_id)
    return calls[0]


# -- Endpoint URL construction --


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("https://api.openai.com/v1", "https://api.openai.com/v1/chat/completions"),
        ("https://api.openai.com/v1/", "https://api.openai.com/v1/chat/completions"),
        ("http://127.0.0.1:8000/v1", "http://127.0.0.1:8000/v1/chat/completions"),
        ("https://relay.example.com/openai/v1", "https://relay.example.com/openai/v1/chat/completions"),
    ],
)
def test_chat_endpoint_is_derived_from_base_url(base_url, expected) -> None:
    assert _config(base_url=base_url).chat_completions_url == expected


def test_base_url_already_ending_in_the_path_is_not_doubled() -> None:
    """Some gateways publish the full chat endpoint as their base URL."""
    config = _config(base_url="https://relay.example.com/v1/chat/completions")
    assert config.chat_completions_url == "https://relay.example.com/v1/chat/completions"


def test_azure_style_base_url_with_query_string_is_preserved() -> None:
    """Azure carries ?api-version=..., which must survive intact."""
    azure = "https://my-resource.openai.azure.com/openai/deployments/gpt4o/chat/completions?api-version=2024-02-01"
    assert _config(base_url=azure).chat_completions_url == azure


# -- Authentication styles --


def test_bearer_is_the_default() -> None:
    headers = _capture(_config())["headers"]
    assert headers["Authorization"] == "Bearer test-key"
    assert "api-key" not in headers


def test_azure_uses_an_api_key_header_not_bearer() -> None:
    headers = _capture(_config(auth_style="api-key"))["headers"]
    assert headers["api-key"] == "test-key"
    assert "Authorization" not in headers


def test_custom_auth_header_is_honoured() -> None:
    headers = _capture(_config(auth_style="custom", auth_header="X-Api-Token"))["headers"]
    assert headers["X-Api-Token"] == "test-key"
    assert "Authorization" not in headers


def test_auth_style_none_sends_no_credential() -> None:
    """Self-hosted vLLM or Ollama behind a private network often needs no key."""
    headers = _capture(_config(auth_style="none"))["headers"]
    assert "Authorization" not in headers
    assert "api-key" not in headers


def test_no_credential_header_when_key_is_empty() -> None:
    config = _config(api_key="")
    # An unconfigured client refuses before building a request at all.
    assert config.request_headers().get("Authorization") is None


def test_attribution_uses_the_header_openrouter_actually_reads() -> None:
    headers = _config(app_title="Aletheia").request_headers()
    assert headers["X-Title"] == "Aletheia"


def test_extra_headers_are_applied_and_can_override() -> None:
    """Escape hatch for gateways needing a tenant id, group id or similar."""
    headers = _config(extra_headers={"X-Tenant-Id": "acme", "Authorization": "Custom override"}).request_headers()
    assert headers["X-Tenant-Id"] == "acme"
    assert headers["Authorization"] == "Custom override"


# -- Provider-specific body fields --


def test_provider_extras_are_sent_by_default() -> None:
    """Preserves existing OpenRouter behaviour."""
    payload = _capture(_config(service_tier="auto"), session_id="s-1")["payload"]
    assert payload["service_tier"] == "auto"
    assert payload["session_id"] == "s-1"


def test_provider_extras_can_be_suppressed_for_strict_servers() -> None:
    """vLLM and LM Studio reject unknown body fields with a 400."""
    payload = _capture(_config(service_tier="auto", send_provider_extras=False), session_id="s-1")["payload"]
    assert "service_tier" not in payload
    assert "session_id" not in payload
    # The standard fields must still be present.
    assert payload["model"] == "gpt-4o-mini"
    assert payload["messages"][0]["content"] == "ping"


# -- Persistence --


def test_custom_endpoint_settings_round_trip_through_the_database(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)

    update_model_config(
        platform_db,
        {
            "apiKey": "relay-key",
            "model": "qwen-max",
            "baseUrl": "https://relay.example.com/v1/",
            "authStyle": "custom",
            "authHeader": "X-Api-Token",
            "extraHeaders": {"X-Tenant-Id": "acme"},
            "sendProviderExtras": False,
        },
    )

    config = OpenRouterConfig.from_db_or_env(platform_db)
    assert config.model == "qwen-max"
    assert config.base_url == "https://relay.example.com/v1"
    assert config.auth_style == "custom"
    assert config.auth_header == "X-Api-Token"
    assert config.extra_headers == {"X-Tenant-Id": "acme"}
    assert config.send_provider_extras is False

    headers = config.request_headers()
    assert headers["X-Api-Token"] == "relay-key"
    assert headers["X-Tenant-Id"] == "acme"


def test_reported_config_exposes_the_resolved_endpoint(tmp_path: Path) -> None:
    """Operators need to see the URL that will actually be called."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    update_model_config(platform_db, {"baseUrl": "https://relay.example.com/v1"})

    reported = get_model_config(platform_db)
    assert reported["resolvedEndpoint"] == "https://relay.example.com/v1/chat/completions"
    assert reported["authStyleOptions"] == list(AUTH_STYLES)


def test_unknown_auth_style_is_rejected(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with pytest.raises(ValueError, match="不支持的鉴权方式"):
        update_model_config(platform_db, {"authStyle": "magic"})


def test_custom_style_requires_a_header_name(tmp_path: Path) -> None:
    """Otherwise the credential would be silently dropped."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with pytest.raises(ValueError, match="必须填写鉴权请求头"):
        update_model_config(platform_db, {"authStyle": "custom", "authHeader": ""})


def test_malformed_extra_headers_degrade_instead_of_breaking_calls(tmp_path: Path) -> None:
    """A bad stored value must not make every model call fail."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    update_model_config(platform_db, {"extraHeaders": "not-json{{"})
    config = OpenRouterConfig.from_db_or_env(platform_db)
    assert config.extra_headers == {}
    assert "Content-Type" in config.request_headers()


def test_api_key_is_not_returned_in_full(tmp_path: Path) -> None:
    """Regression guard: the config screen must never leak a usable key."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    update_model_config(platform_db, {"apiKey": "sk-super-secret-value-1234567890"})
    reported = get_model_config(platform_db)
    assert "sk-super-secret-value-1234567890" not in str(reported)
