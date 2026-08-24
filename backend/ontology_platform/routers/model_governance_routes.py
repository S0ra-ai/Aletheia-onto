"""Model endpoint configuration, AI-assisted drafting, and the governance ledgers.

Three concerns that all trace back to the same boundary: **the model is an adviser, not
an authority**. Configuration decides which endpoint gets called, the AI routes produce
drafts a human must review, and the governance ledgers record what was called and what
was decided.

They belong together because the ledgers are what make the adviser role verifiable.
`/governance/model-invocations` exists so "which answers involved a model" is answerable
after the fact; without it, a deployment cannot distinguish a rule-derived verdict from
a generated one, and the difference is the whole basis of accountability here.

Credentials are redacted on the way out (`credentials.py`). A config endpoint that
echoed the API key back would put it in every browser cache and screenshot.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..database import connect
from ..decisions import list_decisions
from ..http_runtime import platform_db
from ..model_client import (
    OpenRouterClient,
    OpenRouterConfig,
    generate_blueprint_draft,
    generate_ontology_reasoning_chain,
    generate_semantic_suggestions,
    get_model_config,
    reset_model_config,
    test_model_config,
    update_model_config,
)

router = APIRouter()


# -- Request models --


class ModelConfigUpdate(BaseModel):
    apiKey: Optional[str] = None
    model: Optional[str] = None
    baseUrl: Optional[str] = None
    httpReferer: Optional[str] = None
    appTitle: Optional[str] = None
    serviceTier: Optional[str] = None
    timeoutSeconds: Optional[float] = None


@router.get("/model/status")
def model_status() -> dict[str, object]:
    return OpenRouterClient(OpenRouterConfig.from_db_or_env(platform_db())).status()


@router.get("/model/config")
def get_openrouter_config() -> dict[str, object]:
    return get_model_config(platform_db())


@router.post("/model/config")
def update_openrouter_config(payload: ModelConfigUpdate) -> dict[str, object]:
    return update_model_config(platform_db(), payload.model_dump(exclude_unset=True))


@router.delete("/model/config")
def reset_openrouter_config() -> dict[str, object]:
    return reset_model_config(platform_db())


@router.get("/model/config/test")
def test_openrouter_config() -> dict[str, object]:
    return test_model_config(platform_db())


@router.post("/ai/data-sources/{data_source_id}/ontology-suggestions")
def ai_ontology_suggestions(data_source_id: int) -> dict[str, object]:
    try:
        return generate_semantic_suggestions(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/ai/data-sources/{data_source_id}/blueprint-draft")
def ai_blueprint_draft(data_source_id: int) -> dict[str, object]:
    try:
        return generate_blueprint_draft(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/ai/data-sources/{data_source_id}/ontology-reasoning-chain")
def ai_ontology_reasoning_chain(data_source_id: int) -> dict[str, object]:
    try:
        return generate_ontology_reasoning_chain(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/governance/audit-log")
def audit_log(limit: int = 50) -> dict[str, object]:
    with connect(platform_db()) as conn:
        rows = conn.execute(
            """
            select actor, action, target_type, target_id, detail, created_at
            from audit_log
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return {"items": [dict(row) for row in rows]}


@router.get("/governance/model-invocations")
def model_invocations(limit: int = 50) -> dict[str, object]:
    with connect(platform_db()) as conn:
        rows = conn.execute(
            """
            select provider, model, purpose, prompt_tokens, completion_tokens, total_tokens, status, error, created_at
            from model_invocation
            order by id desc
            limit ?
            """,
            (limit,),
        ).fetchall()
        return {"items": [dict(row) for row in rows]}


@router.get("/governance/decisions")
def decisions(limit: int = 50) -> dict[str, object]:
    return {"items": list_decisions(platform_db(), limit)}
