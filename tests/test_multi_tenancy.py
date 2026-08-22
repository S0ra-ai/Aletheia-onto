"""Multi-tenant isolation: separate schema plus a tenant_id column.

Implements ADR-0006. The two layers exist because their failure modes do not
overlap: the schema stops a query that forgets its tenant filter, and tenant_id
turns a mis-routed connection into a visible error rather than a silent
cross-tenant read.

That second property is the reason the shared-table design was rejected: a missed
`where tenant_id = ?` is invisible in single-tenant test data. So these tests
assert isolation *positively* -- tenant A cannot see tenant B's rows -- rather than
only checking that a filter string was appended.
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform import database as database_module
from ontology_platform.context import PlatformContext, reset_default_context, use_context
from ontology_platform.metadata import list_data_sources, register_data_source
from ontology_platform.tenancy import (
    SCHEMA_PREFIX,
    TENANT_SCOPED_TABLES,
    TenantError,
    assert_tenant_row,
    list_tenants,
    provision_tenant,
    require_tenant,
    schema_for,
    scope_query,
    stamp_tenant,
    tenant_context,
    tenant_statistics,
    validate_tenant,
)


@pytest.fixture(autouse=True)
def _clean_default():
    reset_default_context()
    saved = database_module._platform_adapter
    database_module._platform_adapter = None
    yield
    reset_default_context()
    database_module._platform_adapter = saved


@pytest.fixture
def base(tmp_path: Path) -> PlatformContext:
    return PlatformContext(db_type="sqlite", connection_uri=str(tmp_path / "platform.sqlite3"))


def _business_db(path: Path) -> str:
    sqlite3.connect(path).close()
    return str(path)


# -- Identifier validation: this is an injection boundary --


@pytest.mark.parametrize(
    "value",
    [
        "acme; drop table data_source",
        'public"',
        "tenant'--",
        "1abc",
        "",
        "   ",
        "a" * 40,
        "has space",
        "has-dash",
    ],
)
def test_unsafe_tenant_identifiers_are_rejected(value) -> None:
    """Tenant names are interpolated into DDL and search_path, which cannot bind."""
    with pytest.raises(TenantError):
        validate_tenant(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("acme", "acme"), ("ACME", "acme"), ("  acme  ", "acme"), ("a_1", "a_1")],
)
def test_valid_identifiers_are_normalised(value, expected) -> None:
    assert validate_tenant(value) == expected


def test_schema_name_is_prefixed_to_avoid_system_collisions() -> None:
    """Without a prefix a tenant could be named `public` or `information_schema`."""
    assert schema_for("acme") == f"{SCHEMA_PREFIX}acme"
    assert schema_for("public") == f"{SCHEMA_PREFIX}public"


# -- Fail-closed --


def test_require_tenant_refuses_when_no_context_is_bound() -> None:
    """Defaulting to "any tenant" would turn a routing bug into a data leak."""
    with pytest.raises(TenantError, match="未绑定平台上下文"):
        require_tenant()


def test_require_tenant_reads_the_bound_context(base: PlatformContext) -> None:
    with use_context(tenant_context(base, "acme")):
        assert require_tenant() == "acme"


# -- Layer one: schema / file isolation --


def test_sqlite_maps_each_tenant_to_its_own_file(base: PlatformContext) -> None:
    """SQLite has no schema concept, so the file is the isolation unit."""
    first = tenant_context(base, "acme")
    second = tenant_context(base, "globex")
    assert first.connection_uri != second.connection_uri
    assert first.connection_uri.endswith("platform-acme.sqlite3")
    assert second.connection_uri.endswith("platform-globex.sqlite3")


def test_provisioning_is_idempotent(base: PlatformContext) -> None:
    """Safe to call on every deployment."""
    first = provision_tenant(base, "acme")
    second = provision_tenant(base, "acme")
    assert first["schema"] == second["schema"] == f"{SCHEMA_PREFIX}acme"


def test_one_tenant_cannot_see_another_tenants_rows(base: PlatformContext, tmp_path: Path) -> None:
    """The property that matters. Asserted positively, not via filter strings."""
    provision_tenant(base, "acme")
    provision_tenant(base, "globex")

    register_data_source(
        tenant_context(base, "acme"),
        "ACME 的数据源",
        "sqlite",
        _business_db(tmp_path / "a.sqlite3"),
        domain="测试",
    )
    register_data_source(
        tenant_context(base, "globex"),
        "GLOBEX 的数据源",
        "sqlite",
        _business_db(tmp_path / "b.sqlite3"),
        domain="测试",
    )

    acme_names = [item["name"] for item in list_data_sources(tenant_context(base, "acme"))]
    globex_names = [item["name"] for item in list_data_sources(tenant_context(base, "globex"))]

    assert acme_names == ["ACME 的数据源"]
    assert globex_names == ["GLOBEX 的数据源"]


def test_a_tenant_starts_empty_even_when_another_has_data(base: PlatformContext, tmp_path: Path) -> None:
    provision_tenant(base, "acme")
    register_data_source(
        tenant_context(base, "acme"),
        "只属于 ACME",
        "sqlite",
        _business_db(tmp_path / "a.sqlite3"),
        domain="测试",
    )
    provision_tenant(base, "newcomer")
    assert list_data_sources(tenant_context(base, "newcomer")) == []


def test_tenants_can_be_discovered(base: PlatformContext) -> None:
    provision_tenant(base, "acme")
    provision_tenant(base, "globex")
    assert {item["tenant"] for item in list_tenants(base)} == {"acme", "globex"}


def test_statistics_report_per_tenant_counts(base: PlatformContext, tmp_path: Path) -> None:
    provision_tenant(base, "acme")
    provision_tenant(base, "globex")
    register_data_source(
        tenant_context(base, "acme"),
        "源",
        "sqlite",
        _business_db(tmp_path / "a.sqlite3"),
        domain="测试",
    )
    assert tenant_statistics(tenant_context(base, "acme"))["tables"]["data_source"] == 1
    assert tenant_statistics(tenant_context(base, "globex"))["tables"]["data_source"] == 0


def test_derived_context_carries_the_schema(base: PlatformContext) -> None:
    assert tenant_context(base, "acme").schema == f"{SCHEMA_PREFIX}acme"


def test_server_dialects_keep_the_uri_and_route_by_schema() -> None:
    """For PostgreSQL and MySQL the URI is unchanged; the schema isolates."""
    base = PlatformContext(db_type="postgresql", connection_uri="postgresql://localhost:5432/platform")
    derived = tenant_context(base, "acme")
    assert derived.connection_uri == base.connection_uri
    assert derived.schema == f"{SCHEMA_PREFIX}acme"


def test_postgres_adapter_receives_the_schema() -> None:
    """Routing must reach the adapter, not merely sit on the context."""
    context = PlatformContext(
        db_type="postgresql",
        connection_uri="postgresql://localhost:5432/platform",
        schema="tenant_acme",
    )
    assert context.adapter.schema == "tenant_acme"


def test_mysql_adapter_receives_the_schema() -> None:
    context = PlatformContext(
        db_type="mysql",
        connection_uri="mysql://root@localhost:3306/platform",
        schema="tenant_acme",
    )
    assert context.adapter.schema == "tenant_acme"


def test_single_tenant_context_has_no_schema_routing(base: PlatformContext) -> None:
    """Existing single-tenant deployments must be unaffected."""
    assert base.schema == ""


# -- Layer two: tenant_id --


def test_tenant_id_column_is_added_to_scoped_tables(base: PlatformContext) -> None:
    provision_tenant(base, "acme")
    context = tenant_context(base, "acme")
    with context.connect() as conn:
        columns = {row["name"] for row in conn.execute("pragma table_info(data_source)").fetchall()}
    assert "tenant_id" in columns


def test_platform_global_tables_are_not_tenant_scoped() -> None:
    """Blueprints are shared vocabulary; users and model config are platform-level."""
    for table in ("industry_blueprint", "platform_user", "user_session", "model_config"):
        assert table not in TENANT_SCOPED_TABLES


def test_stamp_tenant_adds_the_owner_to_a_write(base: PlatformContext) -> None:
    with use_context(tenant_context(base, "acme")):
        assert stamp_tenant({"name": "x"})["tenant_id"] == "acme"


def test_cross_tenant_row_is_detected(base: PlatformContext) -> None:
    """If schema routing ever misfires, this converts a silent read into an error."""
    with use_context(tenant_context(base, "acme")):
        with pytest.raises(TenantError, match="跨租户"):
            assert_tenant_row({"tenant_id": "globex"})


def test_same_tenant_row_passes(base: PlatformContext) -> None:
    with use_context(tenant_context(base, "acme")):
        assert_tenant_row({"tenant_id": "acme"})


def test_legacy_rows_without_a_tenant_are_accepted(base: PlatformContext) -> None:
    """An upgraded single-tenant deployment has rows that predate tenancy."""
    with use_context(tenant_context(base, "acme")):
        assert_tenant_row({"tenant_id": ""})


@pytest.mark.parametrize("row", [None, {"id": 1}])
def test_rows_without_the_column_are_accepted(base: PlatformContext, row) -> None:
    with use_context(tenant_context(base, "acme")):
        assert_tenant_row(row)


def test_scope_query_appends_a_where_clause(base: PlatformContext) -> None:
    with use_context(tenant_context(base, "acme")):
        query, params = scope_query("select * from data_source", ())
    assert "where" in query
    assert params == ("acme",)


def test_scope_query_appends_and_when_a_where_exists(base: PlatformContext) -> None:
    with use_context(tenant_context(base, "acme")):
        query, params = scope_query("select * from ontology where status = ?", ("draft",), "o")
    assert " and " in query
    assert "o.tenant_id" in query
    assert params == ("draft", "acme")


def test_scope_query_tolerates_legacy_rows(base: PlatformContext) -> None:
    """Must not hide rows written before the column existed."""
    with use_context(tenant_context(base, "acme")):
        query, _ = scope_query("select * from data_source", ())
    assert "= ''" in query


# -- Server dialects, when available --


def _server_context(env_var: str, db_type: str, database: str) -> PlatformContext | None:
    uri = os.environ.get(env_var, "")
    if not uri:
        return None
    return PlatformContext(db_type=db_type, connection_uri=f"{uri}{database}")


@pytest.mark.parametrize(
    ("env_var", "db_type", "database"),
    [
        ("ONTOLOGY_TEST_POSTGRES_URI", "postgresql", "postgres"),
        ("ONTOLOGY_TEST_MYSQL_URI", "mysql", "mysql"),
    ],
)
def test_isolation_holds_on_server_dialects(env_var, db_type, database, tmp_path: Path) -> None:
    """Skips when no server is reachable, matching the dialect test convention."""
    base = _server_context(env_var, db_type, database)
    if base is None:
        pytest.skip(f"{env_var} 未设置")
    try:
        base.connect().close()
    except Exception as error:  # pragma: no cover - environment dependent
        pytest.skip(f"{db_type} 不可用: {error}")

    provision_tenant(base, "isolation_a")
    provision_tenant(base, "isolation_b")

    register_data_source(
        tenant_context(base, "isolation_a"),
        "A 源",
        "sqlite",
        _business_db(tmp_path / "a.sqlite3"),
        domain="测试",
    )
    register_data_source(
        tenant_context(base, "isolation_b"),
        "B 源",
        "sqlite",
        _business_db(tmp_path / "b.sqlite3"),
        domain="测试",
    )

    a_names = [item["name"] for item in list_data_sources(tenant_context(base, "isolation_a"))]
    b_names = [item["name"] for item in list_data_sources(tenant_context(base, "isolation_b"))]
    assert "A 源" in a_names and "B 源" not in a_names, a_names
    assert "B 源" in b_names and "A 源" not in b_names, b_names


# -- API surface --


def test_tenant_endpoints_have_sensible_capabilities() -> None:
    """Provisioning creates schemas and tables, so it is strictly administrative."""
    from ontology_platform.access_policy import required_capability

    assert required_capability("POST", "/tenants") == "platform:admin"
    assert required_capability("GET", "/tenants") == "platform:read"
    assert required_capability("GET", "/tenants/acme/statistics") == "platform:read"


def test_listing_tenants_on_a_single_tenant_deployment_is_not_an_error(
    base: PlatformContext,
) -> None:
    """Multi-tenancy is opt-in; provisioning nothing must return an empty list."""
    assert list_tenants(base) == []
