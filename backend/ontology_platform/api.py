from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .access_policy import PUBLIC_PATHS, describe_policy, is_public, required_capability
from .agent import agent_chat, get_agent_roles
from .agent_roles import delete_agent_role, init_agent_role_schema, upsert_agent_role
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
from .automation import execute_operation, preflight_operation
from .contract_documents import parse_rule_docx_bytes
from .coverage import build_semantic_coverage
from .credentials import redact_connection_uri
from .database import DEFAULT_PLATFORM_DB, configure_platform_db, connect, get_platform_config, initialize_platform_db
from .decisions import list_decisions
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
from .industry_blueprints import list_industry_blueprints, upsert_industry_blueprint
from .kernel_package import build_kernel_package, export_kernel_package
from .knowledge_base import browse_source_table, build_reasoning_chain, initialize_knowledge_base, list_knowledge_bases
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
from .vocabulary import default_object_code_for_ontology
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

# Authentication is on by default; it can only be disabled explicitly for local
# development, and the app logs loudly when it is.
AUTH_ENABLED = os.environ.get("ONTOLOGY_AUTH_DISABLED", "").strip().lower() not in {"1", "true", "yes"}

DEV_ADMIN_PRINCIPAL = Principal(user_id=0, username="dev-anonymous", display_name="开发匿名用户", role_code="admin")

app = FastAPI(title="本体改造研发平台", version="0.2.0", lifespan=lifespan)

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


def current_principal(request: Request) -> Principal:
    """The authenticated caller, for handlers that need the acting identity."""
    principal = getattr(request.state, "principal", None)
    if principal is None:
        if not AUTH_ENABLED:
            return DEV_ADMIN_PRINCIPAL
        raise HTTPException(status_code=401, detail="缺少访问令牌")
    return principal


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


@app.get("/health")
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


@app.post("/auth/login")
def auth_login(payload: LoginCreate) -> dict[str, object]:
    try:
        return login(DEFAULT_PLATFORM_DB, payload.username, payload.password)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/auth/logout")
def auth_logout(request: Request) -> dict[str, object]:
    return logout(DEFAULT_PLATFORM_DB, _bearer_token(request))


@app.get("/auth/me")
def auth_me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return principal.public_dict()


@app.post("/auth/change-password")
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


@app.get("/auth/users")
def auth_list_users() -> dict[str, object]:
    return {"items": list_users(DEFAULT_PLATFORM_DB), "roles": sorted(ROLE_CAPABILITIES)}


@app.post("/auth/users")
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


@app.patch("/auth/users/{username}/status")
def auth_set_user_status(
    username: str,
    payload: UserStatusUpdate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return set_user_status(DEFAULT_PLATFORM_DB, username, payload.status, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/auth/access-policy")
def auth_access_policy() -> dict[str, object]:
    """Effective route-to-capability policy, for review."""
    return {
        "authEnabled": AUTH_ENABLED,
        "roles": {role: sorted(caps) for role, caps in ROLE_CAPABILITIES.items()},
        "rules": describe_policy(),
        "publicPaths": sorted(PUBLIC_PATHS),
    }


@app.post("/demo/bootstrap")
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


@app.post("/demo/bootstrap/equipment")
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


@app.post("/data-sources")
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


@app.post("/onboarding/run")
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


@app.get("/data-sources")
def get_data_sources() -> dict[str, object]:
    items = list_data_sources(DEFAULT_PLATFORM_DB)
    return {"dataSources": items, "data_sources": items}


@app.post("/data-sources/test-connection")
def test_unregistered_data_source(payload: DataSourceConnectionTest) -> dict[str, object]:
    try:
        return check_data_source_connection(
            DEFAULT_PLATFORM_DB,
            source_type=payload.sourceType,
            connection_uri=payload.connectionUri,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/data-sources/{data_source_id}/test-connection")
def test_registered_data_source(data_source_id: int) -> dict[str, object]:
    try:
        return check_data_source_connection(DEFAULT_PLATFORM_DB, data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/data-sources/{data_source_id}/test-api-gateway")
def test_registered_api_gateway(data_source_id: int) -> dict[str, object]:
    try:
        return check_business_api_gateway(DEFAULT_PLATFORM_DB, data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/data-sources/{data_source_id}/apis")
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


@app.get("/data-sources/{data_source_id}/apis")
def get_source_apis(data_source_id: int) -> dict[str, object]:
    return {"apis": list_source_apis(DEFAULT_PLATFORM_DB, data_source_id)}


@app.post("/data-sources/{data_source_id}/apis/import-openapi")
def import_openapi_apis(data_source_id: int, payload: OpenApiImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations(DEFAULT_PLATFORM_DB, data_source_id, payload.spec)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/data-sources/{data_source_id}/apis/import-openapi-url")
def import_openapi_apis_from_url(data_source_id: int, payload: OpenApiUrlImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations_from_url(
            DEFAULT_PLATFORM_DB, data_source_id, payload.url, payload.timeoutSeconds
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/readiness")
def get_data_source_readiness(data_source_id: int) -> dict[str, object]:
    try:
        return assess_data_source_readiness(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/schema-drift")
def get_data_source_schema_drift(data_source_id: int) -> dict[str, object]:
    try:
        return analyze_schema_drift(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/semantic-coverage")
def get_data_source_semantic_coverage(data_source_id: int) -> dict[str, object]:
    try:
        return build_semantic_coverage(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/operation-bindings")
def get_data_source_operation_bindings(data_source_id: int) -> dict[str, object]:
    try:
        return assess_operation_bindings(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/kernel-package")
def get_kernel_package(data_source_id: int) -> dict[str, object]:
    try:
        return build_kernel_package(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/kernel-package/download")
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


@app.post("/data-sources/{data_source_id}/scan")
def scan_source(data_source_id: int) -> dict[str, object]:
    try:
        return scan_data_source(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/tables")
def list_source_tables(data_source_id: int) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
        tables = conn.execute(
            "select id, table_name, row_count, primary_key, scanned_at from source_table where data_source_id = ? order by table_name",
            (data_source_id,),
        ).fetchall()
        return {"tables": [dict(row) for row in tables]}


@app.get("/data-sources/{data_source_id}/tables/{table_name}/rows")
def browse_table_rows(data_source_id: int, table_name: str, limit: int = 50, offset: int = 0) -> dict[str, object]:
    try:
        return browse_source_table(DEFAULT_PLATFORM_DB, data_source_id, table_name, limit, offset)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/data-sources/{data_source_id}/initialize")
def initialize_data_source_knowledge_base(data_source_id: int) -> dict[str, object]:
    try:
        return initialize_knowledge_base(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/data-sources/{data_source_id}/reasoning-chain")
def get_data_source_reasoning_chain(data_source_id: int) -> dict[str, object]:
    return build_reasoning_chain(DEFAULT_PLATFORM_DB, data_source_id)


@app.get("/knowledge-bases")
def get_knowledge_bases() -> dict[str, object]:
    return {"items": list_knowledge_bases(DEFAULT_PLATFORM_DB)}


@app.post("/ontologies/draft")
def create_ontology_draft(payload: OntologyDraftCreate) -> dict[str, object]:
    try:
        return generate_ontology_draft(
            DEFAULT_PLATFORM_DB, payload.dataSourceId, payload.name, payload.domain, payload.blueprintId
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/industry-blueprints")
def get_industry_blueprints() -> dict[str, object]:
    return {"items": list_industry_blueprints(DEFAULT_PLATFORM_DB)}


@app.post("/industry-blueprints")
def upsert_blueprint(payload: IndustryBlueprintUpsert) -> dict[str, object]:
    try:
        return upsert_industry_blueprint(DEFAULT_PLATFORM_DB, payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/ontologies")
def get_ontologies() -> dict[str, object]:
    items = list_ontologies(DEFAULT_PLATFORM_DB)
    return {"items": items, "ontologies": items}


@app.get("/ontologies/{ontology_id}")
def get_ontology(ontology_id: int) -> dict[str, object]:
    with connect(DEFAULT_PLATFORM_DB) as conn:
        try:
            return summarize_ontology(conn, ontology_id)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/ontologies/{ontology_id}/export")
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


@app.get("/ontologies/{ontology_id}/mappings")
def get_ontology_mappings(ontology_id: int, status: Optional[str] = None) -> dict[str, object]:
    try:
        return list_semantic_mappings(DEFAULT_PLATFORM_DB, ontology_id, status)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/semantic-mappings/{mapping_id}/review")
def review_mapping(
    mapping_id: int,
    payload: MappingReviewCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_semantic_mapping(DEFAULT_PLATFORM_DB, mapping_id, payload.status, principal.actor, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/mappings/review")
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


@app.post("/ontologies/{ontology_id}/publish")
def publish_ontology_version(
    ontology_id: int,
    payload: OntologyPublishCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return publish_ontology(DEFAULT_PLATFORM_DB, ontology_id, principal.actor, payload.force)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/ontologies/{ontology_id}/release-readiness")
def get_ontology_release_readiness(ontology_id: int) -> dict[str, object]:
    try:
        return assess_ontology_release_readiness(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/derive")
def derive_ontology_draft(
    ontology_id: int,
    payload: OntologyDeriveCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return derive_ontology_version(DEFAULT_PLATFORM_DB, ontology_id, payload.version, principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/ontologies/{ontology_id}/rules")
def get_business_rules(ontology_id: int) -> dict[str, object]:
    try:
        return list_business_rules(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/rules")
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


@app.post("/ontologies/{ontology_id}/rules/import-word")
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


@app.post("/ontologies/{ontology_id}/rules/validate-expression")
def validate_ontology_rule_expression(ontology_id: int, payload: RuleExpressionValidateCreate) -> dict[str, object]:
    """Statically check a rule expression before it is saved."""
    available: Optional[list[str]] = None
    if payload.scopeObjectCode:
        available = available_rule_names(DEFAULT_PLATFORM_DB, ontology_id, payload.scopeObjectCode)
    return validate_rule_expression(payload.expression, available)


@app.get("/ontologies/{ontology_id}/rules/{rule_id}")
def get_ontology_rule(ontology_id: int, rule_id: int) -> dict[str, object]:
    try:
        return get_business_rule(DEFAULT_PLATFORM_DB, ontology_id, rule_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.put("/ontologies/{ontology_id}/rules/{rule_id}")
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


@app.delete("/ontologies/{ontology_id}/rules/{rule_id}")
def delete_ontology_rule(ontology_id: int, rule_id: int) -> dict[str, object]:
    try:
        return delete_business_rule(DEFAULT_PLATFORM_DB, ontology_id, rule_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.patch("/ontologies/{ontology_id}/rules/{rule_id}/status")
def toggle_ontology_rule_status(ontology_id: int, rule_id: int, status: str = "published") -> dict[str, object]:
    try:
        return toggle_business_rule_status(DEFAULT_PLATFORM_DB, ontology_id, rule_id, status)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/semantic/objects/{object_code}/instances/{instance_id}/explain")
def explain_object_instance(object_code: str, instance_id: str, ontologyId: Optional[int] = None) -> dict[str, object]:
    try:
        resolved = (
            ontologyId if ontologyId is not None else resolve_ontology_for_object(DEFAULT_PLATFORM_DB, object_code)
        )
        return explain_instance(DEFAULT_PLATFORM_DB, resolved, object_code, instance_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/semantic/objects/{object_code}/instances/{instance_id}/assess")
def assess_object_instance(object_code: str, instance_id: str, ontologyId: Optional[int] = None) -> dict[str, object]:
    try:
        resolved = (
            ontologyId if ontologyId is not None else resolve_ontology_for_object(DEFAULT_PLATFORM_DB, object_code)
        )
        return assess_instance(DEFAULT_PLATFORM_DB, resolved, object_code, instance_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/semantic/objects/{object_code}/consistency")
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


@app.post("/semantic/natural-language/query")
def ask_semantic_kernel(payload: NaturalLanguageQueryCreate) -> dict[str, object]:
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
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/agent/roles")
def list_agent_roles() -> dict[str, object]:
    return {"roles": get_agent_roles(DEFAULT_PLATFORM_DB)}


class AgentRoleUpsert(BaseModel):
    code: str
    name: str
    description: str = ""
    domain: str = ""
    systemPrompt: str = ""
    dataSourceId: Optional[int] = None


@app.post("/agent/roles")
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


@app.delete("/agent/roles/{code}")
def remove_agent_role(code: str, principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return delete_agent_role(DEFAULT_PLATFORM_DB, code, actor=principal.actor)


@app.post("/agent/chat")
def chat_with_agent(payload: AgentChatCreate) -> dict[str, object]:
    try:
        return agent_chat(
            DEFAULT_PLATFORM_DB,
            payload.message,
            payload.roleId,
            payload.dataSourceId,
            payload.objectCode,
            payload.history,
            payload.sessionId,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/automation/operations/{operation_code}/preflight")
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


@app.post("/automation/operations/{operation_code}/execute")
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


@app.get("/model/status")
def model_status() -> dict[str, object]:
    return OpenRouterClient(OpenRouterConfig.from_db_or_env(DEFAULT_PLATFORM_DB)).status()


@app.get("/model/config")
def get_openrouter_config() -> dict[str, object]:
    return get_model_config(DEFAULT_PLATFORM_DB)


@app.post("/model/config")
def update_openrouter_config(payload: ModelConfigUpdate) -> dict[str, object]:
    return update_model_config(DEFAULT_PLATFORM_DB, payload.model_dump(exclude_unset=True))


@app.delete("/model/config")
def reset_openrouter_config() -> dict[str, object]:
    return reset_model_config(DEFAULT_PLATFORM_DB)


@app.get("/model/config/test")
def test_openrouter_config() -> dict[str, object]:
    return test_model_config(DEFAULT_PLATFORM_DB)


@app.post("/ai/data-sources/{data_source_id}/ontology-suggestions")
def ai_ontology_suggestions(data_source_id: int) -> dict[str, object]:
    try:
        return generate_semantic_suggestions(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ai/data-sources/{data_source_id}/blueprint-draft")
def ai_blueprint_draft(data_source_id: int) -> dict[str, object]:
    try:
        return generate_blueprint_draft(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ai/data-sources/{data_source_id}/ontology-reasoning-chain")
def ai_ontology_reasoning_chain(data_source_id: int) -> dict[str, object]:
    try:
        return generate_ontology_reasoning_chain(DEFAULT_PLATFORM_DB, data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/governance/audit-log")
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


@app.get("/governance/model-invocations")
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


@app.get("/governance/decisions")
def decisions(limit: int = 50) -> dict[str, object]:
    return {"items": list_decisions(DEFAULT_PLATFORM_DB, limit)}


# ============================================================
# Workflow & Permission Management
# ============================================================

from .workflow_permission import (
    add_workflow_state,
    add_workflow_transition,
    authorize_tool,
    check_permission,
    check_tool_authorization,
    create_role,
    create_workflow,
    delete_workflow,
    get_available_actions,
    get_instance_history,
    get_instance_state,
    get_workflow,
    get_workflow_by_object,
    list_pending_reviews,
    list_policies,
    list_roles,
    list_tools,
    list_workflows,
    register_tool,
    review_tool_execution,
    transition_instance,
    upsert_permission_policy,
)


class WorkflowCreate(BaseModel):
    ontologyId: int
    objectCode: str
    name: str
    description: str = ""
    initialState: str = "draft"


class WorkflowStateAdd(BaseModel):
    code: str
    name: str
    description: str = ""
    isTerminal: bool = False
    color: str = "#666666"
    sortOrder: int = 0


class WorkflowTransitionAdd(BaseModel):
    fromState: str
    toState: str
    actionCode: str
    name: str
    guardExpression: str = ""
    requiresReview: bool = False
    reviewRole: str = ""
    sortOrder: int = 0


class WorkflowTransitionRun(BaseModel):
    instanceId: str
    actionCode: str
    reason: str = ""
    metadata: dict[str, object] = Field(default_factory=dict)


class WorkflowEnterInstance(BaseModel):
    objectCode: str
    instanceId: str


class RoleCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    isSystem: bool = False


class PermissionPolicyUpsert(BaseModel):
    roleId: int
    objectCode: str
    canRead: bool = True
    canWrite: bool = False
    canExecute: bool = False
    canDelete: bool = False
    filterExpression: str = ""
    description: str = ""


class PermissionCheck(BaseModel):
    roleCode: str
    objectCode: str
    operation: str = "read"


class ToolRegister(BaseModel):
    code: str
    name: str
    description: str = ""
    toolType: str = "function"
    inputSchema: dict[str, object] = Field(default_factory=dict)
    riskLevel: str = "low"
    requiresReview: bool = False


class ToolAuthorize(BaseModel):
    roleId: int
    toolId: int
    allowed: bool = True
    maxCallsPerHour: int = 100


class ToolAuthCheck(BaseModel):
    roleCode: str
    toolCode: str


class ToolExecutionReview(BaseModel):
    decision: str


# -- Workflow Endpoints --


@app.get("/workflows")
def get_workflows(ontologyId: Optional[int] = None) -> dict[str, object]:
    return {"items": list_workflows(DEFAULT_PLATFORM_DB, ontologyId)}


@app.post("/workflows")
def create_new_workflow(payload: WorkflowCreate) -> dict[str, object]:
    try:
        return create_workflow(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            payload.objectCode,
            payload.name,
            payload.description,
            payload.initialState,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/workflows/{workflow_id}")
def get_workflow_detail(workflow_id: int) -> dict[str, object]:
    try:
        return get_workflow(DEFAULT_PLATFORM_DB, workflow_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/workflows/by-object/{ontology_id}/{object_code}")
def get_workflow_for_object(ontology_id: int, object_code: str) -> dict[str, object]:
    wf = get_workflow_by_object(DEFAULT_PLATFORM_DB, ontology_id, object_code)
    if wf is None:
        raise HTTPException(status_code=404, detail="该业务对象未配置工作流")
    return wf


@app.delete("/workflows/{workflow_id}")
def delete_workflow_def(workflow_id: int) -> dict[str, object]:
    delete_workflow(DEFAULT_PLATFORM_DB, workflow_id)
    return {"deleted": True}


@app.post("/workflows/{workflow_id}/states")
def add_state(workflow_id: int, payload: WorkflowStateAdd) -> dict[str, object]:
    try:
        return add_workflow_state(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.code,
            payload.name,
            payload.description,
            payload.isTerminal,
            payload.color,
            payload.sortOrder,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/workflows/{workflow_id}/transitions")
def add_transition(workflow_id: int, payload: WorkflowTransitionAdd) -> dict[str, object]:
    try:
        return add_workflow_transition(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.fromState,
            payload.toState,
            payload.actionCode,
            payload.name,
            payload.guardExpression,
            payload.requiresReview,
            payload.reviewRole,
            payload.sortOrder,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/workflows/{workflow_id}/enter")
def enter_instance_to_workflow(workflow_id: int, payload: WorkflowEnterInstance) -> dict[str, object]:
    try:
        from .workflow_permission import enter_workflow

        return enter_workflow(DEFAULT_PLATFORM_DB, workflow_id, payload.objectCode, payload.instanceId)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/workflows/{workflow_id}/instances/{instance_id}")
def get_instance_workflow_state(workflow_id: int, instance_id: str) -> dict[str, object]:
    state = get_instance_state(DEFAULT_PLATFORM_DB, workflow_id, instance_id)
    if state is None:
        raise HTTPException(status_code=404, detail="实例不在工作流中")
    return state


@app.get("/workflows/{workflow_id}/instances/{instance_id}/actions")
def get_instance_available_actions(workflow_id: int, instance_id: str) -> dict[str, object]:
    actions = get_available_actions(DEFAULT_PLATFORM_DB, workflow_id, instance_id)
    return {"actions": actions}


@app.post("/workflows/{workflow_id}/transitions/run")
def run_transition(
    workflow_id: int,
    payload: WorkflowTransitionRun,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return transition_instance(
            DEFAULT_PLATFORM_DB,
            workflow_id,
            payload.instanceId,
            payload.actionCode,
            principal.actor,
            payload.reason,
            payload.metadata,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/workflows/{workflow_id}/instances/{instance_id}/history")
def get_instance_workflow_history(workflow_id: int, instance_id: str) -> dict[str, object]:
    return {"items": get_instance_history(DEFAULT_PLATFORM_DB, workflow_id, instance_id)}


# -- Permission Endpoints --


@app.get("/permissions/roles")
def get_permission_roles() -> dict[str, object]:
    return {"roles": list_roles(DEFAULT_PLATFORM_DB)}


@app.post("/permissions/roles")
def create_permission_role(payload: RoleCreate) -> dict[str, object]:
    try:
        return create_role(DEFAULT_PLATFORM_DB, payload.code, payload.name, payload.description, payload.isSystem)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/permissions/policies")
def get_permission_policies(roleId: Optional[int] = None) -> dict[str, object]:
    return {"policies": list_policies(DEFAULT_PLATFORM_DB, roleId)}


@app.post("/permissions/policies")
def upsert_policy(payload: PermissionPolicyUpsert) -> dict[str, object]:
    try:
        return upsert_permission_policy(
            DEFAULT_PLATFORM_DB,
            payload.roleId,
            payload.objectCode,
            payload.canRead,
            payload.canWrite,
            payload.canExecute,
            payload.canDelete,
            payload.filterExpression,
            payload.description,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/permissions/check")
def check_permission_endpoint(payload: PermissionCheck) -> dict[str, object]:
    return check_permission(DEFAULT_PLATFORM_DB, payload.roleCode, payload.objectCode, payload.operation)


# -- Tool Endpoints --


@app.get("/tools")
def get_all_tools() -> dict[str, object]:
    return {"tools": list_tools(DEFAULT_PLATFORM_DB)}


@app.post("/tools")
def register_new_tool(payload: ToolRegister) -> dict[str, object]:
    try:
        return register_tool(
            DEFAULT_PLATFORM_DB,
            payload.code,
            payload.name,
            payload.description,
            payload.toolType,
            payload.inputSchema,
            payload.riskLevel,
            payload.requiresReview,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/tools/authorize")
def authorize_tool_for_role(payload: ToolAuthorize) -> dict[str, object]:
    try:
        return authorize_tool(
            DEFAULT_PLATFORM_DB,
            payload.roleId,
            payload.toolId,
            payload.allowed,
            payload.maxCallsPerHour,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/tools/check-auth")
def check_tool_auth(payload: ToolAuthCheck) -> dict[str, object]:
    return check_tool_authorization(DEFAULT_PLATFORM_DB, payload.roleCode, payload.toolCode)


@app.get("/tools/pending-reviews")
def get_pending_reviews(limit: int = 50) -> dict[str, object]:
    return {"items": list_pending_reviews(DEFAULT_PLATFORM_DB, limit)}


@app.post("/tools/logs/{log_id}/review")
def review_execution(
    log_id: int,
    payload: ToolExecutionReview,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return review_tool_execution(DEFAULT_PLATFORM_DB, log_id, principal.actor, payload.decision)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/files")
def files() -> dict[str, str]:
    config = get_platform_config()
    return {
        "platformDbType": config.db_type,
        "platformDb": redact_connection_uri(config.connection_uri) or str(Path(DEFAULT_PLATFORM_DB).resolve()),
        "sampleDb": str(Path(DEFAULT_SAMPLE_DB).resolve()),
    }
