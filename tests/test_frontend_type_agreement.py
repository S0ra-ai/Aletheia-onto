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

import importlib
import re
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ADMIN_PASSWORD = "frontend-type-agreement-password"

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

    limitations = (ROOT / "docs" / "limitations.zh-CN.md").read_text(encoding="utf-8")
    if typed:
        assert "OpenAPI 生成前端类型" not in limitations, (
            f"{typed} 个端点已有响应类型，可以生成前端类型了——请移除该项技术债记录。"
        )
    else:
        assert "手写" in limitations, "响应仍无类型，限制文档应如实记录前端类型为手写"


# -- The response side, guarded where a screen reads it --

# Each entry: (path, the key holding the rows, the fields the screen reads).
#
# The response side cannot be generated (see above), so it was documented as debt and left
# unguarded -- and it broke four times. `/governance/audit-log` and
# `/governance/model-invocations` returned `dict(row)` while their tables asked for
# camelCase: seven columns blank for every row. `/ontologies/{id}/mappings` blanked five of
# seven on the review queue that gates publication. `/permissions/policies` blanked all
# seven, twenty rows, on the screen that answers "who may do what". None of it failed
# anything, because an antd column whose `dataIndex` does not exist simply draws nothing.
#
# This is not generated agreement and does not pretend to be. It is the contract each
# screen depends on, written down where it can fail: add a field the page reads and it is
# checked; stop sending one and the test names the screen that goes blank.
CHARTED_RESPONSES = (
    ("/governance/audit-log", "items", ("actor", "action", "target_type", "target_id", "detail", "created_at")),
    (
        "/governance/model-invocations",
        "items",
        ("provider", "model", "purpose", "prompt_tokens", "completion_tokens", "total_tokens", "status", "created_at"),
    ),
    (
        "/ontologies/1/mappings",
        "items",
        (
            "mappingType",
            "sourceTable",
            "sourceColumn",
            "targetObjectCode",
            "targetAttributeCode",
            "confidence",
            "status",
        ),
    ),
    # Wire spellings, not the spellings the screens use: the frontend normalises these in
    # `api/index.ts`, and what has to hold is that the keys those normalisers *consume* keep
    # arriving. If `can_read` stops being sent, the normaliser produces 0 and the column is
    # blank again -- silently, exactly as before.
    (
        "/permissions/policies",
        "policies",
        ("role_code", "role_name", "object_code", "can_read", "can_write", "can_execute", "can_delete", "description"),
    ),
    ("/permissions/roles", "roles", ("code", "name", "is_system", "created_at")),
    ("/tools", "tools", ("code", "name", "tool_type", "risk_level", "requires_review", "status", "created_at")),
    ("/data-sources", "dataSources", ("id", "name", "sourceType", "connectionUri")),
    ("/data-sources/1/tables", "tables", ("table_name", "row_count", "primary_key")),
    ("/data-sources/1/apis", "apis", ("operation_code", "name", "method", "path", "semantic_action")),
    ("/ontologies", "items", ("id", "name", "version", "status", "objectCount")),
    ("/ontologies/1", None, ("objects", "attributes", "relations", "mappings", "rules")),
    (
        "/governance/decisions",
        "items",
        ("decisionId", "decisionType", "status", "objectCode", "instanceId", "createdAt"),
    ),
    ("/workbench", None, ("dataSources", "ontologies", "governance", "rules", "decisions", "actionItems", "summary")),
    ("/ontologies/1/graph", "nodes", ("code", "name", "sourceTable", "attributeCount", "ruleCount", "degree")),
    ("/ontologies/1/graph", "edges", ("code", "name", "source", "target", "relationType", "foreignKey")),
    ("/ontologies/1/release-readiness", "gates", ("code", "name", "passed", "severity", "evidence", "remediation")),
    ("/ontologies/1/event-types", "items", ("code", "name", "objectCode", "category", "payloadFields")),
    (
        "/ontologies/1/objects/contract/instances/1/events",
        "items",
        ("eventCode", "eventName", "category", "actor", "occurredAt"),
    ),
    (
        "/ontologies/1/objects/contract/instances/1/versions",
        "versions",
        ("attributeCode", "value", "validFrom", "validTo", "recordedAt"),
    ),
    ("/semantic/objects/contract/instances", "items", ("instanceId", "record")),
    (
        "/semantic/objects/contract/instances/1/explain",
        None,
        ("objectCode", "instanceId", "source", "attributes", "aggregates", "ancestors", "timeline", "asOf"),
    ),
    ("/governance/audit-report/sections", "items", ("section", "name", "answers")),
    # Not listed, because no screen reads them: `/units`, `/source-types` and `/axiom-kinds`
    # are metadata endpoints for pickers that do not exist yet. Listing them would have made
    # this table a description of the API rather than of what the UI depends on -- and the
    # reverse check below now fails on exactly that.
    ("/auth/users", "items", ("username", "displayName", "roleCode", "capabilities", "status", "createdAt")),
    ("/tenants", "items", ("tenant", "schema")),
    ("/industry-blueprints", "items", ("id", "name", "domain", "description")),
    ("/model/config", None, ("provider", "model", "baseUrl", "hasApiKey")),
    ("/knowledge-bases", "items", ("name", "domain", "ontologyName", "sourceType")),
    ("/data-sources/1/readiness", "checks", ("code", "name", "passed", "evidence", "remediation", "weight")),
    ("/data-sources/1/operation-bindings", "items", ("operationCode", "name", "method", "path", "semanticAction")),
    ("/data-sources/1/semantic-coverage", "objects", ("objectCode", "objectName", "sourceTable", "status", "gaps")),
    ("/data-sources/1/schema-drift", None, ("status", "summary", "addedTables", "impacts", "nextActions")),
    # Wire spellings, normalised in `api/index.ts`.
    ("/workflows", "items", ("ontology_id", "object_code", "name", "initial_state", "status", "created_at")),
    (
        "/ontologies/1/rules",
        "items",
        ("code", "name", "ruleType", "scopeObjectCode", "expression", "severity", "naturalLanguage", "status"),
    ),
    ("/admin/backup/list", "backups", ("name", "size", "created_at")),
)


@pytest.fixture
def seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app with a real ontology behind it, so every charted endpoint has rows.

    Rows matter: a field is present in an empty list only in theory, and the four defects
    this checks for were all invisible until a table had something to draw.
    """
    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "legacy_contracts.sqlite3"
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.onboarding import run_onboarding_pipeline
    from ontology_platform.sample_data import create_contract_sample_db

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    initialize_platform_db(platform_db)
    create_contract_sample_db(sample_db)
    run_onboarding_pipeline(
        platform_db,
        "合同管理样例系统",
        "sqlite",
        str(sample_db),
        domain="合同管理",
        system_category="database+api",
        blueprint_id="contract-management",
    )
    from ontology_platform import backup as backup_module
    from ontology_platform.metadata import register_source_api
    from ontology_platform.ontology import generate_ontology_draft
    from ontology_platform.semantic_kernel import assess_instance

    with connect(platform_db) as conn:
        source_id = int(conn.execute("select id from data_source").fetchone()["id"])
        ontology_id = int(conn.execute("select id from ontology").fetchone()["id"])
        # Model invocations are part of the base schema but nothing writes one without a
        # configured model, and an empty list satisfies any assertion about its columns.
        conn.execute(
            "insert into model_invocation (provider, model, purpose, prompt_tokens, completion_tokens,"
            " total_tokens, status) values ('openrouter', 'm', 'qa', 1, 2, 3, 'success')"
        )
    register_source_api(
        platform_db,
        source_id,
        "submit_contract",
        "提交合同审批",
        "POST",
        "/contracts/{id}/submit",
        "contract.submit_for_approval",
    )
    # A verdict, so the decisions table has a row: a contract's shape is only checked by the
    # test if there is something in it to look at.
    draft = generate_ontology_draft(platform_db, source_id)
    assess_instance(platform_db, ontology_id, "contract", "1")
    del draft

    # The optional feature bundles: events, value history, tenancy. Seeded because a list
    # with no rows in it accepts any assertion about its columns, and this guard exists to
    # check columns.
    from ontology_platform.context import PlatformContext
    from ontology_platform.events import EventType, declare_event_type, init_event_schema, record_event
    from ontology_platform.temporal import init_temporal_schema, record_attribute_version
    from ontology_platform.tenancy import provision_tenant

    with connect(platform_db) as conn:
        init_event_schema(conn)
        init_temporal_schema(conn)
    declare_event_type(
        platform_db,
        ontology_id,
        EventType(code="signed", name="签订", object_code="contract"),
        actor="tester",
    )
    record_event(platform_db, ontology_id, "contract", "1", "signed", actor="tester")
    record_attribute_version(platform_db, ontology_id, "contract", "1", "amount", 1200000, actor="tester")
    provision_tenant(PlatformContext(db_type="sqlite", connection_uri=str(platform_db)), "acme")

    # A workflow and a backup archive, for the same reason as the rest: a list with no rows
    # in it accepts any assertion about its columns. The workflow list's 业务对象 / 本体 /
    # 初始状态 columns were blank for every row and stayed invisible exactly as long as no
    # workflow existed.
    from ontology_platform.workflow_permission import (
        create_workflow,
        init_workflow_and_permission_schema,
    )

    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
    create_workflow(platform_db, ontology_id, "contract", "样例审批流", initial_state="draft")
    # `BACKUP_DIR` is read from the environment at import time and defaults to the user's
    # `~/.aletheia/backups`, so the endpoint lists whatever that machine happens to have.
    # Passing `backup_dir` to `create_backup` alone is not enough: it writes where it is
    # told and the endpoint reads the default, which is how this test passed locally (a
    # backup from an earlier manual check was sitting there) and failed in CI.
    monkeypatch.setattr(backup_module, "BACKUP_DIR", tmp_path / "backups")
    backup_module.create_backup(platform_db)

    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as client:
        token = _token(client, "admin", ADMIN_PASSWORD)
        headers = _auth(token)
        # Through the API rather than by inserting rows: these tables live in an optional
        # feature bundle and their foreign keys point at roles the platform creates.
        assert client.post(
            "/permissions/roles", headers=headers, json={"code": "reviewer", "name": "审核员"}
        ).status_code in (200, 201)
        assert client.post(
            "/permissions/policies",
            headers=headers,
            json={"roleId": 1, "objectCode": "contract", "canRead": True, "description": ""},
        ).status_code in (200, 201)
        assert client.post(
            "/tools",
            headers=headers,
            json={"code": "submit", "name": "提交", "toolType": "mutation", "riskLevel": "high"},
        ).status_code in (200, 201)
        yield client
    database_module._platform_adapter = None


@pytest.mark.parametrize(("path", "key", "fields"), CHARTED_RESPONSES)
def test_the_fields_a_screen_reads_are_present_in_the_response(
    seeded_client: TestClient, path: str, key: str | None, fields: tuple[str, ...]
) -> None:
    """Every field a screen reads must exist in the payload it reads it from.

    A missing field is not an error anywhere in this stack: TypeScript checked the type
    declaration, antd drew an empty cell, and the request succeeded. The screen simply
    says nothing, which for a review queue reads as "nothing to review".
    """
    token = _token(seeded_client, "admin", ADMIN_PASSWORD)
    response = seeded_client.get(path, headers=_auth(token))
    assert response.status_code == 200, f"{path}: {response.status_code} {response.text[:200]}"
    payload = response.json()

    if key is None:
        missing = [field for field in fields if field not in payload]
        assert not missing, f"{path} 缺少 {missing}"
        return

    rows = payload.get(key)
    assert isinstance(rows, list), f"{path} 的 {key} 不是列表: {type(rows).__name__}"
    assert rows, f"{path} 没有数据行，这条契约没被真正验证到"
    missing = sorted({field for row in rows for field in fields if field not in row})
    assert not missing, f"{path} 的 {key} 缺少界面读取的字段 {missing}；对应的列会整列为空"


def _token(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_every_contracted_field_is_still_read_by_the_frontend() -> None:
    """The table can rot in the other direction too.

    A field listed here and read by nobody is a stale entry: the endpoint can stop sending
    it, the test stays green, and the claim that screen X reads it is no longer true. The
    check is deliberately loose -- the name has to appear somewhere in the frontend, as a
    `dataIndex`, a type member or a normaliser key -- because the point is to notice an
    entry nothing uses, not to re-derive which table reads what.
    """
    import re as regex

    sources = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "frontend" / "src").rglob("*.ts*"))
    unused = sorted(
        {
            field
            for _path, _key, fields in CHARTED_RESPONSES
            for field in fields
            if not regex.search(rf"\b{regex.escape(field)}\b", sources)
        }
    )
    assert not unused, f"契约表里的字段没有任何前端代码读取，条目已过期：{unused}"
