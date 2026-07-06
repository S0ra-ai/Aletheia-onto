from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field

from .automation import execute_operation, preflight_operation
from .coverage import build_semantic_coverage
from .database import DEFAULT_PLATFORM_DB, connect, initialize_platform_db
from .decisions import list_decisions
from .governance import (
    bulk_review_semantic_mappings,
    derive_ontology_version,
    list_business_rules,
    list_semantic_mappings,
    publish_ontology,
    review_semantic_mapping,
    upsert_business_rule,
)
from .industry_blueprints import list_industry_blueprints, upsert_industry_blueprint
from .kernel_package import build_kernel_package, export_kernel_package
from .metadata import (
    analyze_schema_drift,
    assess_data_source_readiness,
    check_data_source_connection,
    import_openapi_operations,
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
    generate_semantic_suggestions,
    get_model_config,
    reset_model_config,
    test_model_config,
    update_model_config,
)
from .onboarding import run_onboarding_pipeline
from .ontology import export_ontology_asset, explain_instance, generate_ontology_draft, list_ontologies, summarize_ontology
from .release_readiness import assess_ontology_release_readiness
from .sample_data import DEFAULT_EQUIPMENT_SAMPLE_DB, DEFAULT_SAMPLE_DB, create_contract_sample_db, create_equipment_sample_db
from .semantic_kernel import assess_decision_consistency, assess_instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize_platform_db(DEFAULT_PLATFORM_DB)
    yield


app = FastAPI(title="本体改造研发平台", version="0.1.0", lifespan=lifespan)


class DataSourceCreate(BaseModel):
    name: str
    sourceType: str = "sqlite"
    connectionUri: str
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


class OperationExecuteCreate(OperationPreflightCreate):
    payload: dict[str, object] = Field(default_factory=dict)
    actor: str = "semantic_kernel"
    dryRun: bool = True
    timeoutSeconds: float = 10


class MappingReviewCreate(BaseModel):
    status: str
    reviewer: str = "system"
    note: str = ""


class BulkMappingReviewCreate(BaseModel):
    status: str
    reviewer: str = "system"
    note: str = ""


class OntologyPublishCreate(BaseModel):
    publisher: str = "system"


class OntologyDeriveCreate(BaseModel):
    version: str
    actor: str = "system"


class BusinessRuleCreate(BaseModel):
    code: str
    name: str
    ruleType: str
    scopeObjectCode: str
    expression: str
    severity: str
    naturalLanguage: str
    actor: str = "system"
    status: str = "published"


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/demo/bootstrap")
def bootstrap_demo() -> dict[str, object]:
    initialize_platform_db(DEFAULT_PLATFORM_DB)
    sample_path = create_contract_sample_db(DEFAULT_SAMPLE_DB)
    source = register_data_source(DEFAULT_PLATFORM_DB, "合同管理样例系统", "sqlite", str(sample_path), domain="合同管理", system_category="database+api")
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
    return {"dataSource": source.__dict__, "scan": scan, "ontology": ontology}


@app.post("/demo/bootstrap/equipment")
def bootstrap_equipment_demo() -> dict[str, object]:
    initialize_platform_db(DEFAULT_PLATFORM_DB)
    sample_path = create_equipment_sample_db(DEFAULT_EQUIPMENT_SAMPLE_DB)
    source = register_data_source(DEFAULT_PLATFORM_DB, "设备运维样例系统", "sqlite", str(sample_path), domain="设备运维", system_category="database+api")
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
    return {"dataSource": source.__dict__, "scan": scan, "ontology": ontology}


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
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return source.__dict__


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
            payload.blueprintId,
            payload.ontologyName,
            payload.generateOntology,
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


@app.post("/ontologies/draft")
def create_ontology_draft(payload: OntologyDraftCreate) -> dict[str, object]:
    try:
        return generate_ontology_draft(DEFAULT_PLATFORM_DB, payload.dataSourceId, payload.name, payload.domain, payload.blueprintId)
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
def review_mapping(mapping_id: int, payload: MappingReviewCreate) -> dict[str, object]:
    try:
        return review_semantic_mapping(DEFAULT_PLATFORM_DB, mapping_id, payload.status, payload.reviewer, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/mappings/review")
def review_ontology_mappings(ontology_id: int, payload: BulkMappingReviewCreate) -> dict[str, object]:
    try:
        return bulk_review_semantic_mappings(DEFAULT_PLATFORM_DB, ontology_id, payload.status, payload.reviewer, payload.note)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/publish")
def publish_ontology_version(ontology_id: int, payload: OntologyPublishCreate) -> dict[str, object]:
    try:
        return publish_ontology(DEFAULT_PLATFORM_DB, ontology_id, payload.publisher)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/ontologies/{ontology_id}/release-readiness")
def get_ontology_release_readiness(ontology_id: int) -> dict[str, object]:
    try:
        return assess_ontology_release_readiness(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/derive")
def derive_ontology_draft(ontology_id: int, payload: OntologyDeriveCreate) -> dict[str, object]:
    try:
        return derive_ontology_version(DEFAULT_PLATFORM_DB, ontology_id, payload.version, payload.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/ontologies/{ontology_id}/rules")
def get_business_rules(ontology_id: int) -> dict[str, object]:
    try:
        return list_business_rules(DEFAULT_PLATFORM_DB, ontology_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/ontologies/{ontology_id}/rules")
def create_or_update_business_rule(ontology_id: int, payload: BusinessRuleCreate) -> dict[str, object]:
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
            payload.actor,
            payload.status,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/semantic/objects/{object_code}/instances/{instance_id}/explain")
def explain_object_instance(object_code: str, instance_id: str, ontologyId: int = 1) -> dict[str, object]:
    try:
        return explain_instance(DEFAULT_PLATFORM_DB, ontologyId, object_code, instance_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/semantic/objects/{object_code}/instances/{instance_id}/assess")
def assess_object_instance(object_code: str, instance_id: str, ontologyId: int = 1) -> dict[str, object]:
    try:
        return assess_instance(DEFAULT_PLATFORM_DB, ontologyId, object_code, instance_id)
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
def execute_business_operation(operation_code: str, payload: OperationExecuteCreate) -> dict[str, object]:
    try:
        return execute_operation(
            DEFAULT_PLATFORM_DB,
            payload.ontologyId,
            payload.dataSourceId,
            operation_code,
            payload.instanceId,
            payload.objectCode,
            payload.payload,
            payload.actor,
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


@app.get("/files")
def files() -> dict[str, str]:
    return {
        "platformDb": str(Path(DEFAULT_PLATFORM_DB).resolve()),
        "sampleDb": str(Path(DEFAULT_SAMPLE_DB).resolve()),
    }
