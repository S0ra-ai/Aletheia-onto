"""CSV directories and REST APIs as data sources.

Generality item #12. These two matter more than the driver-based ones for a reason that is
easy to miss: they are the sources a *first evaluation* uses. Getting production database
credentials takes weeks; an extract or an API token takes an afternoon. A platform that
can only read databases it has credentials for cannot be tried at all.

They are also the two that can be proven in CI without any external service, which is why
the end-to-end assertions here go all the way to a verdict rather than stopping at "the
adapter returned some tables".

The properties worth pinning down are about what is **not** inferred:

- **Foreign keys are never guessed from column names.** `customer_id` next to
  `customers.csv` is almost certainly a foreign key -- but relation semantics (ADR-0012)
  rest on declared structure, and a relation whose cardinality came from a naming
  coincidence would be unexplainable in a verdict.
- **A REST schema is never sampled from a payload.** A schema derived from one response
  changes when the response changes, and a verdict resting on it would be unreproducible.
- **A primary key requires the data to prove it.** Inferring one from the name alone would
  make `fetch_one` return an arbitrary row when values repeat -- an instance identity
  silently pointing at the wrong record.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.file_adapter import (
    CSVAdapter,
    FileSourceError,
    coerce_value,
    describe_file_source,
    foreign_key_candidates,
    infer_column_type,
    infer_primary_key,
    resolve_directory,
)
from ontology_platform.metadata import register_data_source, scan_data_source
from ontology_platform.ontology import generate_ontology_draft
from ontology_platform.rest_adapter import (
    RestResource,
    RestSourceError,
    RestSpec,
    register_openapi_source,
    register_rest_source,
    resources_from_openapi,
)
from ontology_platform.semantic_kernel import assess_instance

# -- CSV: type inference --


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["1", "2", "3"], "integer"),
        (["1.5", "2"], "number"),
        (["true", "false"], "boolean"),
        (["2026-01-01", "2026-12-31"], "date"),
        (["2026-01-01 10:00:00"], "timestamp"),
        (["abc", "def"], "text"),
        ([], "text"),
        (["", ""], "text"),
    ],
)
def test_column_types_are_inferred_narrowest_first(values, expected) -> None:
    assert infer_column_type(values) == expected


def test_one_bad_value_makes_the_whole_column_text() -> None:
    """A column that is 99% integers and 1% `N/A` is text.

    Calling it integer would make a rule comparing it fail closed on exactly those rows,
    which reads as a business violation rather than as a parsing problem.
    """
    assert infer_column_type(["1", "2", "N/A"]) == "text"


def test_empty_cells_do_not_change_the_type() -> None:
    assert infer_column_type(["1", "", "3"]) == "integer"


def test_values_are_coerced_so_rules_compare_real_numbers() -> None:
    """Otherwise `amount > 0` compares `str > int`, which fail-closed reports as a
    violation -- turning a parsing detail into a wrong verdict."""
    assert coerce_value("42", "integer") == 42
    assert coerce_value("4.5", "number") == 4.5
    assert coerce_value("", "integer") is None
    assert coerce_value("2026/03/01", "date") == "2026-03-01"


def test_an_unparseable_value_stays_as_text_rather_than_becoming_none() -> None:
    """None would compare as absence; the raw string at least fails visibly."""
    assert coerce_value("N/A", "integer") == "N/A"


# -- CSV: key inference --


def test_a_primary_key_must_be_unique_and_complete() -> None:
    rows = [{"id": "1"}, {"id": "2"}]
    assert infer_primary_key("contracts", ["id"], rows) == "id"


def test_a_repeating_candidate_is_not_a_primary_key() -> None:
    """Otherwise `fetch_one` returns an arbitrary row -- an instance identity silently
    pointing at the wrong record."""
    rows = [{"id": "1"}, {"id": "1"}]
    assert infer_primary_key("contracts", ["id"], rows) == ""


def test_a_candidate_with_blanks_is_not_a_primary_key() -> None:
    rows = [{"id": "1"}, {"id": ""}]
    assert infer_primary_key("contracts", ["id"], rows) == ""


def test_a_table_specific_key_name_is_recognised() -> None:
    rows = [{"contract_id": "1"}, {"contract_id": "2"}]
    assert infer_primary_key("contracts", ["contract_id"], rows) == "contract_id"


# -- CSV: fixtures --


@pytest.fixture
def csv_directory(tmp_path: Path) -> Path:
    directory = tmp_path / "extract"
    directory.mkdir()
    (directory / "customers.csv").write_text(
        "id,name,credit_status\n1,甲公司,normal\n2,乙公司,blacklist\n",
        encoding="utf-8",
    )
    (directory / "contracts.csv").write_text(
        "id,customer_id,amount,status,signed_date\n1,1,500,effective,2026-01-01\n2,2,900,draft,\n",
        encoding="utf-8",
    )
    # Ignored: no header, and a dotfile.
    (directory / "notes.txt").write_text("not a table", encoding="utf-8")
    (directory / ".hidden.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    return directory


def test_a_directory_of_csvs_scans_as_tables(csv_directory: Path) -> None:
    tables = {table.name: table for table in CSVAdapter().scan(str(csv_directory))}
    assert set(tables) == {"customers", "contracts"}, "非 CSV 与隐藏文件不应被登记"
    contracts = tables["contracts"]
    assert contracts.row_count == 2
    assert contracts.primary_key == "id"
    types = {column.name: column.data_type for column in contracts.columns}
    assert types["amount"] == "integer"
    assert types["status"] == "text"
    # `signed_date` is blank on one row, so the column is nullable and still a date.
    signed = next(column for column in contracts.columns if column.name == "signed_date")
    assert signed.nullable is True
    assert signed.data_type == "date"


def test_foreign_keys_are_not_inferred_from_column_names(csv_directory: Path) -> None:
    """The central restraint. A guessed foreign key would give a relation whose
    cardinality and strength rest on a naming coincidence, and a verdict citing it could
    not be explained."""
    tables = CSVAdapter().scan(str(csv_directory))
    assert all(table.foreign_keys == [] for table in tables)


def test_candidates_are_reported_so_a_modeller_can_declare_them(csv_directory: Path) -> None:
    candidates = foreign_key_candidates(csv_directory)
    assert {
        "sourceTable": "contracts",
        "column": "customer_id",
        "targetTable": "customers",
        "targetColumn": "id",
    } in candidates
    description = describe_file_source(str(csv_directory))
    assert description["foreignKeyCandidates"]
    assert "不会自动建立关系" in description["note"]


def test_the_uri_accepts_a_scheme_or_a_bare_path(csv_directory: Path) -> None:
    assert resolve_directory(str(csv_directory)) == csv_directory
    assert resolve_directory(f"file://{csv_directory}") == csv_directory
    assert resolve_directory(f"csv://{csv_directory}") == csv_directory


def test_pointing_at_a_single_file_uses_its_directory(csv_directory: Path) -> None:
    """That is what a user pointing at `contracts.csv` means."""
    assert resolve_directory(str(csv_directory / "contracts.csv")) == csv_directory


def test_a_missing_directory_is_refused_with_the_path(csv_directory: Path) -> None:
    with pytest.raises(FileSourceError, match="不存在"):
        resolve_directory(str(csv_directory / "nope"))


def test_an_empty_directory_reports_why_it_is_unusable(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    status = CSVAdapter().test_connection(str(empty))
    assert status["reachable"] is False
    assert "没有 CSV" in status["message"]


def test_the_runtime_reads_and_relates_rows(csv_directory: Path) -> None:
    with CSVAdapter().runtime(str(csv_directory)) as runtime:
        row = runtime.fetch_one("contracts", "id", "1")
        assert row is not None and row["amount"] == 500
        related = runtime.fetch_related_many("contracts", "customer_id", 1)
        assert [item["id"] for item in related] == [1]
        assert runtime.fetch_primary_keys("contracts", "id") == [1, 2]
        rows, total = runtime.browse_rows("contracts", limit=1, offset=1)
        assert total == 2 and rows[0]["id"] == 2


def test_a_missing_related_file_yields_no_rows_rather_than_failing(csv_directory: Path) -> None:
    """A declared relation whose target file is absent must not fail the whole
    assessment; the rule referencing it fails closed instead."""
    with CSVAdapter().runtime(str(csv_directory)) as runtime:
        assert runtime.fetch_related_many("absent_table", "x", 1) == []


def test_a_csv_source_reaches_a_verdict(csv_directory: Path, tmp_path: Path) -> None:
    """The full claim: an extract on disk gets ontology drafting and assessment, not just
    a table listing."""
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "导出文件", "csv", str(csv_directory), domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology_id = generate_ontology_draft(platform_db, source.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        object_code = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.table_name = 'contracts'
            """,
            (ontology_id,),
        ).fetchone()["code"]
    result = assess_instance(platform_db, ontology_id, object_code, "1")
    assert result["decision"]["status"] in {"approved", "review", "blocked"}
    assert result["ruleResults"], "CSV 数据源未产出任何规则判定"


def test_csv_is_available_without_installing_anything() -> None:
    """Nobody would guess they must import `file_adapter`, so it registers itself."""
    from ontology_platform.adapters import supported_source_types

    assert "csv" in supported_source_types()
    assert get_adapter("file").source_type == "csv"


# -- REST --


class _Handler(BaseHTTPRequestHandler):
    """A minimal API: a collection, a detail endpoint, and a wrapped collection."""

    # ClassVar because BaseHTTPRequestHandler is instantiated per request, and these are
    # shared fixture data rather than per-connection state.
    customers: ClassVar[list[dict]] = [
        {"id": 1, "name": "甲公司", "credit_status": "normal", "internal_note": "不应下发"},
        {"id": 2, "name": "乙公司", "credit_status": "blacklist", "internal_note": "x"},
    ]
    contracts: ClassVar[list[dict]] = [
        {"id": 1, "customer_id": 1, "amount": 500, "status": "effective"},
        {"id": 2, "customer_id": 2, "amount": 900, "status": "draft"},
    ]

    def do_GET(self) -> None:
        if self.path == "/api/customers":
            self._send(self.customers)
        elif self.path.startswith("/api/customers/"):
            wanted = self.path.rsplit("/", 1)[-1]
            match = [row for row in self.customers if str(row["id"]) == wanted]
            self._send(match[0] if match else {})
        elif self.path == "/api/contracts":
            # Wrapped, to exercise itemsPath.
            self._send({"data": {"items": self.contracts}})
        elif self.path == "/api/broken":
            self._send_raw(b"not json")
        else:
            self.send_error(404)

    def _send(self, payload) -> None:
        self._send_raw(json.dumps(payload).encode("utf-8"))

    def _send_raw(self, body: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        """Silence the default stderr logging so test output stays readable."""


@pytest.fixture
def rest_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()


def _crm_spec(source_type: str = "crm") -> RestSpec:
    return RestSpec(
        source_type=source_type,
        resources=(
            RestResource(
                name="customers",
                list_path="/api/customers",
                detail_path="/api/customers/{id}",
                primary_key="id",
                fields=("id", "name", "credit_status"),
                field_types={"id": "integer"},
            ),
            RestResource(
                name="contracts",
                list_path="/api/contracts",
                primary_key="id",
                fields=("id", "customer_id", "amount", "status"),
                field_types={"id": "integer", "customer_id": "integer", "amount": "number"},
                items_path="data.items",
            ),
        ),
    )


def test_a_resource_must_declare_its_fields() -> None:
    """A REST response has no discoverable schema, and sampling one would make the model
    change when the payload changes."""
    with pytest.raises(RestSourceError, match="必须声明字段"):
        RestResource(name="x", list_path="/x", fields=()).validate()


def test_the_primary_key_must_be_a_declared_field() -> None:
    with pytest.raises(RestSourceError, match="主键"):
        RestResource(name="x", list_path="/x", primary_key="id", fields=("name",)).validate()


def test_a_list_path_must_be_absolute() -> None:
    with pytest.raises(RestSourceError, match="listPath"):
        RestResource(name="x", list_path="x", fields=("id",)).validate()


def test_duplicate_resource_names_are_refused() -> None:
    resource = RestResource(name="x", list_path="/x", fields=("id",))
    with pytest.raises(RestSourceError, match="重名"):
        RestSpec(source_type="dup", resources=(resource, resource)).validate()


def test_a_rest_source_scans_from_the_declaration(rest_server) -> None:
    register_rest_source(_crm_spec(), replace=True)
    tables = {table.name: table for table in get_adapter("crm").scan(rest_server)}
    assert set(tables) == {"customers", "contracts"}
    assert tables["contracts"].row_count == 2
    assert tables["contracts"].primary_key == "id"
    # Declared types survive; the shape came from the declaration, the profile from data.
    amount = next(column for column in tables["contracts"].columns if column.name == "amount")
    assert amount.data_type == "number"
    assert amount.profile.samples


def test_undeclared_fields_are_not_passed_through(rest_server) -> None:
    """The declaration is the contract. Passing through whatever the API returned would
    make a rule's available names depend on the payload of the moment -- and would leak
    fields the API owner did not intend to expose to the model."""
    register_rest_source(_crm_spec(), replace=True)
    with get_adapter("crm").runtime(rest_server) as runtime:
        row = runtime.fetch_one("customers", "id", "1")
    assert row is not None
    assert "internal_note" not in row


def test_a_wrapped_collection_is_read_through_items_path(rest_server) -> None:
    register_rest_source(_crm_spec(), replace=True)
    with get_adapter("crm").runtime(rest_server) as runtime:
        rows = runtime.rows("contracts")
    assert [row["id"] for row in rows] == [1, 2]


def test_a_detail_endpoint_is_preferred_for_one_instance(rest_server) -> None:
    register_rest_source(_crm_spec(), replace=True)
    with get_adapter("crm").runtime(rest_server) as runtime:
        row = runtime.fetch_one("customers", "id", "2")
    assert row is not None and row["credit_status"] == "blacklist"


def test_related_rows_are_filtered_client_side(rest_server) -> None:
    register_rest_source(_crm_spec(), replace=True)
    with get_adapter("crm").runtime(rest_server) as runtime:
        related = runtime.fetch_related_many("contracts", "customer_id", 2)
    assert [row["id"] for row in related] == [2]


def test_responses_are_cached_within_one_runtime(rest_server) -> None:
    """Without this a single verdict could issue dozens of calls to one endpoint."""
    register_rest_source(_crm_spec(), replace=True)
    with get_adapter("crm").runtime(rest_server) as runtime:
        first = runtime.rows("customers")
        second = runtime.rows("customers")
    assert first is second, "同一次运行内应复用响应"


def test_an_unreachable_related_resource_yields_no_rows(rest_server) -> None:
    spec = RestSpec(
        source_type="crm_broken",
        resources=(RestResource(name="missing", list_path="/api/nowhere", primary_key="id", fields=("id",)),),
    )
    register_rest_source(spec, replace=True)
    with get_adapter("crm_broken").runtime(rest_server) as runtime:
        assert runtime.fetch_related_many("missing", "id", 1) == []


def test_a_non_json_response_is_reported_not_silently_empty(rest_server) -> None:
    """An empty result would read as "this resource has no rows", which sends someone
    looking in the wrong place."""
    spec = RestSpec(
        source_type="crm_bad_json",
        resources=(RestResource(name="broken", list_path="/api/broken", primary_key="id", fields=("id",)),),
    )
    register_rest_source(spec, replace=True)
    status = get_adapter("crm_bad_json").test_connection(rest_server)
    assert status["reachable"] is False
    assert "JSON" in status["message"]


def test_a_rest_source_reaches_a_verdict(rest_server, tmp_path: Path) -> None:
    register_rest_source(_crm_spec("crm_e2e"), replace=True)
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "CRM 接口", "crm_e2e", rest_server, domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology_id = generate_ontology_draft(platform_db, source.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        object_code = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = ? and st.table_name = 'contracts'
            """,
            (ontology_id,),
        ).fetchone()["code"]
    result = assess_instance(platform_db, ontology_id, object_code, "1")
    assert result["decision"]["status"] in {"approved", "review", "blocked"}
    assert result["ruleResults"], "REST 数据源未产出任何规则判定"


# -- OpenAPI-derived declarations --


OPENAPI = {
    "paths": {
        "/api/customers": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "id": {"type": "integer"},
                                            "name": {"type": "string"},
                                            "created_at": {"type": "string", "format": "date-time"},
                                        },
                                    },
                                }
                            }
                        }
                    }
                }
            }
        },
        # Skipped: a path parameter means it is not a collection.
        "/api/customers/{id}": {"get": {"responses": {"200": {}}}},
        # Skipped: no readable schema, so it is left for a hand declaration.
        "/api/opaque": {"get": {"responses": {"200": {"content": {"application/json": {}}}}}},
    }
}


def test_openapi_yields_declarations_for_readable_collections() -> None:
    """Still a declaration -- just one written by the API's owner."""
    resources = {resource.name: resource for resource in resources_from_openapi(OPENAPI)}
    assert set(resources) == {"api_customers"}
    customers = resources["api_customers"]
    assert customers.primary_key == "id"
    assert set(customers.fields) == {"id", "name", "created_at"}
    assert customers.field_types["id"] == "integer"
    # A date-time format becomes a timestamp, so rules can compare it as one.
    assert customers.field_types["created_at"] == "timestamp"


def test_an_openapi_document_with_nothing_usable_fails_loudly() -> None:
    """Registering an empty source type would look like success and then behave as though
    the API had no data."""
    with pytest.raises(RestSourceError, match="没有可用于声明的集合端点"):
        register_openapi_source("empty_api", {"paths": {}}, replace=True)


def test_an_openapi_derived_source_is_usable(rest_server) -> None:
    register_openapi_source("crm_from_openapi", OPENAPI, replace=True)
    tables = get_adapter("crm_from_openapi").scan(rest_server)
    assert [table.name for table in tables] == ["api_customers"]
    assert tables[0].row_count == 2
