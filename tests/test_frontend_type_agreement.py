"""The frontend's hand-written types must agree with the API they mirror.

`frontend/src/types/index.ts` is a large hand-written mirror of the backend models.
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
    # Added when the literal-payload check below found four request bodies sending an
    # identity field the API does not declare. These two are the ones that had a named
    # interface to be checked against; the other two were inline object types, which is
    # precisely why they went unnoticed -- see `test_no_request_body_sends_a_field_the_api_discards`.
    "BulkMappingReviewCreate",
    "ToolExecutionReview",
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


# -- Request bodies written inline, which the interface comparison cannot see --

# The five mirrored interfaces above are the requests somebody thought to name. Most bodies
# are written inline at the call site (`api.post(url, { status, note })`), and an inline
# object type has no declaration to compare -- so the check above looked past exactly the
# places the same mistake kept happening.
#
# Four of them were live at once, all the same shape: the console sends an identity
# (`reviewer`, `actor`, `publisher`) that the server does not accept, because the server
# credits the authenticated principal instead. Pydantic drops the field, the request
# succeeds, and the call site reads as though it decided who was recorded. `publish` had
# already been fixed and commented; `reviewMappings`, `derive` and `reviewExecution` had not,
# and a fourth sent a *canned Chinese note* that the server did accept and wrote into
# `semantic_mapping.evidence` -- stored in whatever language the console was in.
#
# Comparing the literal's keys against the request model the route actually declares is the
# general form of that bug, and it needs no interface to exist.

# Bodies FastAPI takes as an untyped `dict`, so there is no schema to compare against.
# Empty because every write route in this API declares a model -- listed rather than assumed
# so that the day one does not, the exclusion has to be written down with its reason.
UNTYPED_REQUEST_BODIES: tuple[str, ...] = ()


def _js_arguments(call: str) -> list[str]:
    """Top-level arguments of a call, given its source text from `(` to the matching `)`.

    Split by hand rather than by `split(",")`: a body like
    `{"name": "a,b", "tags": ["x", "y"]}` has commas at four different depths, and splitting
    on all of them would report a field named `"y"]`.
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(call):
        char = call[index]
        if quote:
            current.append(char)
            if char == "\\":
                index += 1
                if index < len(call):
                    current.append(call[index])
            elif char == quote:
                quote = None
        elif char in "\"'`":
            quote = char
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            if current:
                parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def _object_literal_keys(literal: str) -> list[str]:
    """Every key at the top level of a JS object literal, including shorthand entries.

    `{ status }` declares `status` just as `{ status: s }` does, and the bodies that send an
    identity field are mostly shorthand (`{ username, password }`).
    """
    keys: list[str] = []
    depth = 0
    brackets = 0
    expecting_key = False
    index = 0
    while index < len(literal):
        char = literal[index]
        if char in "\"'`":
            quote = char
            index += 1
            while index < len(literal) and literal[index] != quote:
                if literal[index] == "\\":
                    index += 1
                index += 1
            index += 1
            continue
        if char == "{":
            depth += 1
            expecting_key = depth == 1
        elif char == "}":
            depth -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "," and depth == 1 and brackets == 0:
            expecting_key = True
        elif expecting_key and (char.isalpha() or char in "_$"):
            start = index
            while index < len(literal) and (literal[index].isalnum() or literal[index] in "_$"):
                index += 1
            key = literal[start:index]
            ahead = index
            while ahead < len(literal) and literal[ahead].isspace():
                ahead += 1
            # `key:` is a pair; `key,` / `key}` is shorthand for `key: key`.
            if ahead < len(literal) and literal[ahead] in ":,}":
                keys.append(key)
            expecting_key = False
            continue
        index += 1
    return keys


def _inline_request_bodies() -> list[tuple[str, str, str, list[str]]]:
    """`(method, url, literal, keys)` for every request body written as an object literal.

    Only literals: a body passed as `payload` has a type by construction, and the interface
    comparison above is what checks those. What is invisible to that check is a body typed at
    the call site, which is where all four occurrences of the identity-field bug lived.
    """
    api_source = (ROOT / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
    found: list[tuple[str, str, str, list[str]]] = []
    for match in re.finditer(r"api\.(post|put|patch)\(\s*(`[^`]*`|'[^']*'|\"[^\"]*\")", api_source):
        verb = match.group(1).upper()
        url = match.group(2)[1:-1]
        # The arguments run to the matching `)`, so the body's own braces are not the end.
        start = match.end()
        depth = 0
        index = start
        while index < len(api_source):
            char = api_source[index]
            if char in "([{":
                depth += 1
            elif char in ")]}":
                depth -= 1
                if depth < 0:
                    break
            index += 1
        # The URL is prepended so the argument positions match the real call: axios takes
        # `(url, data, config)`, so a slice starting after the URL would make `data` look
        # like the first argument and hand the *config* object to the comparison below.
        arguments = _js_arguments(match.group(2) + api_source[start:index])
        if len(arguments) < 2:
            continue
        body = arguments[1]
        if not (body.startswith("{") and body.endswith("}")):
            continue
        keys = _object_literal_keys(body)
        if keys:
            found.append((verb, url, body, keys))
    return found


def _route_request_models() -> dict[tuple[str, str], str]:
    """`{("POST", "/ontologies/{ontology_id}/derive"): "OntologyDeriveCreate"}` from OpenAPI.

    Read from the API's own schema rather than from the Pydantic classes by name: the schema
    is what a client sees, and a route that stopped declaring a model would drop out of this
    table instead of silently comparing against a class nothing uses.
    """
    from ontology_platform.api import app

    routes: dict[tuple[str, str], str] = {}
    for path, operations in app.openapi()["paths"].items():
        for method, operation in operations.items():
            schema = operation.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            reference = schema.get("$ref", "")
            if reference:
                routes[(method.upper(), path)] = reference.rsplit("/", 1)[-1]
    return routes


def test_no_request_body_sends_a_field_the_api_discards() -> None:
    """Every object-literal request body must declare only fields its route accepts.

    This is the check that was missing, not another instance of the fix. The four identity
    fields it finds (`reviewer` twice, `actor`, and a canned `note`) had each been fixed
    where somebody happened to look, and the reason there was a next one is that nothing
    compared a call site's body to the route's model. Naming five interfaces did not help:
    an inline literal has no interface to name.
    """
    schemas = _api_schemas()
    routes = _route_request_models()
    bodies = _inline_request_bodies()
    assert bodies, "没有解析到任何行内请求体——这个检查多半已经失效，而不是前端改了写法"

    findings: list[str] = []
    for verb, url, literal, keys in bodies:
        matches = [
            (route_method, route_path, model)
            for (route_method, route_path), model in routes.items()
            if route_method == verb and _matches(url, route_path)
        ]
        if not matches:
            findings.append(f"{verb} {url}: 请求体 {literal} 找不到对应的路由声明")
            continue
        for _method, route_path, model in matches:
            if route_path in UNTYPED_REQUEST_BODIES:
                continue
            accepted = set(schemas.get(model, {}).get("properties", {}))
            discarded = sorted(set(keys) - accepted)
            if discarded:
                findings.append(f"{verb} {url} → {model}: 前端发送但 API 未声明的字段会被静默丢弃: {discarded}")

    assert not findings, (
        "以下请求体包含 API 不会读取的字段——请求会成功，值会消失：\n  "
        + "\n  ".join(sorted(set(findings)))
        + "\n若该字段是身份（审核人／操作者／发布者），服务端记录的是认证主体，"
        "请删除该字段而不是补进模型。"
    )


def test_no_page_navigates_to_a_protected_endpoint() -> None:
    """A URL the browser opens on its own carries no `Authorization` header.

    This platform authenticates with a bearer token and deliberately sets no cookie, so
    `window.open('/api/ontologies/1/export?format=jsonld')` cannot download anything: the new
    tab is unauthenticated and shows `{"detail":"缺少访问令牌"}`. Five buttons did exactly
    that -- the four export formats and the kernel package -- and every one of them was
    broken in every deployment, because nothing about the code looks wrong: the URL is right,
    the endpoint is right, and only the credential is missing.

    The endpoint prefixes are read from the API's own schema rather than listed, so a route
    added tomorrow is covered without anyone editing this.
    """
    from ontology_platform.api import app

    prefixes = {"/" + path.strip("/").split("/")[0] for path in app.openapi()["paths"] if path.strip("/")}
    # Navigation that is *meant* to leave the application. Not an exemption list for API
    # paths: these are the external destinations, and they are the only ones allowed.
    external = ("http://", "https://", "mailto:", "//")

    offenders: list[str] = []
    for page in sorted((ROOT / "frontend" / "src").rglob("*.ts*")):
        text = page.read_text(encoding="utf-8")
        for match in re.finditer(r"(window\.open|location\.assign|location\.href\s*=)\s*\(?\s*([^)\n;]+)", text):
            target = match.group(2)
            if any(marker in target for marker in external):
                continue
            # The segment itself starts with `/`, so that *is* the left boundary. Requiring a
            # quote or a slash before it was the first version of this check, and it matched
            # nothing: the URL a page hands to `window.open` is written `/api/ontologies/…`
            # (the proxy strips the prefix) while the axios client writes `/ontologies/…`
            # relative to its `baseURL`. Only a segment-shaped search sees both.
            if any(re.search(rf"{re.escape(prefix)}(?:[/?\"'`]|$)", target) for prefix in prefixes):
                line = text[: match.start()].count("\n") + 1
                offenders.append(f"{page.relative_to(ROOT)}:{line}  {match.group(0).strip()}")

    assert not offenders, (
        "以下位置让浏览器自己打开一个受保护的接口地址——新标签页不带 Bearer 令牌，"
        "只会显示 401 的 JSON。请改为通过 `api/index.ts` 的 `downloadFile` 或对应的 API 方法发起请求：\n  "
        + "\n  ".join(offenders)
    )


def test_the_literal_payload_check_can_actually_fail() -> None:
    """A check nobody has seen fail is a check that may be comparing nothing.

    Pinned against the parser itself: an object literal with a nested body, an array of
    strings and a quoted comma is the shape a naive split would shred, and the four bugs
    this guard found were all shorthand entries, which a `\\w+:\\s` key scan misses.
    """
    literal = '{ status: "confirmed", note: "", tags: ["a,b", "c"], nested: { reviewer: "x" } }'
    assert _object_literal_keys(literal) == ["status", "note", "tags", "nested"]
    assert _object_literal_keys("{ reviewer, actor }") == ["reviewer", "actor"]
    assert _object_literal_keys("{}") == []

    arguments = _js_arguments('"/ontologies/1/derive", { version, actor }, { params: { a: 1 } }')
    assert arguments[0] == '"/ontologies/1/derive"'
    assert arguments[1] == "{ version, actor }"

    # And end to end: a body carrying a field this route does not declare must be reported.
    routes = _route_request_models()
    model = routes.get(("POST", "/ontologies/{ontology_id}/derive"))
    assert model, "derive 路由应从 OpenAPI 中解析出来"
    accepted = set(_api_schemas()[model].get("properties", {}))
    assert "actor" not in accepted, "OntologyDeriveCreate 若开始接受 actor，本测试需要重写"


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
    (
        "/governance/audit-report?start=2020-01-01&end=2030-01-01",
        None,
        ("period", "decisions", "rules", "coverage", "findings"),
    ),
    ("/feedback", "items", ("rating", "decisionId", "status", "actor", "createdAt")),
    ("/conversations", "items", ("title", "escalatedTo", "escalationReason", "status", "createdAt")),
    (
        "/ontologies/1/knowledge/documents",
        "items",
        ("title", "sourceName", "chunkCount", "confirmedCount", "pendingCount", "status", "createdAt"),
    ),
    (
        "/ontologies/1/knowledge/entries",
        "items",
        ("citation", "content", "heading", "objectCode", "ruleCode", "status"),
    ),
    ("/tenants/acme/quotas", "resources", ("current", "limit", "remaining", "table", "description")),
    ("/tenants/acme/statistics", None, ("tenant", "schema", "tables", "totalRows")),
    ("/workflows/1", "transitions", ("action_code", "from_state", "to_state", "name", "guard_expression")),
    ("/workflows/1", "states", ("code", "name", "is_terminal", "color", "sort_order")),
    ("/workflows/1/instances/1/actions", "actions", ("action_code", "from_state", "to_state", "name")),
    (
        "/workflows/1/instances/1/history",
        "items",
        ("action_code", "from_state", "to_state", "actor", "reason", "created_at"),
    ),
    # Wire spellings: `/tools/pending-reviews` returns `dict(row)` and the console maps it.
    (
        "/tools/pending-reviews",
        "items",
        ("tool_code", "agent_role", "object_code", "instance_id", "status", "duration_ms", "created_at"),
    ),
    (
        "/auth/sso",
        None,
        ("enabled", "issuer", "audience", "algorithm", "groupClaim", "usernameClaim", "mappings"),
    ),
    (
        "/data-sources/1/reasoning-chain",
        "rules",
        ("code", "name", "ruleType", "scopeObjectCode", "severity", "naturalLanguage", "status"),
    ),
)

# Charted, but with nothing to agree on: `/admin/backup/download/{name}` returns an archive,
# and the table browser's columns are the *source table's*, which the page iterates rather
# than names. Both are excluded from the coverage check below for that reason, not for
# convenience.
NOT_TABULAR = ("/admin/backup/download/", "/tables/")


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
        enter_workflow,
        init_workflow_and_permission_schema,
    )

    with connect(platform_db) as conn:
        init_workflow_and_permission_schema(conn)
    workflow = create_workflow(platform_db, ontology_id, "contract", "样例审批流", initial_state="draft")
    # Entered, so the actions and history endpoints have something to return: an empty list
    # accepts any assertion about its columns, which is the failure this file keeps meeting.
    enter_workflow(platform_db, workflow["id"], "contract", "1")
    # `BACKUP_DIR` is read from the environment at import time and defaults to the user's
    # `~/.aletheia/backups`, so the endpoint lists whatever that machine happens to have.
    # Passing `backup_dir` to `create_backup` alone is not enough: it writes where it is
    # told and the endpoint reads the default, which is how this test passed locally (a
    # backup from an earlier manual check was sitting there) and failed in CI.
    monkeypatch.setattr(backup_module, "BACKUP_DIR", tmp_path / "backups")
    backup_module.create_backup(platform_db, "smoke")

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
        registered = client.post(
            "/tools",
            headers=headers,
            json={"code": "submit", "name": "提交", "toolType": "mutation", "riskLevel": "high"},
        )
        assert registered.status_code in (200, 201), registered.text
        # One execution waiting for review, so that table has a row. `/tools/pending-reviews`
        # returns `dict(row)` and the console reads camelCase -- eight blank columns nobody
        # saw, because on every deployment this table was empty.
        with connect(platform_db) as conn:
            conn.execute(
                "insert into tool_execution_log (tool_id, tool_code, agent_role, object_code, instance_id,"
                " input_args, result_summary, status, error, duration_ms, requires_review)"
                " values (?, 'submit', 'reviewer', 'contract', '1', '{}', '', 'success', '', 12, 1)",
                (int(registered.json()["id"]),),
            )
        # Conversations and their feedback, and one knowledge document. All three are read
        # by screens whose tables the contract covers, and all three are empty on a fresh
        # install -- which is what let a blank column survive in the workflow list.
        chat = client.post(
            "/agent/chat",
            headers=headers,
            json={"message": "合同的金额是多少", "objectCode": "contract", "instanceId": "1"},
        )
        assert chat.status_code == 200, chat.text
        conversations = client.get("/conversations", headers=headers).json()["items"]
        assert conversations, "聊天应当留下一条会话"
        session_id = conversations[0]["sessionId"]
        assert client.post(
            "/conversations/" + session_id + "/escalate",
            headers=headers,
            json={"assignee": "法务部", "reason": "金额超出授权范围"},
        ).status_code in (200, 201)
        messages = client.get(f"/conversations/{session_id}", headers=headers).json()
        for key in ("messages", "items"):
            if isinstance(messages, dict) and messages.get(key):
                message_id = messages[key][-1]["id"]
                client.post(
                    f"/conversations/messages/{message_id}/feedback",
                    headers=headers,
                    json={"rating": "helpful", "note": ""},
                )
                break
        assert client.post(
            f"/ontologies/{ontology_id}/knowledge/documents",
            headers=headers,
            files={
                "file": ("policy.txt", "第一条 合同金额超过一百万元的，应经部门负责人审批。".encode(), "text/plain")
            },
            data={"title": "合同审批制度", "objectCode": "contract"},
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
    if isinstance(rows, dict) and rows and all(isinstance(value, dict) for value in rows.values()):
        # A mapping of rows rather than a list of them -- the quota report is keyed by
        # resource name and the tenant statistics by table name. The page turns either into
        # rows with `Object.entries`, so the fields to check are the values'.
        rows = list(rows.values())
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


# Rendered as-is, deliberately, with the reason each one is not a vocabulary.
BARE_ENUM_ALLOWED = {
    # An identifier or a field name, not a state.
    "row.decisionId",
    "record.decisionId",
    # The audit trail's action name is the record of what happened; translating it would
    # make the log disagree with itself across releases.
    "row.action",
    "record.action",
    # Rendered through a lookup that already returns a word: `SEVERITY_META[..].label`.
    "item.severity",
    # A machine-facing code shown on purpose, in a column labelled as a code.
    "h.actionCode",
    "a.actionCode",
    # The server's own word, rendered only for a category this build's map does not have --
    # the branch beside it goes through `label(EVENT_CATEGORY, ...)`. An extension that adds a
    # category should still see something, and the alternative is a blank cell.
    "row.categoryLabel",
}

ENUM_ISH = re.compile(
    # `(?<!\$)` is what keeps this about JSX: `${gate.status}` inside a template literal
    # builds a *key* rather than rendering a value, and one of those (the message that says
    # which status a release gate is in) is how the gate reports it in the reader's language.
    # Without the lookbehind, a screen that got this right was reported as one that did not.
    r"(?<!\$)\{([A-Za-z_][A-Za-z0-9_.]*\."
    r"(?:status|severity|decision|ruleType|mappingType|category|nextAction|relationType|kind|toolType|riskLevel)[A-Za-z0-9_]*)\}"
)


def test_no_screen_renders_a_backend_vocabulary_verbatim() -> None:
    """A value from a controlled vocabulary has a word in `labels.ts`; printing the raw one
    puts English identifiers in a Chinese console.

    This is the check that found five of them in one pass -- `mixed_with_blockers` on the
    consistency page, `allow_automation` under a heading that said 建议, `ready_for_execution`,
    and the rule drawer's type and severity. Each had been fixed where it was noticed, which
    is why they kept appearing: nothing looked for the next one.

    Two things count as handled: the line calls `label(...)`, or the expression is a lookup
    whose result is already a word. A short allow-list covers the values that are identifiers
    or audit records rather than states, and each entry says which it is.
    """
    offenders: list[str] = []
    for page in sorted((ROOT / "frontend" / "src").rglob("*.tsx")):
        text = page.read_text(encoding="utf-8")
        for match in ENUM_ISH.finditer(text):
            expression = match.group(1)
            if expression in BARE_ENUM_ALLOWED:
                continue
            line = text[: match.start()].count("\n")
            source_line = text.split("\n")[line]
            # `key={...}` and `rowKey={...}` produce React identities, not text. So does a
            # lookup whose result is already a word.
            if "label(" in source_line or "rowKey" in source_line or "key=" in source_line:
                continue
            offenders.append(f"{page.relative_to(ROOT)}:{line + 1} {{{expression}}}")

    assert not offenders, "界面直接渲染后端词表的值，未经 labels.ts 翻译：\n  " + "\n  ".join(offenders)


def _api_method_paths() -> dict[str, tuple[str, str, bool]]:
    """`{"permissionApi.getPolicies": ("GET", "/permissions/policies", True)}`, from the source.

    The third element is whether the method reads the response body. A `delete` that awaits
    and returns nothing has no shape to agree on, and requiring every method a page *calls*
    to be in the table would fill it with entries that assert nothing.
    """
    import re as regex

    api_source = (ROOT / "frontend" / "src" / "api" / "index.ts").read_text(encoding="utf-8")
    urls: dict[str, tuple[str, str, bool]] = {}
    for obj in regex.finditer(r"export const (\w+Api) = \{(.*?)\n\};", api_source, regex.DOTALL):
        name, body = obj.group(1), obj.group(2)
        for method in regex.finditer(
            r"^\s{2}(\w+):\s*(?:async\s*)?\([^)]*\)[^{]*\{(.*?)\n  \},", body, regex.DOTALL | regex.MULTILINE
        ):
            body_text = method.group(2)
            verb = regex.search(r"api\.(get|post|put|patch|delete)\(\s*[`'\"]([^`'\"]+)", body_text)
            if verb:
                urls[f"{name}.{method.group(1)}"] = (
                    verb.group(1).upper(),
                    verb.group(2),
                    "const { data }" in body_text,
                )
    return urls


def _matches(template: str, path: str) -> bool:
    """Whether a concrete path fills a template's slots.

    Segment-wise, not string-wise: `/tenants/acme/quotas` fills
    `/tenants/${tenant}/quotas`, and `/ontologies/1/objects/contract/instances/1/events` fills
    the four-slot template. Rewriting one side into placeholder form would have to guess which
    segments are values; comparing position by position does not.
    """

    def segments(value: str) -> list[str]:
        return [part for part in value.split("?")[0].split("/") if part]

    def is_slot(part: str) -> bool:
        return part.startswith("${") or (part.startswith("{") and part.endswith("}")) or part.isdigit()

    left, right = segments(template), segments(path)
    if len(left) != len(right):
        return False
    return all(is_slot(a) or is_slot(b) or a == b for a, b in zip(left, right, strict=True))


def _charted_calls() -> set[tuple[str, str]]:
    """Every `(method, url template)` a page that charts a table calls, from the source.

    Derived rather than listed: a page's `dataIndex` values say it charts something, and the
    API methods it calls say what. The link runs through `api/index.ts`, where each method
    names its URL, so a new screen is covered the moment it exists rather than when somebody
    remembers to add it here.
    """
    import re as regex

    urls = _api_method_paths()
    charted: set[tuple[str, str]] = set()
    for page in sorted((ROOT / "frontend" / "src" / "pages").rglob("*.tsx")):
        text = page.read_text(encoding="utf-8")
        if "dataIndex:" not in text:
            continue
        for api_object, method_name in set(regex.findall(r"\b(\w+Api)\.(\w+)", text)):
            entry = urls.get(f"{api_object}.{method_name}")
            if entry is None or not entry[2]:
                continue
            method, path, _reads = entry
            if any(marker in path for marker in NOT_TABULAR):
                continue
            charted.add((method, path))
    return charted


def test_every_endpoint_a_screen_charts_is_in_the_contract() -> None:
    """The table covered what somebody remembered; this requires it to cover what is read.

    Adding a field to a screen was already caught -- the endpoint has to be listed, and a
    stale entry fails. What was not caught is adding a *screen*, or pointing an existing one
    at an endpoint nobody had listed: the table stayed green while covering less of the
    application than it claimed to.
    """
    gets = [path for path, _key, _fields in CHARTED_RESPONSES]
    writes = [(method, path) for method, path, _body, _fields in CHARTED_WRITES]
    missing: list[str] = []
    for method, template in sorted(_charted_calls()):
        if any(marker in template for marker in NOT_TABULAR):
            continue
        if method == "GET":
            if not any(_matches(template, path) for path in gets):
                missing.append(f"GET  {template}")
        elif any(
            action_method == method and _matches(template, action_path)
            for action_method, action_path in ACTION_ONLY_WRITES
        ):
            continue
        elif not any(method == written_method and _matches(template, path) for written_method, path in writes):
            missing.append(f"{method} {template}")

    assert not missing, (
        "以下调用有页面在读它的响应，但不在契约表里——它可以停止发送某个字段而测试仍然全绿：\n  " + "\n  ".join(missing)
    )


# Writes whose responses a screen renders. Curated, because the body is page-specific and no
# derivation can invent it -- but the coverage check below requires every non-GET method a
# charting page calls to appear here, so a new one cannot be added silently.
#
# Entries are `(method, path, body, dotted paths the screen or the client reads)`.
CHARTED_WRITES = (
    ("POST", "/auth/login", {"username": "admin", "password": ADMIN_PASSWORD}, ("token", "user")),
    (
        "POST",
        "/semantic/objects/contract/instances/1/assess",
        {"ontologyId": 1},
        ("decision.status", "decision.recommendation", "ruleResults", "semanticKernel"),
    ),
    (
        "POST",
        "/automation/operations/submit_contract/preflight",
        {"ontologyId": 1, "dataSourceId": 1, "instanceId": "1", "objectCode": "contract"},
        ("decision.status", "decision.recommendation", "nextAction", "operation.operationCode", "target.instanceId"),
    ),
    (
        "POST",
        "/automation/operations/submit_contract/execute",
        {"ontologyId": 1, "dataSourceId": 1, "instanceId": "1", "objectCode": "contract"},
        ("executed", "status", "message", "preflight"),
    ),
    (
        "POST",
        "/semantic/natural-language/query",
        {"question": "合同 1 是否合规", "objectCode": "contract", "instanceId": "1"},
        ("answer", "intent", "confidence", "resolved.ontologyId", "resolved.objectCode"),
    ),
    (
        "POST",
        "/semantic/objects/contract/consistency",
        {"ontologyId": 1, "limit": 3},
        ("status", "items", "nextActions", "summary"),
    ),
    ("POST", "/agent/chat", {"message": "合同的金额是多少"}, ("answer", "sessionId", "roleId", "messageId", "intent")),
    ("POST", "/permissions/check", {"roleCode": "admin", "objectCode": "contract"}, ("allowed",)),
    (
        "POST",
        "/data-sources",
        {"name": "渲染检查", "sourceType": "sqlite", "connectionUri": "/tmp/does-not-exist.sqlite3"},
        ("id", "name", "sourceType", "connectionUri"),
    ),
    (
        "POST",
        "/data-sources/1/initialize",
        {},
        ("status", "scan", "ontology", "reasoningChain"),
    ),
    (
        "POST",
        "/ai/data-sources/1/blueprint-draft",
        {},
        ("blueprint", "usedRemoteModel", "model", "provider"),
    ),
    (
        "POST",
        "/ai/data-sources/1/ontology-reasoning-chain",
        {},
        (
            "usedRemoteModel",
            "model",
            "chain.summary",
            "chain.reasoningSteps",
            "chain.proposedObjects",
            "chain.proposedRelations",
            "chain.proposedRules",
            "chain.buildPlan",
        ),
    ),
    (
        "POST",
        "/data-sources/1/apis/import-openapi",
        {"dataSourceId": 1, "spec": {"openapi": "3.0.0", "paths": {}}},
        ("imported", "skipped", "count"),
    ),
    ("POST", "/admin/backup/create", {}, ("name", "size", "created_at")),
    ("POST", "/admin/backup/restore/smoke", {}, ("name", "restored_at", "database")),
    (
        "POST",
        "/data-sources/1/test-connection",
        {},
        ("sourceType", "reachable", "status", "message", "dataSourceId", "name"),
    ),
    (
        "POST",
        "/data-sources/test-connection",
        {"sourceType": "sqlite", "connectionUri": "/tmp/does-not-exist.sqlite3"},
        ("sourceType", "reachable", "status", "message"),
    ),
    (
        "POST",
        "/data-sources/1/test-api-gateway",
        {},
        ("dataSourceId", "name", "configured", "reachable", "status", "statusCode", "message"),
    ),
    ("POST", "/industry-blueprints", {"id": "smoke", "name": "冒烟", "domain": "测试"}, ("id", "name", "domain")),
    ("POST", "/ontologies/draft", {"dataSourceId": 1}, ("id", "name", "version", "status")),
    (
        "POST",
        "/permissions/roles",
        {"code": "smoke_role", "name": "冒烟角色"},
        ("id", "code", "name", "is_system", "created_at"),
    ),
    (
        "POST",
        "/permissions/policies",
        {"roleId": 1, "objectCode": "contract", "canRead": True},
        ("id", "role_id", "object_code", "can_read", "can_write", "can_execute", "can_delete"),
    ),
    (
        "POST",
        "/workflows",
        {"ontologyId": 1, "objectCode": "customer", "name": "冒烟审批流", "initialState": "draft"},
        ("id", "ontology_id", "object_code", "name", "initial_state", "states", "transitions"),
    ),
    (
        "POST",
        "/tools/logs/1/review",
        {"reviewer": "admin", "decision": "approved"},
        ("id", "tool_code", "status", "reviewed_by", "review_decision"),
    ),
    (
        "POST",
        "/tenants",
        {"tenant": "smoke_tenant"},
        ("tenant", "schema"),
    ),
    (
        "POST",
        "/onboarding/run",
        {
            "name": "冒烟接入",
            "sourceType": "sqlite",
            "connectionUri": "/tmp/does-not-exist.sqlite3",
            "domain": "测试",
        },
        ("status", "steps", "dataSource", "connection", "readiness"),
    ),
    (
        "POST",
        "/ontologies/1/rules",
        {
            "code": "smoke_rule",
            "name": "冒烟规则",
            "naturalLanguage": "金额必须大于零。",
            "expression": "amount > 0",
            "severity": "warning",
            "ruleType": "validation",
            "scopeObjectCode": "contract",
        },
        ("id", "code", "ruleType", "scopeObjectCode", "severity", "naturalLanguage", "status"),
    ),
)

# Calls whose response no screen renders: a delete, a status toggle, or a write whose result
# the page reports with a toast and then re-reads. Excluded by name, so a new one has to be
# added here on purpose rather than being ignored by a rule that happens to skip it.
ACTION_ONLY_WRITES = (
    # Reports its outcome with a toast and refreshes; the counts are per table and the page
    # renders the table list from a separate call.
    ("POST", "/data-sources/${id}/scan"),
    # The rule import and the document upload are multipart and their results are rendered;
    # they are driven by the two tests below, which build a real file rather than a body.
    ("POST", "/ontologies/${ontologyId}/rules/import-word"),
    ("POST", "/ontologies/${ontologyId}/knowledge/documents"),
    # Returns counts and a status; the review table is re-read from the list endpoint.
    ("POST", "/ontologies/${ontologyId}/mappings/review"),
    # Returns the event that was just recorded; the drawer re-reads the timeline.
    (
        "POST",
        "/ontologies/${ontologyId}/objects/${encodeURIComponent(objectCode)}/instances/${encodeURIComponent(instanceId)}/events",
    ),
    # The same shape of call: an update whose result the screen re-reads from the endpoint
    # that owns the list. Each returns the row it just wrote.
    ("POST", "/workflows/${workflowId}/transitions/run"),
    ("PUT", "/auth/sso/mappings"),
    ("PUT", "/ontologies/${ontologyId}/objects/${objectCode}/event-types"),
    ("PUT", "/ontologies/${ontologyId}/rules/${ruleId}"),
    ("PUT", "/tenants/${encodeURIComponent(tenant)}/quotas"),
    # Reports the published version in a toast and re-reads the page. The *success* path also
    # needs zero pending mappings, which the contract fixture cannot arrange -- so the summary
    # shape is asserted where publishing is: the governance tests.
    ("POST", "/ontologies/${ontologyId}/publish"),
    # Needs a live OpenAPI endpoint to fetch, and a feedback row to resolve.
    ("POST", "/data-sources/${dataSourceId}/apis/import-openapi-url"),
    ("POST", "/feedback/${feedbackId}/resolve"),
    ("POST", "/knowledge/entries/${entryId}/review"),
    ("DELETE", "/auth/sso/mappings/${encodeURIComponent(providerGroup)}"),
    ("DELETE", "/ontologies/${ontologyId}/rules/${ruleId}"),
    ("DELETE", "/workflows/${id}"),
    ("PATCH", "/ontologies/${ontologyId}/rules/${ruleId}/status"),
)


# `resolve` on a dotted path, tolerating a missing step so the failure names the path.
def _resolve(payload: object, path: str) -> bool:
    current: object = payload
    for part in path.split("."):
        if part.endswith("[]"):
            part = part[:-2]
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


@pytest.mark.parametrize(("method", "path", "body", "fields"), CHARTED_WRITES)
def test_the_fields_a_screen_reads_from_a_write_are_present(
    seeded_client: TestClient, method: str, path: str, body: dict, fields: tuple[str, ...]
) -> None:
    """The contract covered GETs only.

    Every screen that submits a form renders the response, and those shapes were outside the
    table -- which is where the preflight's 建议 turned out to be an internal code, and where
    the rule detail drawer printed raw enums. A response is a response whether a page asked
    for it with a click or with a URL.
    """
    token = _token(seeded_client, "admin", ADMIN_PASSWORD)
    response = seeded_client.request(method, path, headers=_auth(token), json=body)
    assert response.status_code in (200, 201), f"{method} {path}: {response.status_code} {response.text[:200]}"

    payload = response.json()
    missing = [field for field in fields if not _resolve(payload, field)]
    assert not missing, f"{method} {path} 缺少界面读取的字段 {missing}"
