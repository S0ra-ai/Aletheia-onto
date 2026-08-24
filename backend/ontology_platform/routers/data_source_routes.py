"""Data source routes: registration, probing, metadata scan and the kernel package.

Everything about a legacy system *as a source* -- registering it, testing whether the
credentials work, scanning its schema, browsing rows, and reporting how ready it is to
be modelled. Ontology construction lives elsewhere; this module stops at "we can read
this system and we know what is in it".

`/source-types` and `/writeback-channels` belong here rather than in a separate
capabilities module: both answer "what can this deployment connect to", which is the
question a caller asks immediately before registering a source. `/source-types` reports
declared-but-unavailable drivers with an install hint, so "why is Oracle missing" is
answerable without reading the source.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from ..adapters import supported_source_types
from ..automation import supported_executor_schemes
from ..coverage import build_semantic_coverage
from ..database import connect
from ..db_executors import registered_database_targets
from ..generic_sql_adapter import describe_bundled_sql_sources, register_bundled_sql_sources
from ..http_runtime import platform_db
from ..kernel_package import build_kernel_package, export_kernel_package
from ..knowledge_base import (
    browse_source_table,
    build_reasoning_chain,
    initialize_knowledge_base,
    list_knowledge_bases,
)
from ..metadata import (
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
from ..onboarding import run_onboarding_pipeline
from ..operation_bindings import assess_operation_bindings
from ..sql_dialects import known_dialects

router = APIRouter()


# -- Request models --


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


@router.post("/data-sources")
def create_data_source(payload: DataSourceCreate) -> dict[str, object]:
    try:
        source = register_data_source(
            platform_db(),
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


@router.post("/onboarding/run")
def run_onboarding(payload: OnboardingRunCreate) -> dict[str, object]:
    try:
        return run_onboarding_pipeline(
            platform_db(),
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


@router.get("/data-sources")
def get_data_sources() -> dict[str, object]:
    items = list_data_sources(platform_db())
    return {"dataSources": items, "data_sources": items}


@router.post("/data-sources/test-connection")
def test_unregistered_data_source(payload: DataSourceConnectionTest) -> dict[str, object]:
    try:
        return check_data_source_connection(
            platform_db(),
            source_type=payload.sourceType,
            connection_uri=payload.connectionUri,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/data-sources/{data_source_id}/test-connection")
def test_registered_data_source(data_source_id: int) -> dict[str, object]:
    try:
        return check_data_source_connection(platform_db(), data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/data-sources/{data_source_id}/test-api-gateway")
def test_registered_api_gateway(data_source_id: int) -> dict[str, object]:
    try:
        return check_business_api_gateway(platform_db(), data_source_id=data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/data-sources/{data_source_id}/apis")
def create_source_api(data_source_id: int, payload: SourceApiCreate) -> dict[str, object]:
    try:
        source_api = register_source_api(
            platform_db(),
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


@router.get("/data-sources/{data_source_id}/apis")
def get_source_apis(data_source_id: int) -> dict[str, object]:
    return {"apis": list_source_apis(platform_db(), data_source_id)}


@router.post("/data-sources/{data_source_id}/apis/import-openapi")
def import_openapi_apis(data_source_id: int, payload: OpenApiImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations(platform_db(), data_source_id, payload.spec)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/data-sources/{data_source_id}/apis/import-openapi-url")
def import_openapi_apis_from_url(data_source_id: int, payload: OpenApiUrlImportCreate) -> dict[str, object]:
    try:
        return import_openapi_operations_from_url(platform_db(), data_source_id, payload.url, payload.timeoutSeconds)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/readiness")
def get_data_source_readiness(data_source_id: int) -> dict[str, object]:
    try:
        return assess_data_source_readiness(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/schema-drift")
def get_data_source_schema_drift(data_source_id: int) -> dict[str, object]:
    try:
        return analyze_schema_drift(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/semantic-coverage")
def get_data_source_semantic_coverage(data_source_id: int) -> dict[str, object]:
    try:
        return build_semantic_coverage(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/operation-bindings")
def get_data_source_operation_bindings(data_source_id: int) -> dict[str, object]:
    try:
        return assess_operation_bindings(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/kernel-package")
def get_kernel_package(data_source_id: int) -> dict[str, object]:
    try:
        return build_kernel_package(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/kernel-package/download")
def download_kernel_package(data_source_id: int) -> Response:
    try:
        asset = export_kernel_package(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return Response(
        content=asset["content"],
        media_type=asset["mediaType"],
        headers={"Content-Disposition": f"attachment; filename={asset['filename']}"},
    )


@router.post("/data-sources/{data_source_id}/scan")
def scan_source(data_source_id: int) -> dict[str, object]:
    try:
        return scan_data_source(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/tables")
def list_source_tables(data_source_id: int) -> dict[str, object]:
    with connect(platform_db()) as conn:
        tables = conn.execute(
            "select id, table_name, row_count, primary_key, scanned_at from source_table where data_source_id = ? order by table_name",
            (data_source_id,),
        ).fetchall()
        return {"tables": [dict(row) for row in tables]}


@router.get("/data-sources/{data_source_id}/tables/{table_name}/rows")
def browse_table_rows(data_source_id: int, table_name: str, limit: int = 50, offset: int = 0) -> dict[str, object]:
    try:
        return browse_source_table(platform_db(), data_source_id, table_name, limit, offset)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/data-sources/{data_source_id}/initialize")
def initialize_data_source_knowledge_base(data_source_id: int) -> dict[str, object]:
    try:
        return initialize_knowledge_base(platform_db(), data_source_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/data-sources/{data_source_id}/reasoning-chain")
def get_data_source_reasoning_chain(data_source_id: int) -> dict[str, object]:
    return build_reasoning_chain(platform_db(), data_source_id)


@router.get("/knowledge-bases")
def get_knowledge_bases() -> dict[str, object]:
    return {"items": list_knowledge_bases(platform_db())}


@router.get("/source-types")
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


@router.get("/writeback-channels")
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
