from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from .automation import execute_operation, preflight_operation
from .coverage import build_semantic_coverage
from .contract_documents import parse_contract_docx_bytes, parse_rule_docx_bytes
from .contract_management import add_contract_version, compare_contract_engines, create_contract, get_contract, get_contract_document, list_contracts
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
from .operation_bindings import assess_operation_bindings
from .ontology import export_ontology_asset, explain_instance, generate_ontology_draft, list_ontologies, summarize_ontology
from .release_readiness import assess_ontology_release_readiness
from .sample_data import DEFAULT_EQUIPMENT_SAMPLE_DB, DEFAULT_SAMPLE_DB, create_contract_sample_db, create_equipment_sample_db
from .semantic_kernel import assess_decision_consistency, assess_instance


@asynccontextmanager
async def lifespan(app: FastAPI):
    platform_db_type = os.environ.get("ONTOLOGY_PLATFORM_DB_TYPE", "sqlite").lower()
    platform_db_uri = os.environ.get("ONTOLOGY_PLATFORM_DB_URI", "")
    if platform_db_type != "sqlite":
        configure_platform_db(platform_db_type, platform_db_uri)
        initialize_platform_db()
    else:
        initialize_platform_db(DEFAULT_PLATFORM_DB)
    yield


app = FastAPI(title="本体改造研发平台", version="0.1.0", lifespan=lifespan)


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
    priority: int = 0
    category: str = ""
    effectiveStart: Optional[str] = None
    effectiveEnd: Optional[str] = None
    dependsOn: Optional[str] = None


class ContractDocumentParseOptions(BaseModel):
    persist: bool = False


class ContractCompareRequest(BaseModel):
    question: str = Field(min_length=2, max_length=1000)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents/contracts/parse")
async def parse_contract_document(file: UploadFile = File(...)) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="当前仅支持 .docx 文件解析")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        return parse_contract_docx_bytes(file.filename, content)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/contracts")
def managed_contracts() -> dict[str, object]:
    return {"items": list_contracts(DEFAULT_PLATFORM_DB)}


@app.post("/contracts")
async def upload_managed_contract(file: UploadFile = File(...), actor: str = Form("system")) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    content = await file.read()
    try:
        return create_contract(DEFAULT_PLATFORM_DB, file.filename, content, actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/contracts/{contract_id}")
def managed_contract_detail(contract_id: int) -> dict[str, object]:
    try:
        return get_contract(DEFAULT_PLATFORM_DB, contract_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.get("/contracts/{contract_id}/document")
def download_managed_contract(contract_id: int, version: Optional[int] = None) -> Response:
    try:
        document = get_contract_document(DEFAULT_PLATFORM_DB, contract_id, version)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=document["content"], media_type=document["mimeType"],
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(document['fileName'])}", "X-Document-SHA256": document["sha256"]},
    )


@app.post("/contracts/{contract_id}/versions")
async def upload_contract_version(contract_id: int, file: UploadFile = File(...), actor: str = Form("system")) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    try:
        return add_contract_version(DEFAULT_PLATFORM_DB, contract_id, file.filename, await file.read(), actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.post("/contracts/{contract_id}/compare")
def compare_managed_contract(contract_id: int, payload: ContractCompareRequest) -> dict[str, object]:
    try:
        return compare_contract_engines(DEFAULT_PLATFORM_DB, contract_id, payload.question)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


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
            payload.apiBaseUrl,
            payload.apiHeaders,
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
        return import_openapi_operations_from_url(DEFAULT_PLATFORM_DB, data_source_id, payload.url, payload.timeoutSeconds)
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
    actor: str = Form("rule_word_import"),
) -> dict[str, object]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    try:
        parsed = parse_rule_docx_bytes(file.filename, content)
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


@app.get("/ontologies/{ontology_id}/rules/{rule_id}")
def get_ontology_rule(ontology_id: int, rule_id: int) -> dict[str, object]:
    try:
        return get_business_rule(DEFAULT_PLATFORM_DB, ontology_id, rule_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.put("/ontologies/{ontology_id}/rules/{rule_id}")
def update_ontology_rule(ontology_id: int, rule_id: int, payload: BusinessRuleCreate) -> dict[str, object]:
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
            payload.actor,
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


@app.get("/files")
def files() -> dict[str, str]:
    config = get_platform_config()
    return {
        "platformDbType": config.db_type,
        "platformDb": config.connection_uri or str(Path(DEFAULT_PLATFORM_DB).resolve()),
        "sampleDb": str(Path(DEFAULT_SAMPLE_DB).resolve()),
    }
