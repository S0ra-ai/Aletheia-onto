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
    PUBLIC_PATHS,
    VERSION_PREFIXES,
    describe_policy,
    is_public,
    required_capability,
)
from .adapters import supported_source_types
from .agent import agent_chat, get_agent_roles
from .agent_roles import delete_agent_role, init_agent_role_schema, upsert_agent_role
from .aggregation import (
    AggregateSpec,
    AggregationError,
    define_aggregate,
    init_aggregate_schema,
    list_aggregates,
)
from .auth import (
    ROLE_CAPABILITIES,
    AuthenticationError,
    AuthorizationError,
    Principal,
    authorize,
    change_password,
    create_user,
    ensure_bootstrap_admin,
    init_auth_schema,
    list_users,
    login,
    logout,
    purge_expired_sessions,
    resolve_principal,
    set_user_status,
)
from .automation import execute_operation, preflight_operation, supported_executor_schemes
from .context import resolve_context
from .contract_documents import parse_rule_docx_bytes
from .conversations import (
    escalate_conversation,
    feedback_summary,
    get_conversation,
    init_conversation_schema,
    list_conversations,
    list_feedback,
    resolve_feedback,
    set_conversation_status,
    submit_feedback,
)
from .coverage import build_semantic_coverage
from .credentials import redact_connection_uri
from .database import DEFAULT_PLATFORM_DB, configure_platform_db, connect, get_platform_config, initialize_platform_db
from .db_executors import registered_database_targets
from .decisions import list_decisions
from .derived_attributes import (
    DerivedAttributeError,
    DerivedSpec,
    UnitError,
    define_derived_attribute,
    known_units,
    list_derived_attributes,
    set_attribute_unit,
)
from .entity_resolution import (
    CrossSourceLink,
    EntityResolutionError,
    MatchKey,
    declare_cross_source_link,
    describe_cross_source,
    init_entity_resolution_schema,
)
from .events import (
    MAX_EVENT_HISTORY,
    EventError,
    EventType,
    declare_event_type,
    init_event_schema,
    instance_timeline,
    list_event_types,
    record_event,
)
from .generic_sql_adapter import describe_bundled_sql_sources, register_bundled_sql_sources
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
from .http_runtime import AUTH_ENABLED, DEV_ADMIN_PRINCIPAL, current_principal
from .industry_blueprints import list_industry_blueprints, upsert_industry_blueprint
from .instance_resolver import (
    ResolverError,
    ResolverSpec,
    configure_object_resolver,
    get_object_resolver,
    supported_resolver_kinds,
)
from .kernel_package import build_kernel_package, export_kernel_package
from .knowledge_base import browse_source_table, build_reasoning_chain, initialize_knowledge_base, list_knowledge_bases
from .knowledge_documents import (
    extract_text_from_docx,
    ingest_document,
    init_knowledge_schema,
    list_documents,
    list_entries,
    review_knowledge_entry,
)
from .metadata import (
    analyze_schema_drift,
    assess_data_source_readiness,
    check_business_api_gateway,
    check_data_source_connection,
    import_openapi_operations,
    import_openapi_operations_from_url,
    list_data_sources,
    list_source_apis,
    register_data_source,
    register_source_api,
    scan_data_source,
)
from .model_client import (
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
from .natural_language import query_natural_language
from .onboarding import run_onboarding_pipeline
from .ontology import (
    explain_instance,
    export_ontology_asset,
    generate_ontology_draft,
    list_ontologies,
    resolve_ontology_for_object,
    summarize_ontology,
)
from .operation_bindings import assess_operation_bindings
from .release_readiness import assess_ontology_release_readiness
from .retrieval import supported_embedding_models, supported_retrieval_backends
from .routers import workflow_permission_router
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
from .sql_dialects import known_dialects
from .temporal import (
    TemporalError,
    init_temporal_schema,
    instance_history,
    record_attribute_version,
)
from .tenancy import (
    TenantError,
    list_tenants,
    provision_tenant,
    tenant_context,
    tenant_statistics,
)
from .type_hierarchy import HierarchyError, declare_subtype, describe_hierarchy
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


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


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
        principal = resolve_principal(DEFAULT_PLATFORM_DB, _bearer_token(request))
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


class DataSourceCreate(BaseModel):
    name: str
    sourceType: str = "sqlite"
    connectionUri: str
    apiBaseUrl: str = ""
    apiHeaders: dict[str, str] = Field(default_factory=dict)
    domain: str = ""
    systemCategory: str = "database"
    capabilities: list[str] = Field(default_factory=lambda: ["metadata_scan", "semantic_mapping"])


class DataSourceConnectionTest(BaseModel):
    sourceType: str
    connectionUri: str


class OnboardingRunCreate(DataSourceCreate):
    blueprintId: Optional[str] = None
    ontologyName: Optional[str] = None
    generateOntology: bool = True
    openApiUrl: str = ""
    openApiSpec: Optional[dict[str, object]] = None


class ModelConfigUpdate(BaseModel):
    apiKey: Optional[str] = None
    model: Optional[str] = None
    baseUrl: Optional[str] = None
    httpReferer: Optional[str] = None
    appTitle: Optional[str] = None
    serviceTier: Optional[str] = None
    timeoutSeconds: Optional[float] = None


class SourceApiCreate(BaseModel):
    operationCode: str
    name: str
    method: str
    path: str
    semanticAction: str = ""
    requestSchema: dict[str, object] = Field(default_factory=dict)
    responseSchema: dict[str, object] = Field(default_factory=dict)


class OpenApiImportCreate(BaseModel):
    spec: dict[str, object]


class OpenApiUrlImportCreate(BaseModel):
    url: str
    timeoutSeconds: float = 10


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


# ============================================================
# Authentication
# ============================================================


class LoginCreate(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    roleCode: str = "analyst"
    displayName: str = ""


class UserStatusUpdate(BaseModel):
    status: str


class PasswordChange(BaseModel):
    currentPassword: str
    newPassword: str


@core_router.post("/auth/login")
def auth_login(payload: LoginCreate) -> dict[str, object]:
    try:
        return login(DEFAULT_PLATFORM_DB, payload.username, payload.password)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/auth/logout")
def auth_logout(request: Request) -> dict[str, object]:
    return logout(DEFAULT_PLATFORM_DB, _bearer_token(request))


@core_router.get("/auth/me")
def auth_me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return principal.public_dict()


@core_router.post("/auth/change-password")
def auth_change_password(
    payload: PasswordChange,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return change_password(DEFAULT_PLATFORM_DB, principal.username, payload.currentPassword, payload.newPassword)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/auth/users")
def auth_list_users() -> dict[str, object]:
    return {"items": list_users(DEFAULT_PLATFORM_DB), "roles": sorted(ROLE_CAPABILITIES)}


@core_router.post("/auth/users")
def auth_create_user(
    payload: UserCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return create_user(
            DEFAULT_PLATFORM_DB,
            payload.username,
            payload.password,
            payload.roleCode,
            payload.displayName,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.patch("/auth/users/{username}/status")
def auth_set_user_status(
    username: str,
    payload: UserStatusUpdate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return set_user_status(DEFAULT_PLATFORM_DB, username, payload.status, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/auth/access-policy")
def auth_access_policy() -> dict[str, object]:
    """Effective route-to-capability policy, for review."""
    return {
        "authEnabled": AUTH_ENABLED,
        "roles": {role: sorted(caps) for role, caps in ROLE_CAPABILITIES.items()},
        "rules": describe_policy(),
        "publicPaths": sorted(PUBLIC_PATHS),
    }


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


@core_router.post("/data-sources")
def create_data_source(payload: DataSourceCreate) -> dict[str, object]:
    try:
        source = register_data_source(
            DEFAULT_PLATFORM_DB,
            payload.name,
            payload.sourceType,
            payload.connectionUri,
            payload.domain,
            payload.systemCategory,
            payload.capabilities,
            payload.apiBaseUrl,
            payload.apiHeaders,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return source.public_dict()


@core_router.post("/onboarding/run")
def run_onboarding(payload: OnboardingRunCreate) -> dict[str, object]:
    try:
        return run_onboarding_pipeline(
            DEFAULT_PLATFORM_DB,
            payload.name,
            payload.sourceType,
            payload.connectionUri,
            payload.domain,
            payload.systemCategory,
            payload.capabilities,
            payload.apiBaseUrl,
            payload.apiHeaders,
            payload.blueprintId,
            payload.ontologyName,
            payload.generateOntology,
            payload.openApiUrl,
            payload.openApiSpec,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/data-sources")
def get_data_sources() -> dict[str, object]:
    items = list_data_sources(DEFAULT_PLATFORM_DB)
    return {"dataSources": items, "data_sources": items}


@core_router.post("/data-sources/test-connection")
def test_unregistered_data_source(payload: DataSourceConnectionTest) -> dict[str, object]:
    try:
        return check_data_source_connection(
            DEFAULT_PLATFORM_DB,
            source_type=payload.sourceType,
            connection_uri=payload.connectionUri,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/data-sources/{data_source_id}/test-connection")
def test_registered_data_source(data_source_id: int) -> dict[str, object]:
    try:
        return check_data_source_connection(DEFAULT_PLATFORM_DB, data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/data-sources/{data_source_id}/test-api-gateway")
def test_registered_api_gateway(data_source_id: int) -> dict[str, object]:
    try:
        return check_business_api_gateway(DEFAULT_PLATFORM_DB, data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/data-sources/{data_source_id}/apis")
def create_source_api(data_source_id: int, payload: SourceApiCreate) -> dict[str, object]:
    try:
        source_api = register_source_api(
            DEFAULT_PLATFORM_DB,
            data_source_id,
            payload.operationCode,
            payload.name,
            payload.method,
            payload.path,
            payload.semanticAction,
            payload.requestSchema,
            payload.responseSchema,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return source_api.__dict__


@core_router.get("/data-sources/{data_source_id}/apis")
def get_source_apis(data_source_id: int) -> dict[str, object]:
    return {"apis": list_source_apis(DEFAULT_PLATFORM_DB, data_source_id)}


@core_router.post("/data-sources/{data_source_id}/apis/import-openapi")
def import_openapi_apis(data_source_id: int, payload: OpenApiImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations(DEFAULT_PLATFORM_DB, data_source_id, payload.spec)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/data-sources/{data_source_id}/apis/import-openapi-url")
def import_openapi_apis_from_url(data_source_id: int, payload: OpenApiUrlImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations_from_url(
            DEFAULT_PLATFORM_DB, data_source_id, payload.url, payload.timeoutSeconds
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/readiness")
def get_data_source_readiness(data_source_id: int) -> dict[str, object]:
    try:
        return assess_data_source_readiness(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/schema-drift")
def get_data_source_schema_drift(data_source_id: int) -> dict[str, object]:
    try:
        return analyze_schema_drift(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/semantic-coverage")
def get_data_source_semantic_coverage(data_source_id: int) -> dict[str, object]:
    try:
        return build_semantic_coverage(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/operation-bindings")
def get_data_source_operation_bindings(data_source_id: int) -> dict[str, object]:
    try:
        return assess_operation_bindings(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/kernel-package")
def get_kernel_package(data_source_id: int) -> dict[str, object]:
    try:
        return build_kernel_package(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/kernel-package/download")
def download_kernel_package(data_source_id: int) -> Response:
    try:
        asset = export_kernel_package(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=asset["content"],
        media_type=asset["mediaType"],
        headers={"Content-Disposition": f"attachment; filename={asset['filename']}"},
    )


@core_router.post("/data-sources/{data_source_id}/scan")
def scan_source(data_source_id: int) -> dict[str, object]:
    try:
        return scan_data_source(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/tables")
def list_source_tables(data_source_id: int) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
        tables = conn.execute(
            "select id, table_name, row_count, primary_key, scanned_at from source_table where data_source_id = ? order by table_name",
            (data_source_id,),
        ).fetchall()
        return {"tables": [dict(row) for row in tables]}


@core_router.get("/data-sources/{data_source_id}/tables/{table_name}/rows")
def browse_table_rows(data_source_id: int, table_name: str, limit: int = 50, offset: int = 0) -> dict[str, object]:
    try:
        return browse_source_table(DEFAULT_PLATFORM_DB, data_source_id, table_name, limit, offset)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/data-sources/{data_source_id}/initialize")
def initialize_data_source_knowledge_base(data_source_id: int) -> dict[str, object]:
    try:
        return initialize_knowledge_base(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/data-sources/{data_source_id}/reasoning-chain")
def get_data_source_reasoning_chain(data_source_id: int) -> dict[str, object]:
    return build_reasoning_chain(DEFAULT_PLATFORM_DB, data_source_id)


@core_router.get("/knowledge-bases")
def get_knowledge_bases() -> dict[str, object]:
    return {"items": list_knowledge_bases(DEFAULT_PLATFORM_DB)}


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


@core_router.get("/model/status")
def model_status() -> dict[str, object]:
    return OpenRouterClient(OpenRouterConfig.from_db_or_env(DEFAULT_PLATFORM_DB)).status()


@core_router.get("/model/config")
def get_openrouter_config() -> dict[str, object]:
    return get_model_config(DEFAULT_PLATFORM_DB)


@core_router.post("/model/config")
def update_openrouter_config(payload: ModelConfigUpdate) -> dict[str, object]:
    return update_model_config(DEFAULT_PLATFORM_DB, payload.model_dump(exclude_unset=True))


@core_router.delete("/model/config")
def reset_openrouter_config() -> dict[str, object]:
    return reset_model_config(DEFAULT_PLATFORM_DB)


@core_router.get("/model/config/test")
def test_openrouter_config() -> dict[str, object]:
    return test_model_config(DEFAULT_PLATFORM_DB)


@core_router.post("/ai/data-sources/{data_source_id}/ontology-suggestions")
def ai_ontology_suggestions(data_source_id: int) -> dict[str, object]:
    try:
        return generate_semantic_suggestions(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/ai/data-sources/{data_source_id}/blueprint-draft")
def ai_blueprint_draft(data_source_id: int) -> dict[str, object]:
    try:
        return generate_blueprint_draft(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/ai/data-sources/{data_source_id}/ontology-reasoning-chain")
def ai_ontology_reasoning_chain(data_source_id: int) -> dict[str, object]:
    try:
        return generate_ontology_reasoning_chain(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


class KnowledgeEntryReview(BaseModel):
    status: str
    objectCode: Optional[str] = None
    ruleCode: Optional[str] = None


@core_router.get("/ontologies/{ontology_id}/knowledge/documents")
def knowledge_documents(ontology_id: int) -> dict[str, object]:
    return {"items": list_documents(DEFAULT_PLATFORM_DB, ontology_id)}


@core_router.get("/ontologies/{ontology_id}/knowledge/entries")
def knowledge_entries(
    ontology_id: int,
    documentId: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> dict[str, object]:
    return {
        "items": list_entries(DEFAULT_PLATFORM_DB, ontology_id, document_id=documentId, status=status, limit=limit),
        "retrievalBackends": list(supported_retrieval_backends()),
        "embeddingModels": list(supported_embedding_models()),
    }


@core_router.post("/ontologies/{ontology_id}/knowledge/documents")
async def upload_knowledge_document(
    ontology_id: int,
    file: UploadFile = File(...),
    title: str = Form(""),
    objectCode: str = Form(""),
    ruleCode: str = Form(""),
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Ingest a policy or contract document as pending knowledge entries."""
    content = await file.read()
    name = file.filename or "document"
    try:
        if name.lower().endswith(".docx"):
            text = extract_text_from_docx(content)
        else:
            # Plain text and Markdown are accepted as-is; anything else is
            # rejected rather than silently mis-parsed.
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError as error:
                raise ValueError("仅支持 .docx 或 UTF-8 文本文件。") from error
        return ingest_document(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            title.strip() or Path(name).stem,
            text,
            source_name=name,
            object_code=objectCode,
            rule_code=ruleCode,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/knowledge/entries/{entry_id}/review")
def review_entry(
    entry_id: int,
    payload: KnowledgeEntryReview,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_knowledge_entry(
            DEFAULT_PLATFORM_DB,
            entry_id,
            payload.status,
            object_code=payload.objectCode,
            rule_code=payload.ruleCode,
            reviewer=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class FeedbackCreate(BaseModel):
    rating: str
    comment: str = ""
    correction: str = ""
    objectCode: str = ""
    ruleCode: str = ""


class FeedbackResolve(BaseModel):
    resolution: str = "resolved"


class EscalationCreate(BaseModel):
    assignee: str = ""
    reason: str = ""


class ConversationStatusUpdate(BaseModel):
    status: str


@core_router.get("/conversations")
def conversations(status: str = "", limit: int = 50) -> dict[str, object]:
    return {"items": list_conversations(DEFAULT_PLATFORM_DB, status=status, limit=limit)}


@core_router.get("/conversations/{session_id}")
def conversation_detail(session_id: str) -> dict[str, object]:
    try:
        return get_conversation(DEFAULT_PLATFORM_DB, session_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.post("/conversations/{session_id}/escalate")
def escalate(
    session_id: str,
    payload: EscalationCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Hand a conversation to a human."""
    try:
        return escalate_conversation(
            DEFAULT_PLATFORM_DB,
            session_id,
            assignee=payload.assignee,
            reason=payload.reason,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.patch("/conversations/{session_id}/status")
def update_conversation_status(
    session_id: str,
    payload: ConversationStatusUpdate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return set_conversation_status(DEFAULT_PLATFORM_DB, session_id, payload.status, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/conversations/messages/{message_id}/feedback")
def create_feedback(
    message_id: int,
    payload: FeedbackCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Record a verdict on one answer.

    Corrections are stored, never auto-applied: promoting one to a rule or a
    knowledge entry goes through governance.
    """
    try:
        return submit_feedback(
            DEFAULT_PLATFORM_DB,
            message_id,
            payload.rating,
            comment=payload.comment,
            correction=payload.correction,
            object_code=payload.objectCode,
            rule_code=payload.ruleCode,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/feedback")
def feedback_items(status: str = "", rating: str = "", limit: int = 100) -> dict[str, object]:
    return {
        "items": list_feedback(DEFAULT_PLATFORM_DB, status=status, rating=rating, limit=limit),
        "summary": feedback_summary(DEFAULT_PLATFORM_DB),
    }


@core_router.post("/feedback/{feedback_id}/resolve")
def resolve_feedback_item(
    feedback_id: int,
    payload: FeedbackResolve,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return resolve_feedback(DEFAULT_PLATFORM_DB, feedback_id, resolution=payload.resolution, actor=principal.actor)
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


class ResolverConfigure(BaseModel):
    kind: str
    table: str = ""
    primaryKey: str = "id"
    joins: list[dict[str, str]] = Field(default_factory=list)
    discriminatorColumn: str = ""
    discriminatorValue: str = ""
    query: str = ""
    idColumn: str = ""


@core_router.get("/ontologies/{ontology_id}/objects/{object_code}/resolver")
def object_resolver(ontology_id: int, object_code: str) -> dict[str, object]:
    """The instance resolver in effect for a business object."""
    try:
        return get_object_resolver(DEFAULT_PLATFORM_DB, ontology_id, object_code)
    except ResolverError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/resolver")
def set_object_resolver(
    ontology_id: int,
    object_code: str,
    payload: ResolverConfigure,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Attach a resolver so an object is no longer limited to one table.

    The spec is validated before storage, so an invalid configuration fails here
    rather than later as a failed assessment.
    """
    spec = ResolverSpec(
        kind=payload.kind,
        table=payload.table,
        primary_key=payload.primaryKey,
        joins=payload.joins,
        discriminator_column=payload.discriminatorColumn,
        discriminator_value=payload.discriminatorValue,
        query=payload.query,
        id_column=payload.idColumn,
    )
    try:
        return configure_object_resolver(DEFAULT_PLATFORM_DB, ontology_id, object_code, spec, actor=principal.actor)
    except ResolverError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/resolvers")
def resolvers() -> dict[str, object]:
    return {"kinds": list(supported_resolver_kinds())}


class AggregateDefine(BaseModel):
    name: str
    function: str
    targetTable: str
    targetColumn: str
    groupColumn: str
    valueColumn: str = ""
    excludeSelf: bool = False
    selfColumn: str = ""
    filterColumn: str = ""
    filterValue: str = ""
    description: str = ""


@core_router.get("/ontologies/{ontology_id}/aggregates")
def ontology_aggregates(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    """Cross-object aggregates available to rules."""
    return {"items": list_aggregates(DEFAULT_PLATFORM_DB, ontology_id, objectCode)}


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/aggregates")
def define_object_aggregate(
    ontology_id: int,
    object_code: str,
    payload: AggregateDefine,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare an aggregate that rules for this object may reference by name.

    Validated before storage, so an invalid definition is refused here rather than
    surfacing later as a failed assessment.
    """
    spec = AggregateSpec(
        name=payload.name,
        function=payload.function,
        target_table=payload.targetTable,
        target_column=payload.targetColumn,
        group_column=payload.groupColumn,
        value_column=payload.valueColumn,
        exclude_self=payload.excludeSelf,
        self_column=payload.selfColumn,
        filter_column=payload.filterColumn,
        filter_value=payload.filterValue,
    )
    try:
        return define_aggregate(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            spec,
            description=payload.description,
            actor=principal.actor,
        )
    except AggregationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class DerivedAttributeDefine(BaseModel):
    code: str
    name: str
    expression: str
    unit: str = ""
    description: str = ""


class AttributeUnitDeclare(BaseModel):
    unit: str = ""


@core_router.get("/source-types")
def source_types() -> dict[str, object]:
    """Data source types, including the ones declared but awaiting a driver.

    Both lists are returned because "why is Oracle not in the dropdown" is otherwise
    unanswerable from the UI: an active type and a declared-but-unavailable one look
    identical if only the active list is exposed.
    """
    # Activating first means the response reflects what is actually reachable rather than
    # what the catalogue lists.
    register_bundled_sql_sources(replace=True)
    return {
        "available": list(supported_source_types()),
        "declared": [
            {
                "sourceType": item["sourceType"],
                "dialect": item["dialect"],
                "driver": item["driverModule"],
                "available": item["driverAvailable"],
                "installHint": "" if item["driverAvailable"] else item["installHint"],
            }
            for item in describe_bundled_sql_sources()
        ],
        "dialects": list(known_dialects()),
    }


@core_router.get("/writeback-channels")
def writeback_channels() -> dict[str, object]:
    """Writeback channels, and what each declared database channel may actually write.

    The declared statements are part of the answer: a channel that can write anything is a
    very different thing from one that can perform three named operations, and an operator
    reviewing automation needs to see which it is.
    """
    return {
        "schemes": list(supported_executor_schemes()),
        "databaseTargets": registered_database_targets(),
    }


@core_router.get("/units")
def units() -> dict[str, object]:
    """Units available for attribute declarations, grouped by dimension.

    Comparison converts within a dimension and refuses across dimensions, so a
    caller needs the dimension to know which units are interchangeable.
    """
    return {
        "items": [
            {
                "code": unit.code,
                "name": unit.name,
                "dimension": unit.dimension,
                "toCanonical": unit.to_canonical,
            }
            for unit in known_units()
        ]
    }


@core_router.get("/ontologies/{ontology_id}/derived-attributes")
def ontology_derived_attributes(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    return {"items": list_derived_attributes(DEFAULT_PLATFORM_DB, ontology_id, objectCode)}


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/derived-attributes")
def define_object_derived_attribute(
    ontology_id: int,
    object_code: str,
    payload: DerivedAttributeDefine,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare a computed attribute that rules may reference by code.

    Validated through the rule sandbox before storage, so an unusable expression is
    refused here rather than surfacing later as a failed assessment.
    """
    try:
        return define_derived_attribute(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            DerivedSpec(
                code=payload.code,
                name=payload.name,
                expression=payload.expression,
                unit=payload.unit,
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except (DerivedAttributeError, UnitError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/attributes/{attribute_code}/unit")
def declare_attribute_unit(
    ontology_id: int,
    object_code: str,
    attribute_code: str,
    payload: AttributeUnitDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare the unit an attribute is measured in. An empty unit clears it."""
    try:
        return set_attribute_unit(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            attribute_code,
            payload.unit,
            actor=principal.actor,
        )
    except (DerivedAttributeError, UnitError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


class EventTypeDeclare(BaseModel):
    code: str
    name: str
    category: str = "interaction"
    payloadFields: list[str] = Field(default_factory=list)
    description: str = ""


class EventRecord(BaseModel):
    eventCode: str
    payload: dict[str, object] = Field(default_factory=dict)
    occurredAt: str = ""
    correlationId: str = ""


class SubtypeDeclare(BaseModel):
    parentObjectCode: str = ""


@core_router.get("/ontologies/{ontology_id}/event-types")
def ontology_event_types(ontology_id: int, objectCode: str = "") -> dict[str, object]:
    return {"items": list_event_types(DEFAULT_PLATFORM_DB, ontology_id, objectCode)}


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/event-types")
def declare_object_event_type(
    ontology_id: int,
    object_code: str,
    payload: EventTypeDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare a kind of event that can happen to instances of this object."""
    try:
        return declare_event_type(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            EventType(
                code=payload.code,
                name=payload.name,
                object_code=object_code,
                category=payload.category,
                payload_fields=list(payload.payloadFields),
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except EventError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.post("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/events")
def append_instance_event(
    ontology_id: int,
    object_code: str,
    instance_id: str,
    payload: EventRecord,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Append one event to an instance's history.

    Recording does not trigger automation: an event that could fire side effects
    would make replaying history re-execute business actions.
    """
    try:
        return record_event(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            instance_id,
            payload.eventCode,
            payload=dict(payload.payload),
            actor=principal.actor,
            occurred_at=payload.occurredAt,
            correlation_id=payload.correlationId,
        )
    except EventError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/events")
def instance_events(
    ontology_id: int, object_code: str, instance_id: str, limit: int = MAX_EVENT_HISTORY
) -> dict[str, object]:
    """One instance's event history, newest first."""
    return instance_timeline(DEFAULT_PLATFORM_DB, ontology_id, object_code, instance_id, limit)


class AttributeVersionRecord(BaseModel):
    attributeCode: str
    value: object = None
    validFrom: str = ""
    source: str = ""


@core_router.post("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/versions")
def record_instance_attribute_version(
    ontology_id: int,
    object_code: str,
    instance_id: str,
    payload: AttributeVersionRecord,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Record a new value for one attribute, closing the version it supersedes.

    Append-only: nothing is overwritten, so a verdict recorded earlier still cites a value
    that exists.
    """
    try:
        return record_attribute_version(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            instance_id,
            payload.attributeCode,
            payload.value,
            valid_from=payload.validFrom or None,
            actor=principal.actor,
            source=payload.source,
        )
    except TemporalError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/objects/{object_code}/instances/{instance_id}/versions")
def instance_attribute_history(
    ontology_id: int, object_code: str, instance_id: str, attributeCode: str = ""
) -> dict[str, object]:
    """One instance's attribute history, with the window it can actually answer for."""
    return instance_history(DEFAULT_PLATFORM_DB, ontology_id, object_code, instance_id, attribute_code=attributeCode)


class MatchKeyDeclare(BaseModel):
    primaryColumn: str
    secondaryColumn: str
    normalize: bool = True


class CrossSourceLinkDeclare(BaseModel):
    name: str
    secondaryDataSourceId: int
    secondaryTable: str
    matchKeys: list[MatchKeyDeclare] = Field(default_factory=list)
    prefix: str = ""
    mergeStrategy: str = "conflict"
    requireUnique: bool = True
    description: str = ""


@core_router.get("/ontologies/{ontology_id}/cross-source-links")
def ontology_cross_source_links(ontology_id: int) -> dict[str, object]:
    """本体的跨源对应声明。

    一并返回说明文字，因为「匹配是声明的、不是推断的」是这套机制的前提，
    而一个只看到列表的调用方会以为平台在做模糊匹配。
    """
    return describe_cross_source(DEFAULT_PLATFORM_DB, ontology_id)


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/cross-source-links")
def declare_object_cross_source_link(
    ontology_id: int,
    object_code: str,
    payload: CrossSourceLinkDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """声明这个对象如何对应到另一个数据源的一张表。

    匹配键必须显式给出：跨源判定会把「这两行是同一实例」写进判定链，
    因此它必须是可审阅的声明，而不是相似度推断出来的结果。
    """
    try:
        return declare_cross_source_link(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            CrossSourceLink(
                name=payload.name,
                primary_object_code=object_code,
                secondary_data_source_id=payload.secondaryDataSourceId,
                secondary_table=payload.secondaryTable,
                match_keys=tuple(
                    MatchKey(
                        primary_column=key.primaryColumn,
                        secondary_column=key.secondaryColumn,
                        normalize=key.normalize,
                    )
                    for key in payload.matchKeys
                ),
                prefix=payload.prefix,
                merge_strategy=payload.mergeStrategy,
                require_unique=payload.requireUnique,
                description=payload.description,
            ),
            actor=principal.actor,
        )
    except EntityResolutionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@core_router.get("/ontologies/{ontology_id}/hierarchy")
def ontology_hierarchy(ontology_id: int) -> dict[str, object]:
    """The declared type hierarchy, with inherited rule counts and overrides."""
    return {"items": describe_hierarchy(DEFAULT_PLATFORM_DB, ontology_id)}


@core_router.put("/ontologies/{ontology_id}/objects/{object_code}/parent")
def declare_object_subtype(
    ontology_id: int,
    object_code: str,
    payload: SubtypeDeclare,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Declare this object as a subtype of another, or clear the declaration.

    A subtype evaluates its ancestors' rules as well as its own, so this changes what
    every assessment of the object checks.
    """
    try:
        return declare_subtype(
            DEFAULT_PLATFORM_DB,
            ontology_id,
            object_code,
            payload.parentObjectCode,
            actor=principal.actor,
        )
    except HierarchyError as error:
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


@core_router.get("/governance/audit-log")
def audit_log(limit: int = 50) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
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


@core_router.get("/governance/model-invocations")
def model_invocations(limit: int = 50) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
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


@core_router.get("/governance/decisions")
def decisions(limit: int = 50) -> dict[str, object]:
    return {"items": list_decisions(DEFAULT_PLATFORM_DB, limit)}


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
ROUTERS: tuple[APIRouter, ...] = (core_router, workflow_permission_router)


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
