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
    model_client = client or OpenRouterClient()
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

