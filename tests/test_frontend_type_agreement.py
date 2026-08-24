"""The frontend's hand-written types must agree with the API they mirror.

`frontend/src/types/index.ts` is 1143 hand-written lines mirroring the backend models.
ROADMAP records this as debt, and the reason it is debt is not the duplication -- it is
that **the two copies can disagree with nothing failing**.

That is not hypothetical. `ModelConfigUpdate` declared four fields in TypeScript
(`authStyle`, `authHeader`, `extraHeaders`, `sendProviderExtras`) that the API model did
not, and Pydantic drops an undeclared field silently. So the settings screen sent them,
reported success, and changed nothing: configuring Azure (which needs an `api-key` header
rather than `Authorization: Bearer`) or a local vLLM (which rejects OpenRouter's extra
fields with a 400) was impossible through the UI, and the next model call failed for a
reason that pointed at the endpoint rather than at the save.

## Why this instead of generating the types

Generating from OpenAPI is the obvious fix and does not work yet: all 144 endpoints
return `dict[str, object]`, so every *response* schema is a bare object and a generator
would emit `unknown`. Annotating 144 response models would freeze the response shapes
into the API layer, which is a larger commitment than this debt justifies.

What is generatable today is the **request** side, since those are real Pydantic models.
So this asserts agreement on exactly that surface -- where a mismatch silently discards
user input -- and leaves the response side documented as debt rather than pretending it
is solved.

A mismatch in the other direction is checked too: a field the API accepts and the
frontend does not declare is a feature no user can reach.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

TYPES = ROOT / "frontend" / "src" / "types" / "index.ts"

# Interfaces the frontend maintains as mirrors of an API request model. Listed explicitly
# rather than matched by name: the frontend also declares view models and response shapes
# that have no backend counterpart, and comparing those would produce failures nobody can
# act on -- which is how a check gets deleted.
MIRRORED_REQUEST_MODELS = (
    "DataSourceCreate",
    "ModelConfigUpdate",
    "OntologyDraftCreate",
    "SourceApiCreate",
    "OnboardingRunCreate",
)


def _api_schemas() -> dict:
    from ontology_platform.api import app

    return app.openapi()["components"]["schemas"]


def _typescript_fields(name: str) -> set[str]:
    """Field names declared on one exported interface, excluding inherited ones.

    Inherited fields are excluded because `extends` already ties them to the parent, and
    the parent is checked on its own.
    """
    source = TYPES.read_text(encoding="utf-8")
    match = re.search(r"export interface " + name + r"\s*(?:extends [\w, ]+)?\{(.*?)\n\}", source, re.S)
    assert match, f"前端未声明 {name}"
    return {field.group(1) for field in re.finditer(r"^\s*(\w+)\??:", match.group(1), re.M)}


def _inherited(name: str) -> set[str]:
    source = TYPES.read_text(encoding="utf-8")
    match = re.search(r"export interface " + name + r"\s*extends ([\w, ]+)\{", source)
    if not match:
        return set()
    fields: set[str] = set()
    for parent in (item.strip() for item in match.group(1).split(",")):
        if parent:
            fields |= _typescript_fields(parent) | _inherited(parent)
    return fields


@pytest.mark.parametrize("model", MIRRORED_REQUEST_MODELS)
def test_the_frontend_does_not_send_fields_the_api_discards(model) -> None:
    """The direction that already caused a bug.

    Pydantic drops an undeclared field without complaint, so the request succeeds and the
    value disappears. A user sees "saved" and gets nothing.
    """
    api_fields = set(_api_schemas()[model].get("properties", {}))
    declared = _typescript_fields(model) | _inherited(model)

    discarded = sorted(declared - api_fields)
    assert not discarded, (
        f"{model}: 前端发送但 API 未声明的字段会被静默丢弃: {discarded}。请在请求模型中声明，或从前端类型中移除。"
    )


@pytest.mark.parametrize("model", MIRRORED_REQUEST_MODELS)
def test_the_frontend_can_reach_every_field_the_api_accepts(model) -> None:
    """The other direction: a field only the API knows about is a feature no user can use.

    Less dangerous than silent discard, and still worth failing on -- an accepted field
    that no client sends is indistinguishable from one that was never implemented.
    """
    api_fields = set(_api_schemas()[model].get("properties", {}))
    declared = _typescript_fields(model) | _inherited(model)

    unreachable = sorted(api_fields - declared)
    assert not unreachable, (
        f"{model}: API 接受但前端未声明的字段无法从界面到达: {unreachable}。"
        "请补充前端类型，或说明该字段仅供 API 调用方使用。"
    )


def test_the_model_config_compatibility_settings_reach_the_backend() -> None:
    """The specific regression, asserted end to end rather than by field comparison.

    These four settings are the difference between "supports any OpenAI-compatible
    endpoint" being true and being a claim: Azure passes credentials in `api-key`, and
    vLLM returns 400 on OpenRouter's extra fields. A field comparison would pass if both
    sides dropped them together, so this checks the value actually survives a round trip.
    """
    from ontology_platform.routers.model_governance_routes import ModelConfigUpdate

    payload = ModelConfigUpdate(
        authStyle="api-key",
        authHeader="api-key",
        extraHeaders={"X-Tenant": "acme"},
        sendProviderExtras=False,
    ).model_dump(exclude_unset=True)

    assert payload["authStyle"] == "api-key"
    assert payload["authHeader"] == "api-key"
    assert payload["extraHeaders"] == {"X-Tenant": "acme"}
    assert payload["sendProviderExtras"] is False


def test_the_response_side_is_recorded_as_debt_rather_than_claimed_as_done() -> None:
    """Generating response types is blocked, and the blocker should be visible.

    Every endpoint returns `dict[str, object]`, so OpenAPI carries no response schema and
    a generator would emit `unknown`. Asserting the blocker still exists means the day
    someone annotates the responses, this test fails and prompts removing the debt entry
    -- rather than the entry outliving the problem.
    """
    from ontology_platform.api import app

    schema = app.openapi()
    typed = 0
    for operations in schema["paths"].values():
        for operation in operations.values():
            body = operation.get("responses", {}).get("200", {}).get("content", {})
            response_schema = body.get("application/json", {}).get("schema", {})
            if response_schema.get("$ref") or response_schema.get("properties"):
                typed += 1

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    if typed:
        assert "OpenAPI 生成前端类型" not in readme, (
            f"{typed} 个端点已有响应类型，可以生成前端类型了——请移除该项技术债记录。"
        )
    else:
        assert "手写" in readme, "响应仍无类型，README 应如实记录前端类型为手写"
