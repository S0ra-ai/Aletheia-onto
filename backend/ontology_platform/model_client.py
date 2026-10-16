from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable

from .config import MODEL_PROVIDER_DEFAULTS
from .context import PlatformDb
from .credentials import resolve_secret
from .database import connect
from .errors import describe_model_failure
from .industry_blueprints import coerce_hints, rule_is_readable

Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


# Auth styles understood by the model layer. Each exists because a real provider
# needed it, not for completeness.
AUTH_STYLES = ("bearer", "api-key", "custom", "none")


def _parse_header_json(raw: Any) -> dict[str, str]:
    """Parse the stored extra-headers JSON, tolerating malformed values.

    A bad value must not break model calls entirely; it degrades to no extra
    headers, which is the previous behaviour.
    """
    if not raw:
        return {}
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if str(k).strip()}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in parsed.items() if str(k).strip()}


def _row_get(row: Any, column: str) -> str:
    """Read a column that may not exist on an older schema."""
    try:
        value = row[column]
    except (KeyError, IndexError, TypeError):
        return ""
    return "" if value is None else str(value)


def _row_flag(row: Any, column: str, *, default: bool) -> bool:
    raw = _row_get(row, column)
    if raw == "":
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    base_url: str
    http_referer: str
    app_title: str
    service_tier: str
    timeout_seconds: float
    # -- Custom endpoint compatibility --
    #
    # base_url alone is not enough to talk to an arbitrary OpenAI-compatible
    # endpoint. Relay gateways, self-hosted vLLM, Azure OpenAI and domestic
    # providers each differ in how they authenticate and which extra fields they
    # tolerate, and an unknown field is frequently a hard 400 rather than being
    # ignored. These four settings cover the differences we have actually hit.
    auth_style: str = "bearer"
    auth_header: str = ""
    extra_headers: dict[str, str] = field(default_factory=dict)
    send_provider_extras: bool = True
    # The transport remains OpenAI-compatible, but keeping the selected vendor
    # lets status pages and invocation ledgers tell DeepSeek direct from OpenRouter.
    # It is last so existing positional construction remains source-compatible.
    provider: str = "openrouter"

    @property
    def chat_completions_url(self) -> str:
        """Full chat endpoint.

        Some gateways publish a base that already ends in /chat/completions, and
        Azure deployments carry a query string. Appending blindly would corrupt
        both, so detect and pass those through unchanged.
        """
        base = self.base_url.rstrip("/")
        if "/chat/completions" in base:
            return self.base_url
        return f"{base}/chat/completions"

    def request_headers(self) -> dict[str, str]:
        """Authentication and attribution headers for this provider."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        style = (self.auth_style or "bearer").strip().lower()
        if self.api_key:
            if style == "none":
                pass
            elif style == "api-key":
                # Azure OpenAI and several domestic gateways.
                headers["api-key"] = self.api_key
            elif style == "custom" and self.auth_header:
                headers[self.auth_header] = self.api_key
            else:
                headers["Authorization"] = f"Bearer {self.api_key}"
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if self.app_title:
            # OpenRouter reads X-Title; the vendor-prefixed name was wrong and is
            # ignored by every other gateway.
            headers["X-Title"] = self.app_title
        # Applied last so an operator can override anything above.
        headers.update({k: v for k, v in (self.extra_headers or {}).items() if k})
        return headers

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        deepseek_key = os.getenv("DEEPSEEK_API_KEY", "")
        use_deepseek = bool(deepseek_key and not openrouter_key)
        return cls(
            api_key=deepseek_key if use_deepseek else openrouter_key,
            model=(os.getenv("DEEPSEEK_MODEL", "").strip() or "deepseek-flash")
            if use_deepseek
            else MODEL_PROVIDER_DEFAULTS.model,
            base_url=(os.getenv("DEEPSEEK_BASE_URL", "").strip() or "https://api.deepseek.com")
            if use_deepseek
            else MODEL_PROVIDER_DEFAULTS.base_url.rstrip("/"),
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER", ""),
            app_title=MODEL_PROVIDER_DEFAULTS.app_title,
            service_tier="" if use_deepseek else MODEL_PROVIDER_DEFAULTS.service_tier,
            timeout_seconds=MODEL_PROVIDER_DEFAULTS.timeout_seconds,
            auth_style=os.getenv("ONTOLOGY_MODEL_AUTH_STYLE", "bearer"),
            auth_header=os.getenv("ONTOLOGY_MODEL_AUTH_HEADER", ""),
            extra_headers=_parse_header_json(os.getenv("ONTOLOGY_MODEL_EXTRA_HEADERS", "")),
            send_provider_extras=(
                os.getenv("ONTOLOGY_MODEL_SEND_EXTRAS", "").strip().lower() not in {"0", "false", "no"}
                if not use_deepseek
                else False
            ),
            provider="deepseek" if use_deepseek else "openrouter",
        )

    @classmethod
    def from_db_or_env(cls, platform_db: PlatformDb) -> "OpenRouterConfig":
        env_config = cls.from_env()
        with connect(platform_db) as conn:
            row = conn.execute("select * from model_config where id = 1").fetchone()
            if row is None:
                return env_config
            # `initialize_platform_db` creates a default row so the settings page can
            # read immediately. An empty default row must not mask a provider key that
            # was intentionally supplied through the environment (notably
            # DEEPSEEK_API_KEY in container deployments).
            if not _row_get(row, "api_key") and env_config.provider != "openrouter":
                return env_config
            return cls(
                # A stored key may be an `env:`/`file:` reference rather than the key itself,
                # which is the only way an operator can keep a custom provider's credential
                # (Azure, a relay, a local gateway) out of the platform database at all -- the
                # environment fallback below covers OpenRouter and DeepSeek by name, and names
                # nothing else. Resolved here, at the point of use, never on a display path:
                # the settings page shows the reference, which is what tells an operator which
                # secret the row is using.
                api_key=resolve_secret(row["api_key"], what="模型 API Key") or env_config.api_key,
                model=row["model"] or env_config.model,
                base_url=(row["base_url"] or env_config.base_url).rstrip("/"),
                http_referer=row["http_referer"] or env_config.http_referer,
                app_title=row["app_title"] or env_config.app_title,
                service_tier=row["service_tier"] or env_config.service_tier,
                timeout_seconds=float(row["timeout_seconds"] or env_config.timeout_seconds),
                # Read defensively: a database migrated by an older build may not
                # carry these columns yet, and the model layer must not be the
                # reason startup fails.
                auth_style=_row_get(row, "auth_style") or env_config.auth_style,
                auth_header=_row_get(row, "auth_header") or env_config.auth_header,
                extra_headers=_parse_header_json(_row_get(row, "extra_headers")) or env_config.extra_headers,
                send_provider_extras=_row_flag(row, "send_provider_extras", default=True),
                provider=_row_get(row, "provider") or env_config.provider,
            )


@dataclass(frozen=True)
class ModelResult:
    provider: str
    model: str
    configured: bool
    used_remote_model: bool
    content: str
    raw: dict[str, Any]


class OpenRouterClient:
    @property
    def provider(self) -> str:
        return self.config.provider

    def __init__(self, config: OpenRouterConfig | None = None, transport: Transport | None = None) -> None:
        self.config = config or OpenRouterConfig.from_env()
        self.transport = transport or _post_json

    @property
    def configured(self) -> bool:
        return bool(self.config.api_key)

    def status(self) -> dict[str, Any]:
        key_source = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(self.provider, "model_config.api_key")
        return {
            "provider": self.provider,
            "configured": self.configured,
            "model": self.config.model,
            "baseUrl": self.config.base_url,
            "serviceTier": self.config.service_tier,
            "usesSubscriptionOrCreditKey": self.configured,
            "apiKeySource": key_source if self.configured else "missing",
        }

    def chat(
        self, messages: list[dict[str, str]], purpose: str = "semantic_assistance", session_id: str | None = None
    ) -> ModelResult:
        if not self.configured:
            raise ValueError("未配置模型 API Key，无法调用远程模型")

        headers = self.config.request_headers()

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        # service_tier and session_id are OpenRouter extensions. Strict
        # OpenAI-compatible servers (vLLM, LM Studio, many relay gateways) reject
        # unknown body fields with a 400, so they are opt-out for custom
        # endpoints rather than always sent.
        if self.config.send_provider_extras:
            if self.config.service_tier:
                payload["service_tier"] = self.config.service_tier
            if session_id:
                payload["session_id"] = session_id

        raw = self.transport(
            self.config.chat_completions_url,
            headers,
            payload,
            self.config.timeout_seconds,
        )
        return ModelResult(
            provider=self.provider,
            model=raw.get("model", self.config.model),
            configured=True,
            used_remote_model=True,
            content=_response_text(raw),
            raw=raw,
        )


def _response_text(raw: Any) -> str:
    """The assistant text of an OpenAI-compatible response, always a string.

    Read defensively because every variation here is a legal HTTP 200 from some gateway:
    `content` is `null` for a turn that produced no text (a tool-call-only or
    reasoning-only reply), `choices` comes back as an empty list on several relays' error
    paths, and the text may be a list of content parts rather than a string.

    Each of those used to raise from whatever consumer next called `.strip()` -- and every
    such consumer sits inside a broad `except` that reports a fallback, so a user whose
    model answered correctly was told the model service was unavailable. An empty string is
    the honest value instead: it says "no text came back", which callers already handle,
    rather than raising something that reads as an outage.

    `ModelResult.content` is annotated `str`, so returning `None` was also a lie to every
    type checker downstream.
    """
    if not isinstance(raw, dict):
        return ""
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    if not isinstance(message, dict):
        return ""

    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # The multimodal shape. Joined rather than stringified: `str([...])` would hand the
        # caller a Python repr, which reads as the model's words but is not.
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts)
    return ""


def generate_semantic_suggestions(
    platform_db: PlatformDb,
    data_source_id: int,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    metadata = _metadata_prompt_payload(platform_db, data_source_id)
    model_client = client or OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    if not model_client.configured:
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "content": _local_suggestions(metadata),
            "openrouter": model_client.status(),
        }

    messages = [
        {
            "role": "system",
            "content": "你是企业信息系统本体改造平台的本体工程助手。请基于数据库元数据生成业务对象、关系、规则和治理风险建议，输出精炼 JSON。",
        },
        {
            "role": "user",
            "content": json.dumps(metadata, ensure_ascii=False),
        },
    ]
    try:
        result = model_client.chat(messages, purpose="ontology_suggestions", session_id=f"ontology-{data_source_id}")
        record_model_invocation(platform_db, result, "ontology_suggestions", "success")
        return {
            "provider": result.provider,
            "model": result.model,
            "usedRemoteModel": result.used_remote_model,
            "content": result.content,
            "openrouter": model_client.status(),
        }
    except Exception as error:
        record_model_invocation(platform_db, None, "ontology_suggestions", "error", str(error), model_client)
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "content": _local_suggestions(metadata),
            "openrouter": model_client.status(),
            "remoteError": describe_model_failure(error),
        }


def generate_blueprint_draft(
    platform_db: PlatformDb,
    data_source_id: int,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    metadata = _metadata_prompt_payload(platform_db, data_source_id)
    model_client = client or OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    local = _local_blueprint_draft(metadata)
    if not model_client.configured:
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "blueprint": local,
            "openrouter": model_client.status(),
        }

    messages = [
        {
            "role": "system",
            "content": (
                "你是企业本体工程师。请基于传统业务系统元数据生成一个可导入的行业蓝图 JSON。"
                "必须只输出 JSON 对象，字段包括 id,name,domain,description,objectHints,attributeHints,rules,tableKeywords,capabilityTags。"
                # The shapes are stated because the platform stores them, and a prompt that
                # names a field without its shape leaves the model to guess -- a live model
                # answered `objectHints` with a list of object descriptors, which the
                # platform then could not read. Stating the shape is cheaper than accepting
                # every shape, and the list form is still accepted for robustness.
                # Placeholders rather than an example drawn from a real domain: the platform
                # ships no industry vocabulary (tests/test_domain_neutrality.py enforces
                # exactly that), and a concrete example here would also anchor the model to
                # one domain's table names instead of the metadata it was handed.
                'objectHints 必须是对象：键为元数据中的来源表名，值为该表对应的业务对象中文名，例如 {"<表名>": "<业务对象名>"}。'
                'attributeHints 必须是对象：键为「<表名>.<列名>」，值为该字段的业务含义中文名，例如 {"<表名>.<列名>": "<字段业务含义>"}。'
                "tableKeywords 与 capabilityTags 必须是字符串数组。"
                "rules 的元素必须包含 code,name,rule_type,scope_object_code,expression,severity,natural_language。"
            ),
        },
        {"role": "user", "content": json.dumps(metadata, ensure_ascii=False)},
    ]
    try:
        result = model_client.chat(messages, purpose="blueprint_draft", session_id=f"blueprint-{data_source_id}")
        record_model_invocation(platform_db, result, "blueprint_draft", "success")
        parsed = _extract_json_object(result.content)
        blueprint, unreadable = _normalize_blueprint(parsed, local)
        response = {
            "provider": result.provider,
            "model": result.model,
            "usedRemoteModel": result.used_remote_model,
            "blueprint": blueprint,
            "openrouter": model_client.status(),
        }
        if unreadable:
            # Surfaced rather than swallowed: the caller asked for a model-assisted draft
            # and is entitled to know which parts of it came from the draft instead. The
            # whole bug this replaces was invisible for exactly the lack of this line.
            response["unreadableModelFields"] = unreadable
        return response
    except Exception as error:
        record_model_invocation(platform_db, None, "blueprint_draft", "error", str(error), model_client)
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "blueprint": local,
            "openrouter": model_client.status(),
            "remoteError": describe_model_failure(error),
        }


def generate_ontology_reasoning_chain(
    platform_db: PlatformDb,
    data_source_id: int,
    client: OpenRouterClient | None = None,
) -> dict[str, Any]:
    metadata = _metadata_prompt_payload(platform_db, data_source_id)
    model_client = client or OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    local = _local_reasoning_chain(metadata)
    if not model_client.configured:
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "chain": local,
            "openrouter": model_client.status(),
        }

    messages = [
        {
            "role": "system",
            "content": (
                "你是企业本体工程架构师。请基于传统数据库元数据构建本体推理链。"
                "必须只输出 JSON 对象，字段包括 summary, reasoningSteps, proposedObjects, proposedRelations, proposedRules, buildPlan, questionsForUser。"
                # Shapes stated for the same reason as the blueprint prompt: naming a field
                # without its shape leaves the model to guess, and the guess that reads most
                # naturally ("给出两种路径" -> one object per path) is the one the UI cannot draw.
                "summary 必须是字符串。"
                "reasoningSteps、buildPlan、questionsForUser 必须是字符串数组。"
                "proposedObjects 的元素必须是对象，包含 objectCode,objectName,sourceTable,reason。"
                "proposedRelations 的元素必须是对象，包含 sourceObject,targetObject,sourceForeignKey,reason。"
                "proposedRules 的元素必须是对象，包含 scopeObject,ruleName,severity,reason。"
                "reasoningSteps 要说明从表、字段、外键、业务 API 推断业务对象/关系/规则的过程。"
                "buildPlan 要给出自动构建与用户手工确认两种路径。"
            ),
        },
        {"role": "user", "content": json.dumps(metadata, ensure_ascii=False)},
    ]
    try:
        result = model_client.chat(
            messages, purpose="ontology_reasoning_chain", session_id=f"reasoning-{data_source_id}"
        )
        record_model_invocation(platform_db, result, "ontology_reasoning_chain", "success")
        parsed = _extract_json_object(result.content)
        chain, unreadable = _normalize_reasoning_chain(parsed, local)
        response = {
            "provider": result.provider,
            "model": result.model,
            "usedRemoteModel": result.used_remote_model,
            "chain": chain,
            "openrouter": model_client.status(),
        }
        if unreadable:
            response["unreadableModelFields"] = unreadable
        return response
    except Exception as error:
        record_model_invocation(platform_db, None, "ontology_reasoning_chain", "error", str(error), model_client)
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "chain": local,
            "openrouter": model_client.status(),
            "remoteError": describe_model_failure(error),
        }


def get_model_config(platform_db: PlatformDb) -> dict[str, Any]:
    config = OpenRouterConfig.from_db_or_env(platform_db)
    source = _model_config_source(platform_db)
    return {
        "configured": bool(config.api_key),
        "provider": config.provider,
        "apiKey": _mask_api_key(config.api_key),
        "hasApiKey": bool(config.api_key),
        "model": config.model,
        "baseUrl": config.base_url,
        "httpReferer": config.http_referer,
        "appTitle": config.app_title,
        "serviceTier": config.service_tier,
        "timeoutSeconds": config.timeout_seconds,
        "authStyle": config.auth_style,
        "authHeader": config.auth_header,
        "extraHeaders": config.extra_headers,
        "sendProviderExtras": config.send_provider_extras,
        "authStyleOptions": list(AUTH_STYLES),
        "resolvedEndpoint": config.chat_completions_url,
        "source": source,
    }


def update_model_config(platform_db: PlatformDb, payload: dict[str, Any], *, actor: str = "system") -> dict[str, Any]:
    current = OpenRouterConfig.from_db_or_env(platform_db)
    api_key = payload.get("apiKey")
    if api_key is None or api_key == "":
        api_key = current.api_key
    model = payload.get("model") or current.model
    base_url = (payload.get("baseUrl") or current.base_url).rstrip("/")
    http_referer = payload.get("httpReferer")
    if http_referer is None:
        http_referer = current.http_referer
    app_title = payload.get("appTitle") or current.app_title
    service_tier = payload.get("serviceTier") or current.service_tier
    timeout_seconds = float(payload.get("timeoutSeconds") or current.timeout_seconds)

    auth_style = (payload.get("authStyle") or current.auth_style or "bearer").strip().lower()
    if auth_style not in AUTH_STYLES:
        raise ValueError(f"不支持的鉴权方式: {auth_style}。可选: {'、'.join(AUTH_STYLES)}")
    auth_header = payload.get("authHeader")
    if auth_header is None:
        auth_header = current.auth_header
    auth_header = str(auth_header).strip()
    if auth_style == "custom" and not auth_header:
        raise ValueError("鉴权方式为 custom 时必须填写鉴权请求头名称")

    if "extraHeaders" in payload:
        extra_headers = _parse_header_json(payload.get("extraHeaders"))
    else:
        extra_headers = current.extra_headers
    send_extras = payload.get("sendProviderExtras")
    send_provider_extras = current.send_provider_extras if send_extras is None else bool(send_extras)
    provider = str(payload.get("provider") or current.provider or "openrouter").strip().lower()
    if not provider:
        provider = "openrouter"

    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into model_config (
                id, provider, api_key, model, base_url, http_referer,
                app_title, service_tier, timeout_seconds,
                auth_style, auth_header, extra_headers, send_provider_extras, updated_at
            )
            values (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            on conflict(id) do update set
                api_key = excluded.api_key,
                provider = excluded.provider,
                model = excluded.model,
                base_url = excluded.base_url,
                http_referer = excluded.http_referer,
                app_title = excluded.app_title,
                service_tier = excluded.service_tier,
                timeout_seconds = excluded.timeout_seconds,
                auth_style = excluded.auth_style,
                auth_header = excluded.auth_header,
                extra_headers = excluded.extra_headers,
                send_provider_extras = excluded.send_provider_extras,
                updated_at = current_timestamp
            """,
            (
                provider,
                api_key,
                model,
                base_url,
                http_referer,
                app_title,
                service_tier,
                timeout_seconds,
                auth_style,
                auth_header,
                json.dumps(extra_headers, ensure_ascii=False),
                1 if send_provider_extras else 0,
            ),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                actor,
                "update_model_config",
                "model_config",
                "1",
                json.dumps({"model": model, "hasApiKey": bool(api_key)}, ensure_ascii=False),
            ),
        )
    return {"success": True, "message": "模型配置已保存。"}


def reset_model_config(platform_db: PlatformDb, *, actor: str = "system") -> dict[str, Any]:
    """Drop the stored configuration, falling back to the environment.

    The audit row names what went: whether a key was stored, and which model and endpoint were
    discarded. Read from the row itself rather than from the resolved configuration -- after a
    reset the resolution falls back to the environment, so a deployment with `ONTOLOGY_MODEL`
    set would report a key that was never in the table. The key's value is never written: an
    audit log is read by more people than a credential store, and the table that answers "who
    reset this" must not become the place the credential survives. But `detail: {}` answered
    nothing at all -- an administrator reading this row afterwards could not tell whether a key
    had just been destroyed or whether there had never been one.
    """
    with connect(platform_db) as conn:
        stored = conn.execute("select provider, api_key, model, base_url from model_config where id = 1").fetchone()
        detail = {
            "provider": stored["provider"] if stored else "",
            "model": stored["model"] if stored else "",
            "baseUrl": stored["base_url"] if stored else "",
            "hasApiKey": bool(stored["api_key"]) if stored else False,
            "hadStoredConfig": stored is not None,
        }
        conn.execute("delete from model_config where id = 1")
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (actor, "reset_model_config", "model_config", "1", json.dumps(detail, ensure_ascii=False)),
        )
    return {"success": True, "message": "模型配置已重置为环境变量默认值。"}


def test_model_config(platform_db: PlatformDb) -> dict[str, Any]:
    client = OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    status = client.status()
    if not client.configured:
        return {"success": False, "message": f"未配置 {client.provider} API Key。", "status": status}
    try:
        result = client.chat(
            [{"role": "user", "content": "Return a short ok response for connectivity test."}],
            purpose="model_config_test",
            session_id="model-config-test",
        )
        record_model_invocation(platform_db, result, "model_config_test", "success")
        return {
            "success": True,
            "message": f"{client.provider} 连接测试成功。",
            "model": result.model,
            "status": status,
        }
    except Exception as error:
        record_model_invocation(platform_db, None, "model_config_test", "error", str(error), client)
        return {"success": False, "message": describe_model_failure(error), "status": status}


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter HTTP {error.code}: {detail}") from error
    return json.loads(body)


def _metadata_prompt_payload(platform_db: PlatformDb, data_source_id: int) -> dict[str, Any]:
    with connect(platform_db) as conn:
        source = conn.execute("select * from data_source where id = ?", (data_source_id,)).fetchone()
        if source is None:
            raise ValueError(f"数据源不存在: {data_source_id}")
        tables = conn.execute(
            "select * from source_table where data_source_id = ? order by table_name",
            (data_source_id,),
        ).fetchall()
        payload_tables = []
        for table in tables:
            columns = conn.execute(
                "select column_name, data_type, nullable, sample_values, null_ratio, distinct_count, enum_candidate from source_column where source_table_id = ? order by ordinal",
                (table["id"],),
            ).fetchall()
            foreign_keys = conn.execute(
                "select column_name, target_table, target_column from source_foreign_key where source_table_id = ?",
                (table["id"],),
            ).fetchall()
            payload_tables.append(
                {
                    "table": table["table_name"],
                    "rowCount": table["row_count"],
                    "primaryKey": table["primary_key"],
                    "columns": [dict(column) for column in columns],
                    "foreignKeys": [dict(foreign_key) for foreign_key in foreign_keys],
                }
            )
        apis = conn.execute(
            "select operation_code, name, method, path, semantic_action from source_api where data_source_id = ? order by operation_code",
            (data_source_id,),
        ).fetchall()
        return {
            "dataSource": {
                "id": source["id"],
                "name": source["name"],
                "domain": source["domain"],
                "systemCategory": source["system_category"],
                "capabilities": json.loads(source["capabilities"] or "[]"),
            },
            "tables": payload_tables,
            "apis": [dict(api) for api in apis],
        }


def _local_suggestions(metadata: dict[str, Any]) -> dict[str, Any]:
    objects = []
    rules = []
    for table in metadata["tables"]:
        object_name = table["table"].replace("_", " ").title()
        objects.append(
            {
                "code": table["table"],
                "name": object_name,
                "reason": "由表结构自动识别为业务对象候选。",
                "attributes": [column["column_name"] for column in table["columns"]],
            }
        )
        for column in table["columns"]:
            column_name = column["column_name"]
            if column["nullable"] == 0 and column_name != table["primaryKey"]:
                rules.append(
                    {
                        "scope": table["table"],
                        "type": "validation",
                        "rule": f"{column_name} 不应为空",
                    }
                )
    return {
        "objects": objects,
        "rules": rules[:20],
        "governanceRisks": [
            "自动建议必须经业务专家确认后才能发布。",
            "字段样例可能包含敏感信息，接入生产库前应启用脱敏策略。",
        ],
    }


def _local_blueprint_draft(metadata: dict[str, Any]) -> dict[str, Any]:
    domain = metadata["dataSource"].get("domain") or metadata["dataSource"]["name"] or "通用业务"
    slug = _slug(domain or metadata["dataSource"]["name"])
    object_hints = {table["table"]: table["table"].replace("_", " ").title() for table in metadata["tables"]}
    attribute_hints: dict[str, str] = {}
    rules = []
    table_keywords = []
    for table in metadata["tables"]:
        table_keywords.append(table["table"])
        for column in table["columns"]:
            column_name = column["column_name"]
            attribute_hints.setdefault(column_name, column_name.replace("_", " ").title())
            if column["nullable"] == 0 and column_name != table["primaryKey"]:
                rules.append(
                    {
                        "code": f"{table['table']}_{column_name}_required",
                        "name": f"{attribute_hints[column_name]}必填",
                        "rule_type": "validation",
                        "scope_object_code": table["table"],
                        "expression": f"{column_name} != null",
                        "severity": "blocking",
                        "natural_language": f"{object_hints[table['table']]}的{attribute_hints[column_name]}不能为空。",
                    }
                )
    return {
        "id": f"{slug}-draft",
        "name": f"{domain}蓝图草案",
        "domain": domain,
        "description": "由数据源元数据自动生成的行业蓝图草案，导入前建议由业务专家复核。",
        "objectHints": object_hints,
        "attributeHints": attribute_hints,
        "rules": rules[:20],
        "tableKeywords": table_keywords[:20],
        "capabilityTags": ["metadata-derived", "semantic-onboarding"],
    }


def _local_reasoning_chain(metadata: dict[str, Any]) -> dict[str, Any]:
    tables = metadata["tables"]
    objects = [
        {
            "objectCode": table["table"],
            "objectName": table["table"].replace("_", " ").title(),
            "sourceTable": table["table"],
            "reason": f"表 {table['table']} 具有主键 {table['primaryKey']}，可作为业务对象候选。",
            "attributes": [column["column_name"] for column in table["columns"]],
        }
        for table in tables
    ]
    relations = []
    for table in tables:
        for foreign_key in table.get("foreignKeys", []):
            relations.append(
                {
                    "sourceObject": table["table"],
                    "targetObject": foreign_key["target_table"],
                    "sourceForeignKey": foreign_key["column_name"],
                    "reason": "由数据库外键推断业务对象关系。",
                }
            )
    rules = []
    for table in tables:
        for column in table["columns"]:
            if column["nullable"] == 0 and column["column_name"] != table["primaryKey"]:
                rules.append(
                    {
                        "scopeObject": table["table"],
                        "ruleName": f"{column['column_name']} 必填",
                        "severity": "blocking",
                        "reason": "非空字段可作为基础完整性规则。",
                    }
                )
    return {
        "summary": f"识别到 {len(objects)} 个业务对象候选、{len(relations)} 条关系候选和 {len(rules)} 条基础规则候选。",
        "reasoningSteps": [
            "读取数据源表、字段、主键、外键和字段画像。",
            "将可独立拥有主键的表识别为业务对象候选。",
            "将外键约束识别为业务关系候选。",
            "将非空字段、金额、状态、日期等字段识别为规则候选。",
            "将业务 API 的 semanticAction 绑定到对象动作，形成自动化预检入口。",
        ],
        "proposedObjects": objects,
        "proposedRelations": relations,
        "proposedRules": rules[:20],
        "buildPlan": [
            "自动路径：使用一键接入生成本体草案、语义映射和基础规则。",
            "人工路径：业务专家逐项确认对象、字段、关系和规则后再发布本体。",
        ],
        "questionsForUser": [
            "哪些表是主业务对象，哪些只是日志、字典或中间表？",
            "哪些规则应作为阻断级规则，哪些只是复核建议？",
            "哪些业务 API 可以被语义内核自动调用？",
        ],
    }


def _extract_json_object(content: str) -> dict[str, Any]:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start < 0 or end < start:
        raise ValueError("模型未返回 JSON 对象")
    return json.loads(stripped[start : end + 1])


def _string_list(raw: Any, fallback: Any) -> list[str]:
    """A list of strings from whatever the model supplied for a list field.

    A bare string is taken as a one-element list rather than iterated: iterating it yields
    its characters, which turns `"contract"` into six nonsense keywords. This is the same
    reason the reasoning-chain normalizer rejects a non-list `proposedObjects` instead of
    trusting it.
    """
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return [str(item) for item in fallback if str(item).strip()]


# Field names a model may use for the human-readable text of one step or plan entry. The
# reasoning prompt asks for "the process of inferring ..." and "two paths", wording that
# invites a descriptive object per entry. Projecting a known field keeps the model's words
# instead of discarding the entry, and it never invents one.
_TEXT_FIELDS = (
    "text",
    "detail",
    "description",
    "title",
    "step",
    "path",
    "name",
    "question",
    "summary",
    "label",
)


def _text_of(value: Any) -> str:
    """The text of an element the schema says is a string."""
    if isinstance(value, dict):
        for field in _TEXT_FIELDS:
            candidate = value.get(field)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        return ""
    if isinstance(value, (list, tuple, set, frozenset)) or value is None or isinstance(value, bool):
        return ""
    return str(value).strip()


def _text_value(raw: Any, fallback: str) -> tuple[str, bool]:
    """A prose field as a string, and whether anything supplied had to be dropped."""
    if isinstance(raw, str) and raw.strip():
        return raw.strip(), False
    if isinstance(raw, list):
        # A model answering a prose field with one line per point. Joined with newlines
        # rather than stringified, and the joined form still renders as Markdown.
        lines = [text for text in (_text_of(item) for item in raw) if text]
        if lines:
            return "\n".join(lines), len(lines) != len(raw)
    return str(fallback), raw not in (None, "", [], {})


def _text_list(raw: Any, fallback: Any) -> tuple[list[str], bool]:
    """A list of strings, and whether anything the model supplied had to be dropped."""
    if not isinstance(raw, list):
        return [str(item) for item in fallback], raw not in (None, "", [], {})
    items = [text for text in (_text_of(item) for item in raw) if text]
    if not items and raw:
        return [str(item) for item in fallback], True
    return items, len(items) != len(raw)


def _record_list(raw: Any, fallback: Any) -> tuple[list[dict[str, Any]], bool]:
    """A list of records, and whether anything supplied had to be dropped.

    Scalars are dropped rather than kept: the frontend reads these entries as records, so
    a string element renders every field as "-" and the candidate list looks empty without
    anything having failed.
    """
    if not isinstance(raw, list):
        return [item for item in fallback if isinstance(item, dict)], raw not in (None, "", [], {})
    items = [item for item in raw if isinstance(item, dict)]
    if not items and raw:
        return [item for item in fallback if isinstance(item, dict)], True
    return items, len(items) != len(raw)


def _normalize_blueprint(parsed: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge a model's blueprint over the local draft, field by field.

    Returns the blueprint and the names of fields the model supplied that could not be
    read. Field-level rather than all-or-nothing: a shape surprise in one field used to
    raise out of this function, and the caller's broad `except` then discarded the
    *entire* response -- sixteen kilobytes of usable modelling replaced by the local
    heuristic, reported only as `usedRemoteModel: False`, which reads as "no model was
    configured". One unreadable field must cost one field.
    """
    result = dict(fallback)
    for key in (
        "id",
        "name",
        "domain",
        "description",
        "objectHints",
        "attributeHints",
        "rules",
        "tableKeywords",
        "capabilityTags",
    ):
        if key in parsed and parsed[key] not in (None, "", [], {}):
            result[key] = parsed[key]
    result["id"] = _slug(str(result["id"]))

    unreadable: list[str] = []
    # `coerce_hints` is shared with the blueprint import path, so a draft the model wrote
    # and a draft the user imported are read by the same rules -- otherwise the platform
    # could generate a blueprint it then refused to import.
    for key, dotted in (("objectHints", False), ("attributeHints", True)):
        raw = result.get(key)
        hints = coerce_hints(raw, dotted=dotted)
        if not hints and raw not in (None, "", [], {}):
            # Non-empty but unreadable: say so, and use the draft's own hints rather than
            # passing an empty mapping off as the model's work.
            unreadable.append(key)
            hints = coerce_hints(fallback.get(key), dotted=dotted)
        result[key] = hints

    if not isinstance(result.get("rules"), list):
        unreadable.append("rules")
        result["rules"] = list(fallback.get("rules") or [])
    else:
        # Keep only elements the import path can read, using that path's own predicate, so
        # a draft this function produces is always a draft `upsert_industry_blueprint`
        # accepts. Without this, one malformed rule element sent the whole import to a 500
        # -- which is how "generate a draft, then import it" was broken on the way back in
        # as well as on the way out.
        readable_rules = [rule for rule in result["rules"] if rule_is_readable(rule)]
        if len(readable_rules) != len(result["rules"]):
            unreadable.append("rules")
        result["rules"] = readable_rules

    for key in ("tableKeywords", "capabilityTags"):
        raw = result.get(key)
        items = _string_list(raw, fallback.get(key) or [])
        if not items and raw not in (None, "", [], {}):
            # A mapping or a number here was silently swapped for the heuristic's keywords
            # while the response still claimed the model's output was used.
            unreadable.append(key)
        result[key] = items
    return result, unreadable


def _normalize_reasoning_chain(parsed: dict[str, Any], fallback: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge a model's reasoning chain over the local one, field by field.

    Element shapes are coerced, not just containers. Validating only `isinstance(list)`
    let a list of *objects* through into fields the frontend renders as text -- React
    rejects an object child and the error boundary replaces the page -- and let a list of
    *strings* through into fields the frontend reads as records, where every lookup falls
    through and the rows render as "-" with nothing reported.

    The prompt for this endpoint names the seven fields and states no element shape, which
    is the same gap that made the blueprint draft unusable; it was fixed there and left
    standing here, so a model answering per its own reading of "给出…两种路径" produced a
    chain the UI could not draw.
    """
    result = dict(fallback)
    unreadable: list[str] = []

    summary, dropped = _text_value(parsed.get("summary"), fallback.get("summary", ""))
    result["summary"] = summary
    if dropped:
        unreadable.append("summary")

    for key in ("reasoningSteps", "buildPlan", "questionsForUser"):
        texts, dropped = _text_list(parsed.get(key), fallback.get(key) or [])
        result[key] = texts
        if dropped:
            unreadable.append(key)

    for key in ("proposedObjects", "proposedRelations", "proposedRules"):
        records, dropped = _record_list(parsed.get(key), fallback.get(key) or [])
        result[key] = records
        if dropped:
            unreadable.append(key)

    return result, unreadable


def _slug(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "industry"


def record_model_invocation(
    platform_db: PlatformDb,
    result: ModelResult | None,
    purpose: str,
    status: str,
    error: str = "",
    client: OpenRouterClient | None = None,
) -> None:
    provider = result.provider if result else (client.provider if client else "openrouter")
    model = result.model if result else (client.config.model if client else "")
    usage = result.raw.get("usage", {}) if result else {}
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into model_invocation (
                provider, model, purpose, prompt_tokens, completion_tokens, total_tokens, status, error
            )
            values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider,
                model,
                purpose,
                usage.get("prompt_tokens"),
                usage.get("completion_tokens"),
                usage.get("total_tokens"),
                status,
                error,
            ),
        )


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 10:
        return "***"
    return f"{api_key[:6]}...{api_key[-4:]}"


def _model_config_source(platform_db: PlatformDb) -> str:
    with connect(platform_db) as conn:
        row = conn.execute("select id from model_config where id = 1").fetchone()
        if row is not None:
            return "database"
    return "environment"
