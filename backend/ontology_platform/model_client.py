from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .database import connect


Transport = Callable[[str, dict[str, str], dict[str, Any], float], dict[str, Any]]


@dataclass(frozen=True)
class OpenRouterConfig:
    api_key: str
    model: str
    base_url: str
    http_referer: str
    app_title: str
    service_tier: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> "OpenRouterConfig":
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY", ""),
            model=os.getenv("OPENROUTER_MODEL", "~openai/gpt-latest"),
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/"),
            http_referer=os.getenv("OPENROUTER_HTTP_REFERER", ""),
            app_title=os.getenv("OPENROUTER_APP_TITLE", "Ontology Transformation Platform"),
            service_tier=os.getenv("OPENROUTER_SERVICE_TIER", "auto"),
            timeout_seconds=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", "30")),
        )

    @classmethod
    def from_db_or_env(cls, platform_db: Path | str) -> "OpenRouterConfig":
        env_config = cls.from_env()
        with connect(platform_db) as conn:
            row = conn.execute("select * from model_config where id = 1").fetchone()
            if row is None:
                return env_config
            return cls(
                api_key=row["api_key"] or env_config.api_key,
                model=row["model"] or env_config.model,
                base_url=(row["base_url"] or env_config.base_url).rstrip("/"),
                http_referer=row["http_referer"] or env_config.http_referer,
                app_title=row["app_title"] or env_config.app_title,
                service_tier=row["service_tier"] or env_config.service_tier,
                timeout_seconds=float(row["timeout_seconds"] or env_config.timeout_seconds),
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
    provider = "openrouter"

    def __init__(self, config: OpenRouterConfig | None = None, transport: Transport | None = None) -> None:
        self.config = config or OpenRouterConfig.from_env()
        self.transport = transport or _post_json

    @property
    def configured(self) -> bool:
        return bool(self.config.api_key)

    def status(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "configured": self.configured,
            "model": self.config.model,
            "baseUrl": self.config.base_url,
            "serviceTier": self.config.service_tier,
            "usesSubscriptionOrCreditKey": self.configured,
            "apiKeySource": "OPENROUTER_API_KEY" if self.configured else "missing",
        }

    def chat(self, messages: list[dict[str, str]], purpose: str = "semantic_assistance", session_id: str | None = None) -> ModelResult:
        if not self.configured:
            raise ValueError("未配置 OPENROUTER_API_KEY，无法调用 OpenRouter 远程模型")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.http_referer:
            headers["HTTP-Referer"] = self.config.http_referer
        if self.config.app_title:
            headers["X-OpenRouter-Title"] = self.config.app_title

        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": False,
        }
        if self.config.service_tier:
            payload["service_tier"] = self.config.service_tier
        if session_id:
            payload["session_id"] = session_id

        raw = self.transport(
            f"{self.config.base_url}/chat/completions",
            headers,
            payload,
            self.config.timeout_seconds,
        )
        content = raw.get("choices", [{}])[0].get("message", {}).get("content", "")
        return ModelResult(
            provider=self.provider,
            model=raw.get("model", self.config.model),
            configured=True,
            used_remote_model=True,
            content=content,
            raw=raw,
        )


def generate_semantic_suggestions(
    platform_db: Path | str,
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
        _record_model_invocation(platform_db, result, "ontology_suggestions", "success")
        return {
            "provider": result.provider,
            "model": result.model,
            "usedRemoteModel": result.used_remote_model,
            "content": result.content,
            "openrouter": model_client.status(),
        }
    except Exception as error:
        _record_model_invocation(platform_db, None, "ontology_suggestions", "error", str(error), model_client)
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "content": _local_suggestions(metadata),
            "openrouter": model_client.status(),
            "remoteError": str(error),
        }


def generate_blueprint_draft(
    platform_db: Path | str,
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
                "rules 的元素必须包含 code,name,rule_type,scope_object_code,expression,severity,natural_language。"
            ),
        },
        {"role": "user", "content": json.dumps(metadata, ensure_ascii=False)},
    ]
    try:
        result = model_client.chat(messages, purpose="blueprint_draft", session_id=f"blueprint-{data_source_id}")
        _record_model_invocation(platform_db, result, "blueprint_draft", "success")
        parsed = _extract_json_object(result.content)
        return {
            "provider": result.provider,
            "model": result.model,
            "usedRemoteModel": result.used_remote_model,
            "blueprint": _normalize_blueprint(parsed, local),
            "openrouter": model_client.status(),
        }
    except Exception as error:
        _record_model_invocation(platform_db, None, "blueprint_draft", "error", str(error), model_client)
        return {
            "provider": "local-heuristic",
            "model": "metadata-profile",
            "usedRemoteModel": False,
            "blueprint": local,
            "openrouter": model_client.status(),
            "remoteError": str(error),
        }


def get_model_config(platform_db: Path | str) -> dict[str, Any]:
    config = OpenRouterConfig.from_db_or_env(platform_db)
    source = _model_config_source(platform_db)
    return {
        "configured": bool(config.api_key),
        "provider": "openrouter",
        "apiKey": _mask_api_key(config.api_key),
        "hasApiKey": bool(config.api_key),
        "model": config.model,
        "baseUrl": config.base_url,
        "httpReferer": config.http_referer,
        "appTitle": config.app_title,
        "serviceTier": config.service_tier,
        "timeoutSeconds": config.timeout_seconds,
        "source": source,
    }


def update_model_config(platform_db: Path | str, payload: dict[str, Any]) -> dict[str, Any]:
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
    with connect(platform_db) as conn:
        conn.execute(
            """
            insert into model_config (
                id, provider, api_key, model, base_url, http_referer,
                app_title, service_tier, timeout_seconds, updated_at
            )
            values (1, 'openrouter', ?, ?, ?, ?, ?, ?, ?, current_timestamp)
            on conflict(id) do update set
                api_key = excluded.api_key,
                model = excluded.model,
                base_url = excluded.base_url,
                http_referer = excluded.http_referer,
                app_title = excluded.app_title,
                service_tier = excluded.service_tier,
                timeout_seconds = excluded.timeout_seconds,
                updated_at = current_timestamp
            """,
            (api_key, model, base_url, http_referer, app_title, service_tier, timeout_seconds),
        )
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            ("system", "update_model_config", "model_config", "1", json.dumps({"model": model, "hasApiKey": bool(api_key)}, ensure_ascii=False)),
        )
    return {"success": True, "message": "模型配置已保存。"}


def reset_model_config(platform_db: Path | str) -> dict[str, Any]:
    with connect(platform_db) as conn:
        conn.execute("delete from model_config where id = 1")
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            ("system", "reset_model_config", "model_config", "1", "{}"),
        )
    return {"success": True, "message": "模型配置已重置为环境变量默认值。"}


def test_model_config(platform_db: Path | str) -> dict[str, Any]:
    client = OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db))
    status = client.status()
    if not client.configured:
        return {"success": False, "message": "未配置 OpenRouter API Key。", "status": status}
    try:
        result = client.chat(
            [{"role": "user", "content": "Return a short ok response for connectivity test."}],
            purpose="model_config_test",
            session_id="model-config-test",
        )
        _record_model_invocation(platform_db, result, "model_config_test", "success")
        return {"success": True, "message": "OpenRouter 连接测试成功。", "model": result.model, "status": status}
    except Exception as error:
        _record_model_invocation(platform_db, None, "model_config_test", "error", str(error), client)
        return {"success": False, "message": str(error), "status": status}


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


def _metadata_prompt_payload(platform_db: Path | str, data_source_id: int) -> dict[str, Any]:
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


def _normalize_blueprint(parsed: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    result = dict(fallback)
    for key in ("id", "name", "domain", "description", "objectHints", "attributeHints", "rules", "tableKeywords", "capabilityTags"):
        if key in parsed and parsed[key] not in (None, "", [], {}):
            result[key] = parsed[key]
    result["id"] = _slug(str(result["id"]))
    result["objectHints"] = {str(key).split(".")[-1]: str(value) for key, value in dict(result.get("objectHints") or {}).items()}
    attribute_hints = {str(key): str(value) for key, value in dict(result.get("attributeHints") or {}).items()}
    for key, value in list(attribute_hints.items()):
        if "." in key:
            attribute_hints.setdefault(key.split(".")[-1], value)
    result["attributeHints"] = attribute_hints
    result["tableKeywords"] = [str(item) for item in result.get("tableKeywords") or []]
    result["capabilityTags"] = [str(item) for item in result.get("capabilityTags") or []]
    return result


def _slug(value: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in value)
    normalized = "-".join(part for part in normalized.split("-") if part)
    return normalized or "industry"


def _record_model_invocation(
    platform_db: Path | str,
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


def _model_config_source(platform_db: Path | str) -> str:
    with connect(platform_db) as conn:
        row = conn.execute("select id from model_config where id = 1").fetchone()
        if row is not None:
            return "database"
    return "environment"
