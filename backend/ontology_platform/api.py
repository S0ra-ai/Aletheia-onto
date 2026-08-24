from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from .access_policy import (
    VERSION_PREFIXES,
    is_public,
    required_capability,
)
from .agent import agent_chat, get_agent_roles
from .agent_roles import delete_agent_role, init_agent_role_schema, upsert_agent_role
from .aggregation import (
    init_aggregate_schema,
)
from .auth import (
    AuthenticationError,
    AuthorizationError,
    Principal,
    authorize,
    ensure_bootstrap_admin,
    init_auth_schema,
    purge_expired_sessions,
    resolve_principal,
)
from .automation import execute_operation, preflight_operation
from .context import resolve_context
from .contract_documents import parse_rule_docx_bytes
from .conversations import (
    init_conversation_schema,
)
from .credentials import redact_connection_uri
from .database import DEFAULT_PLATFORM_DB, configure_platform_db, connect, get_platform_config, initialize_platform_db
from .entity_resolution import (
    init_entity_resolution_schema,
)
from .events import (
    init_event_schema,
)
from .governance import (
    bulk_review_semantic_mappings,
    delete_business_rule,
    derive_ontology_version,
    get_business_rule,
    list_business_rules,
    list_semantic_mappings,
    publish_ontology,
    review_semantic_mapping,
    toggle_business_rule_status,
    update_business_rule,
    upsert_business_rule,
)
from .graph_view import build_ontology_graph
from .http_runtime import AUTH_ENABLED, DEV_ADMIN_PRINCIPAL, bearer_token, current_principal
from .industry_blueprints import list_industry_blueprints, upsert_industry_blueprint
from .knowledge_documents import (
    init_knowledge_schema,
)
from .metadata import (
    register_data_source,
    register_source_api,
    scan_data_source,
)
from .natural_language import query_natural_language
from .ontology import (
    explain_instance,
    export_ontology_asset,
    generate_ontology_draft,
    list_ontologies,
    resolve_ontology_for_object,
    summarize_ontology,
)
from .release_readiness import assess_ontology_release_readiness
from .routers import (
    auth_router,
    data_source_router,
    knowledge_router,
    metamodel_router,
    model_governance_router,
    workflow_permission_router,
)
from .sample_data import (
    DEFAULT_EQUIPMENT_SAMPLE_DB,
    DEFAULT_SAMPLE_DB,
    create_contract_sample_db,
    create_equipment_sample_db,
)
from .semantic_kernel import (
    assess_decision_consistency,
    assess_instance,
    available_rule_names,
    validate_rule_expression,
)
from .temporal import (
    TemporalError,
    init_temporal_schema,
)
from .tenancy import (
    TenantError,
    list_tenants,
    provision_tenant,
    tenant_context,
    tenant_statistics,
)
from .vocabulary import default_object_code_for_ontology
from .workbench import build_workbench
from .workflow_permission import (
    init_workflow_and_permission_schema,
    seed_default_roles_and_policies,
    seed_default_tools,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform_db_type = os.environ.get("ONTOLOGY_PLATFORM_DB_TYPE", "sqlite").lower()
    platform_db_uri = os.environ.get("ONTOLOGY_PLATFORM_DB_URI", "")
    if platform_db_type != "sqlite":
        configure_platform_db(platform_db_type, platform_db_uri)
        initialize_platform_db()
    else:
        initialize_platform_db(DEFAULT_PLATFORM_DB)
    # Schema creation must not be silently swallowed: a missing table turns
    # into a confusing 500 on first use instead of a clear startup failure.
    with connect(DEFAULT_PLATFORM_DB) as conn:
        init_workflow_and_permission_schema(conn)
        init_auth_schema(conn)
        init_agent_role_schema(conn)
        init_knowledge_schema(conn)
        init_aggregate_schema(conn)
        init_event_schema(conn)
        init_temporal_schema(conn)
        init_entity_resolution_schema(conn)
        init_conversation_schema(conn)
    seed_default_tools(DEFAULT_PLATFORM_DB)
    seed_default_roles_and_policies(DEFAULT_PLATFORM_DB)
    if AUTH_ENABLED:
        ensure_bootstrap_admin(DEFAULT_PLATFORM_DB)
        purged = purge_expired_sessions(DEFAULT_PLATFORM_DB)
        if purged:
            logger.info("已清理 %s 个过期会话", purged)
    else:
        logger.warning("认证已通过 ONTOLOGY_AUTH_DISABLED=1 关闭，所有接口可匿名访问。仅限本地开发使用。")
    yield


logger = logging.getLogger(__name__)

app = FastAPI(title="本体改造研发平台", version="0.2.0", lifespan=lifespan)

# The version this build serves under a prefix. Taken from access_policy so the router
# and the authorization matcher can never disagree about which prefix exists -- a
# mismatch would mean a served route with no policy entry.
VERSION_PREFIX = VERSION_PREFIXES[0]

_allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "ONTOLOGY_ALLOWED_ORIGINS",
        "http://127.0.0.1:3000,http://localhost:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def include_router_twice(application: FastAPI, router: APIRouter) -> None:
    """Serve a router's routes bare and under `/v1`.

    Without a version prefix there is nowhere to put a breaking change: the first
    external caller freezes the current shape permanently. Serving both means existing
    callers -- including this repo's own frontend -- keep working while new ones pin
    `/v1`.

    Two `include_router` calls rather than mounting a sub-application, because a
    sub-application does not inherit the parent's middleware, and the middleware is what
    authenticates and authorizes every request. A `/v1` tree without it would be an
    unauthenticated copy of the whole API.

    This replaced a version that reflected over `application.routes` after all routes
    were declared, copying each one to a prefixed path. That worked only while every
    route was registered directly on the app: FastAPI 0.141 makes `include_router`
    lazy, storing a placeholder that expands at startup, so the reflection saw
    routers as a single opaque object and silently produced no `/v1` copies of them.
    Silently is the problem -- the bare routes still worked, so nothing failed until a
    versioned caller got a 404. Declaring both up front cannot drift that way.

    `include_in_schema=False` on the prefixed copy keeps OpenAPI showing each operation
    once, so generated clients do not get two of everything.
    """
    application.include_router(router)
    application.include_router(router, prefix=VERSION_PREFIX, include_in_schema=False)


# Routes still declared in this module. They go on a router rather than on `app`
# directly so that every route -- these and the extracted ones -- reaches `/v1` by the
# same mechanism. A mix of both would mean two ways for a route to be versioned, and
# only one of them tested.
core_router = APIRouter()


@app.middleware("http")
async def enforce_access_policy(request: Request, call_next):
    """Authenticate every request and check the route's capability.

    Doing this in one middleware, driven by access_policy, means a newly added
    endpoint is protected by default rather than by remembering to annotate it.
    """
    if request.method == "OPTIONS" or is_public(request.url.path):
        return await call_next(request)

    if not AUTH_ENABLED:
        request.state.principal = DEV_ADMIN_PRINCIPAL
        return await call_next(request)

    try:
        principal = resolve_principal(DEFAULT_PLATFORM_DB, bearer_token(request))
    except AuthenticationError as error:
        return JSONResponse(
            status_code=401,
            content={"detail": str(error), "code": "unauthenticated"},
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as error:  # pragma: no cover - unexpected auth backend failure
        logger.exception("鉴权失败: %s", error)
        return JSONResponse(status_code=500, content={"detail": "鉴权服务异常", "code": "auth_error"})

    capability = required_capability(request.method, request.url.path)
    try:
        authorize(principal, capability)
    except AuthorizationError as error:
        return JSONResponse(
            status_code=403,
            content={
                "detail": str(error),
                "code": "forbidden",
                "requiredCapability": capability,
                "roleCode": principal.role_code,
            },
        )

    request.state.principal = principal
    return await call_next(request)


class OntologyDraftCreate(BaseModel):
    dataSourceId: int
    name: Optional[str] = None
    domain: Optional[str] = None
    blueprintId: Optional[str] = None


class IndustryBlueprintUpsert(BaseModel):
    id: str
    name: str
    domain: str
    description: str = ""
    objectHints: dict[str, str] = Field(default_factory=dict)
    attributeHints: dict[str, str] = Field(default_factory=dict)
    rules: list[dict[str, object]] = Field(default_factory=list)
    tableKeywords: list[str] = Field(default_factory=list)
    capabilityTags: list[str] = Field(default_factory=list)


class OperationPreflightCreate(BaseModel):
    ontologyId: int
    dataSourceId: int
    instanceId: str
    objectCode: Optional[str] = None


class DecisionConsistencyCreate(BaseModel):
    ontologyId: int
    instanceIds: list[str] = Field(default_factory=list)
    limit: int = 50


class RuleExpressionValidateCreate(BaseModel):
    expression: str
    scopeObjectCode: Optional[str] = None


class NaturalLanguageQueryCreate(BaseModel):
    question: str
    ontologyId: Optional[int] = None
    dataSourceId: Optional[int] = None
    objectCode: Optional[str] = None
    instanceId: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    useModel: bool = True


class OperationExecuteCreate(OperationPreflightCreate):
    payload: dict[str, object] = Field(default_factory=dict)
    dryRun: bool = True
    timeoutSeconds: float = 10


class AgentChatCreate(BaseModel):
    message: str
    # Unset means "let the platform pick a role from the onboarded domains".
    roleId: Optional[str] = None
    dataSourceId: Optional[int] = None
    objectCode: Optional[str] = None
    history: list[dict[str, str]] = Field(default_factory=list)
    sessionId: Optional[str] = None


class MappingReviewCreate(BaseModel):
    status: str
    note: str = ""


class BulkMappingReviewCreate(BaseModel):
    status: str
    note: str = ""


class OntologyPublishCreate(BaseModel):
    force: bool = False


class OntologyDeriveCreate(BaseModel):
    version: str


class BusinessRuleCreate(BaseModel):
    code: str
    name: str
    ruleType: str
    scopeObjectCode: str
    expression: str
    severity: str
    naturalLanguage: str
    status: str = "published"
    priority: int = 0
    category: str = ""
    effectiveStart: Optional[str] = None
    effectiveEnd: Optional[str] = None
    dependsOn: Optional[str] = None


@core_router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@core_router.post("/demo/bootstrap")
def bootstrap_demo() -> dict[str, object]:
    # ValueError here means a governance rule refused the request -- most often
    # "this ontology version is already published, derive a new one". That is a
    # client-correctable condition, so it must not surface as a 500.
    try:
        initialize_platform_db(DEFAULT_PLATFORM_DB)
        sample_path = create_contract_sample_db(DEFAULT_SAMPLE_DB)
        source = register_data_source(
            DEFAULT_PLATFORM_DB,
            "合同管理样例系统",
            "sqlite",
            str(sample_path),
            domain="合同管理",
            system_category="database+api",
        )
        register_source_api(
            DEFAULT_PLATFORM_DB,
            source.id,
            "submit_contract",
            "提交合同审批",
            "POST",
            "/contracts/{id}/submit",
            "contract.submit_for_approval",
        )
        scan = scan_data_source(DEFAULT_PLATFORM_DB, source.id)
        ontology = generate_ontology_draft(DEFAULT_PLATFORM_DB, source.id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"dataSource": source.public_dict(), "scan": scan, "ontology": ontology}


@core_router.post("/demo/bootstrap/equipment")
def bootstrap_equipment_demo() -> dict[str, object]:
    # Same as /demo/bootstrap: a refused governance rule is a 409, not a 500.
    try:
        initialize_platform_db(DEFAULT_PLATFORM_DB)
        sample_path = create_equipment_sample_db(DEFAULT_EQUIPMENT_SAMPLE_DB)
        source = register_data_source(
            DEFAULT_PLATFORM_DB,
            "设备运维样例系统",
            "sqlite",
            str(sample_path),
            domain="设备运维",
            system_category="database+api",
        )
        register_source_api(
            DEFAULT_PLATFORM_DB,
            source.id,
            "close_work_order",
            "关闭工单",
            "POST",
            "/work-orders/{id}/close",
            "work_order.close",
        )
        scan = scan_data_source(DEFAULT_PLATFORM_DB, source.id)
        ontology = generate_ontology_draft(DEFAULT_PLATFORM_DB, source.id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"dataSource": source.public_dict(), "scan": scan, "ontology": ontology}


@core_router.post("/ontologies/draft")
def create_ontology_draft(payload: OntologyDraftCreate) -> dict[str, object]:
    try:
        return generate_ontology_draft(
            DEFAULT_PLATFORM_DB, payload.dataSourceId, payload.name, payload.domain, payload.blueprintId
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/industry-blueprints")
def get_industry_blueprints() -> dict[str, object]:
    return {"items": list_industry_blueprints(DEFAULT_PLATFORM_DB)}


@core_router.post("/industry-blueprints")
def upsert_blueprint(payload: IndustryBlueprintUpsert) -> dict[str, object]:
    try:
        return upsert_industry_blueprint(DEFAULT_PLATFORM_DB, payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies")
def get_ontologies() -> dict[str, object]:
    items = list_ontologies(DEFAULT_PLATFORM_DB)
    return {"items": items, "ontologies": items}


@core_router.get("/ontologies/{ontology_id}")
def get_ontology(ontology_id: int) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
        try:
            return summarize_ontology(conn, ontology_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/export")
def export_ontology(ontology_id: int, format: str = "jsonld") -> Response:
    try:
        asset = export_ontology_asset(DEFAULT_PLATFORM_DB, ontology_id, format)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(
        content=asset["content"],
        media_type=asset["mediaType"],
        headers={"Content-Disposition": f"attachment; filename={asset['filename']}"},
    )


@core_router.get("/ontologies/{ontology_id}/mappings")
def get_ontology_mappings(ontology_id: int, status: Optional[str] = None) -> dict[str, object]:
    try:
        return list_semantic_mappings(DEFAULT_PLATFORM_DB, ontology_id, status)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/semantic-mappings/{mapping_id}/review")
def review_mapping(
    mapping_id: int,
    payload: MappingReviewCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_semantic_mapping(DEFAULT_PLATFORM_DB, mapping_id, payload.status, principal.actor, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/mappings/review")
def review_ontology_mappings(
    ontology_id: int,
    payload: BulkMappingReviewCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return bulk_review_semantic_mappings(
            DEFAULT_PLATFORM_DB, ontology_id, payload.status, principal.actor, payload.note
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/publish")
def publish_ontology_version(
    ontology_id: int,
    payload: OntologyPublishCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return publish_ontology(DEFAULT_PLATFORM_DB, ontology_id, principal.actor, payload.force)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/release-readiness")
def get_ontology_release_readiness(ontology_id: int) -> dict[str, object]:
    try:
        return assess_ontology_release_readiness(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/derive")
def derive_ontology_draft(
    ontology_id: int,
    payload: OntologyDeriveCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return derive_ontology_version(DEFAULT_PLATFORM_DB, ontology_id, payload.version, principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/rules")
def get_business_rules(ontology_id: int) -> dict[str, object]:
    try:
        return list_business_rules(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/rules")
def create_or_update_business_rule(
    ontology_id: int,
    payload: BusinessRuleCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return upsert_business_rule(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            payload.code,
            payload.name,
            payload.ruleType,
            payload.scopeObjectCode,
            payload.expression,
            payload.severity,
            payload.naturalLanguage,
            principal.actor,
            payload.status,
            payload.priority,
            payload.category,
            payload.effectiveStart,
            payload.effectiveEnd,
            payload.dependsOn,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/rules/import-word")
async def import_business_rules_from_word(
    ontology_id: int,
    file: UploadFile = File(...),
    apply: bool = Form(True),
    defaultScope: str = Form(""),
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    actor = principal.actor
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        # Rules that omit a scope fall back to an object from this ontology,
        # never to a built-in business object code.
        resolved_scope = defaultScope or default_object_code_for_ontology(DEFAULT_PLATFORM_DB, ontology_id)
        parsed = parse_rule_docx_bytes(file.filename, content, default_scope=resolved_scope)
        imported = []
        errors = []
        if apply:
            for rule in parsed["rules"]:
                try:
                    imported.append(
                        upsert_business_rule(
                            DEFAULT_PLATFORM_DB,
                            ontology_id,
                            rule["code"],
                            rule["name"],
                            rule["ruleType"],
                            rule["scopeObjectCode"],
                            rule["expression"],
                            rule["severity"],
                            rule["naturalLanguage"],
                            actor,
                            rule.get("status", "published"),
                            rule.get("priority", 0),
                            rule.get("category", ""),
                            rule.get("effectiveStart"),
                            rule.get("effectiveEnd"),
                            rule.get("dependsOn"),
                        )
                    )
                except ValueError as error:
                    errors.append({"code": rule["code"], "error": str(error)})
        return {
            "ontologyId": ontology_id,
            "file": parsed["file"],
            "rules": parsed["rules"],
            "warnings": parsed["warnings"],
            "applied": apply,
            "imported": imported,
            "errors": errors,
            "importedCount": len(imported),
            "errorCount": len(errors),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/rules/validate-expression")
def validate_ontology_rule_expression(ontology_id: int, payload: RuleExpressionValidateCreate) -> dict[str, object]:
    """Statically check a rule expression before it is saved."""
    available: Optional[list[str]] = None
    if payload.scopeObjectCode:
        available = available_rule_names(DEFAULT_PLATFORM_DB, ontology_id, payload.scopeObjectCode)
    return validate_rule_expression(payload.expression, available)


@core_router.get("/ontologies/{ontology_id}/rules/{rule_id}")
def get_ontology_rule(ontology_id: int, rule_id: int) -> dict[str, object]:
    try:
        return get_business_rule(DEFAULT_PLATFORM_DB, ontology_id, rule_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.put("/ontologies/{ontology_id}/rules/{rule_id}")
def update_ontology_rule(
    ontology_id: int,
    rule_id: int,
    payload: BusinessRuleCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return update_business_rule(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            rule_id,
            payload.code,
            payload.name,
            payload.ruleType,
            payload.scopeObjectCode,
            payload.expression,
            payload.severity,
            payload.naturalLanguage,
            principal.actor,
            payload.status,
            payload.priority,
            payload.category,
            payload.effectiveStart,
            payload.effectiveEnd,
            payload.dependsOn,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.delete("/ontologies/{ontology_id}/rules/{rule_id}")
def delete_ontology_rule(ontology_id: int, rule_id: int) -> dict[str, object]:
    try:
        return delete_business_rule(DEFAULT_PLATFORM_DB, ontology_id, rule_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.patch("/ontologies/{ontology_id}/rules/{rule_id}/status")
def toggle_ontology_rule_status(ontology_id: int, rule_id: int, status: str = "published") -> dict[str, object]:
    try:
        return toggle_business_rule_status(DEFAULT_PLATFORM_DB, ontology_id, rule_id, status)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/semantic/objects/{object_code}/instances/{instance_id}/explain")
def explain_object_instance(object_code: str, instance_id: str, ontologyId: Optional[int] = None) -> dict[str, object]:
    try:
        resolved = (
            ontologyId if ontologyId is not None else resolve_ontology_for_object(DEFAULT_PLATFORM_DB, object_code)
        )
        return explain_instance(DEFAULT_PLATFORM_DB, resolved, object_code, instance_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/semantic/objects/{object_code}/instances/{instance_id}/assess")
def assess_object_instance(
    object_code: str,
    instance_id: str,
    ontologyId: Optional[int] = None,
    asOf: str = "",
) -> dict[str, object]:
    """Assess one instance, optionally as of a past moment.

    `asOf` is what a compliance audit actually asks: was the January approval correct given
    what was known in January. Assessing against today's values answers a different
    question, so the moment is echoed in the response and stored with the decision.
    """
    try:
        resolved = (
            ontologyId if ontologyId is not None else resolve_ontology_for_object(DEFAULT_PLATFORM_DB, object_code)
        )
        return assess_instance(DEFAULT_PLATFORM_DB, resolved, object_code, instance_id, as_of=asOf or None)
    except TemporalError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/semantic/objects/{object_code}/consistency")
def assess_object_decision_consistency(object_code: str, payload: DecisionConsistencyCreate) -> dict[str, object]:
    try:
        return assess_decision_consistency(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            object_code,
            payload.instanceIds,
            payload.limit,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/semantic/natural-language/query")
def ask_semantic_kernel(
    payload: NaturalLanguageQueryCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Answer a question, filtering citations by what the caller may read.

    The role comes from the authenticated identity, never from the request body: a caller
    who could name their own role would grant themselves any document.
    """
    try:
        return query_natural_language(
            DEFAULT_PLATFORM_DB,
            payload.question,
            payload.ontologyId,
            payload.dataSourceId,
            payload.objectCode,
            payload.instanceId,
            payload.history,
            payload.useModel,
            role_code=principal.role_code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/agent/roles")
def list_agent_roles() -> dict[str, object]:
    return {"roles": get_agent_roles(DEFAULT_PLATFORM_DB)}


class AgentRoleUpsert(BaseModel):
    code: str
    name: str
    description: str = ""
    domain: str = ""
    systemPrompt: str = ""
    dataSourceId: Optional[int] = None


@core_router.post("/agent/roles")
def create_or_update_agent_role(
    payload: AgentRoleUpsert,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Persist a custom agent role for domains needing bespoke wording."""
    try:
        return upsert_agent_role(
            DEFAULT_PLATFORM_DB,
            payload.code,
            payload.name,
            payload.description,
            payload.domain,
            payload.systemPrompt,
            payload.dataSourceId,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.delete("/agent/roles/{code}")
def remove_agent_role(code: str, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return delete_agent_role(DEFAULT_PLATFORM_DB, code, actor=principal.actor)


@core_router.post("/agent/chat")
def chat_with_agent(
    payload: AgentChatCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return agent_chat(
            DEFAULT_PLATFORM_DB,
            payload.message,
            payload.roleId,
            payload.dataSourceId,
            payload.objectCode,
            # None lets the stored history load; an explicit list still wins, so a
            # caller managing its own context is unaffected.
            payload.history or None,
            payload.sessionId,
            actor=principal.actor,
            # Citations are filtered by what this caller may read. Taken from the
            # authenticated identity, never from the payload's `roleId` -- that names an
            # agent persona, which is not an authorisation.
            role_code=principal.role_code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/automation/operations/{operation_code}/preflight")
def preflight_business_operation(operation_code: str, payload: OperationPreflightCreate) -> dict[str, object]:
    try:
        return preflight_operation(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            payload.dataSourceId,
            operation_code,
            payload.instanceId,
            payload.objectCode,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/automation/operations/{operation_code}/execute")
def execute_business_operation(
    operation_code: str,
    payload: OperationExecuteCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return execute_operation(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            payload.dataSourceId,
            operation_code,
            payload.instanceId,
            payload.objectCode,
            payload.payload,
            principal.actor,
            payload.dryRun,
            payload.timeoutSeconds,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class TenantCreate(BaseModel):
    tenant: str


def _tenant_base_context() -> Any:
    """The context tenants are provisioned from.

    Uses the process default, so provisioning targets whatever platform database
    the deployment is configured with rather than a hardcoded path.
    """
    return resolve_context(DEFAULT_PLATFORM_DB)


@core_router.get("/tenants")
def tenants() -> dict[str, object]:
    """Provisioned tenants.

    Multi-tenancy is opt-in: a single-tenant deployment provisions nothing and this
    returns an empty list, which is not an error.
    """
    base = _tenant_base_context()
    return {
        "items": list_tenants(base),
        "isolationModel": "separate-schema-plus-tenant-id",
        "dbType": base.db_type,
    }


@core_router.post("/tenants")
def create_tenant(
    payload: TenantCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Provision a tenant: create its schema and base tables.

    Idempotent, so it is safe to call on every deployment.
    """
    try:
        result = provision_tenant(_tenant_base_context(), payload.tenant)
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with connect(DEFAULT_PLATFORM_DB) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                principal.actor,
                "provision_tenant",
                "tenant",
                result["tenant"],
                json.dumps({"schema": result["schema"]}, ensure_ascii=False),
            ),
        )
    return result


@core_router.get("/tenants/{tenant}/statistics")
def tenant_stats(tenant: str) -> dict[str, object]:
    """Row counts for one tenant, for verifying isolation after provisioning."""
    try:
        return tenant_statistics(tenant_context(_tenant_base_context(), tenant))
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/workbench")
def workbench(decisionLimit: int = 8) -> dict[str, object]:
    """Aggregated platform state for the workbench screen.

    Read-only projection over existing tables, so it cannot disagree with the
    screens it summarises.
    """
    return build_workbench(DEFAULT_PLATFORM_DB, decisionLimit)


@core_router.get("/ontologies/{ontology_id}/graph")
def ontology_graph(ontology_id: int) -> dict[str, object]:
    """Nodes and edges for the knowledge graph preview."""
    try:
        return build_ontology_graph(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/files")
def files() -> dict[str, str]:
    config = get_platform_config()
    return {
        "platformDbType": config.db_type,
        "platformDb": redact_connection_uri(config.connection_uri) or str(Path(DEFAULT_PLATFORM_DB).resolve()),
        "sampleDb": str(Path(DEFAULT_SAMPLE_DB).resolve()),
    }


# Every router the app serves. Declared as data because it is what the version mounting
# below iterates *and* what the tests enumerate: FastAPI 0.141 expands `include_router`
# lazily, so `app.routes` holds placeholders rather than routes, and there is no
# public way to walk them. Reaching into `_IncludedRouter` would tie the authorization
# tests to a private structure that already changed once.
ROUTERS: tuple[APIRouter, ...] = (
    core_router,
    auth_router,
    data_source_router,
    knowledge_router,
    metamodel_router,
    model_governance_router,
    workflow_permission_router,
)


def declared_routes() -> list[APIRoute]:
    """Every route this app serves, bare form only.

    The one supported way to ask "what does this API expose". Used by the tests that
    assert each route's `/v1` copy requires the same capability -- a check that has to
    enumerate routes to mean anything, and would otherwise depend on FastAPI internals.
    """
    return [route for router in ROUTERS for route in router.routes if isinstance(route, APIRoute)]


# Each router served bare and under `/v1`. Forgetting one means its routes are not
# served at all, which fails on the first request rather than only for versioned callers.
for _router in ROUTERS:
    include_router_twice(app, _router)
