"""SQL dialect profiles and the generic DB-API adapter.

Generality item #12. Oracle / SQL Server / 达梦 / 人大金仓 are B2B table stakes, and the
blocker was never the drivers -- it was that the five places dialects differ were written
as `if dialect == "postgresql" else ...`. A binary branch cannot express a third
database, so adding one meant editing the scanner: a fork, which is exactly what the
extension registry exists to prevent (ADR-0007).

Two things are tested here, and the second is the one that matters:

1. The profiles are internally consistent (quoting, placeholders, paging, catalog case).
2. **A database the platform has no bespoke adapter for can be onboarded by declaration
   alone**, end to end, against a real server. That is demonstrated by registering
   PostgreSQL under a *new* source type through `DriverSpec` and running the real
   onboarding path -- scan, draft, assess. If the generic path were broken, a bespoke
   PostgreSQL adapter passing would hide it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.adapters import get_adapter, supported_source_types
from ontology_platform.generic_sql_adapter import (
    BUNDLED_SPECS,
    DriverError,
    DriverSpec,
    GenericSQLAdapter,
    _MappingCursor,
    default_connect_arguments,
    describe_bundled_sql_sources,
    dsn_connect_arguments,
    register_bundled_sql_sources,
    register_sql_source,
    whole_uri,
)
from ontology_platform.sql_dialects import (
    DAMENG,
    KINGBASE,
    MYSQL,
    ORACLE,
    POSTGRESQL,
    SQLITE,
    SQLSERVER,
    DialectError,
    SqlDialect,
    columns_query,
    foreign_keys_query,
    get_dialect,
    known_dialects,
    primary_keys_query,
    register_dialect,
    resolve_dialect,
    tables_query,
)

ALL_BUILTIN = (POSTGRESQL, MYSQL, SQLITE, ORACLE, SQLSERVER, DAMENG, KINGBASE)


# -- Dialect profiles --


@pytest.mark.parametrize("dialect", ALL_BUILTIN, ids=lambda d: d.name)
def test_every_profile_quotes_and_escapes(dialect: SqlDialect) -> None:
    """An unescaped closing quote is an injection vector, not a formatting nit."""
    quoted = dialect.quote("table")
    assert quoted.startswith(dialect.quote_open)
    assert quoted.endswith(dialect.quote_close)
    hostile = dialect.quote(f"a{dialect.quote_close}b")
    # The closing character is doubled, so it cannot terminate the identifier early.
    assert hostile.count(dialect.quote_close) >= 3


@pytest.mark.parametrize("dialect", ALL_BUILTIN, ids=lambda d: d.name)
def test_every_profile_produces_a_usable_placeholder(dialect: SqlDialect) -> None:
    marker = dialect.placeholder(1)
    assert marker in ("%s", "?", ":1")
    assert len(dialect.placeholders(3)) == 3


def test_numeric_placeholders_are_positional() -> None:
    """Oracle binds by position, so the second parameter must not reuse `:1`."""
    assert ORACLE.placeholders(2) == [":1", ":2"]


@pytest.mark.parametrize("dialect", ALL_BUILTIN, ids=lambda d: d.name)
def test_every_profile_can_limit_rows(dialect: SqlDialect) -> None:
    """A hardcoded `limit n` fails on Oracle, SQL Server and 达梦.

    Column profiling swallows query errors, so an unsupported limit clause would make
    every column come back unprofiled rather than raising -- a silent degradation.
    """
    clause = dialect.limit_clause(5)
    assert "5" in clause
    assert clause.startswith(("limit", "fetch first"))


def test_offset_paging_works_in_both_styles() -> None:
    assert POSTGRESQL.limit_clause(10, 20) == "limit 10 offset 20"
    assert ORACLE.limit_clause(10, 20) == "offset 20 rows fetch first 10 rows only"


def test_negative_paging_values_are_clamped() -> None:
    """These reach SQL text, so a negative value must not become syntax."""
    assert "-" not in POSTGRESQL.limit_clause(-5, -5)


def test_catalog_case_folding_is_declared_not_guessed() -> None:
    """Oracle and 达梦 fold unquoted identifiers to upper case in the catalog.

    Getting this wrong makes a table appear to have no columns, because the lookup
    silently matches nothing -- which reads as "this table is empty" rather than as an
    error.
    """
    assert ORACLE.catalog_name("contracts") == "CONTRACTS"
    assert DAMENG.catalog_name("contracts") == "CONTRACTS"
    assert POSTGRESQL.catalog_name("contracts") == "contracts"
    assert MYSQL.catalog_name("Contracts") == "Contracts"


@pytest.mark.parametrize("dialect", ALL_BUILTIN, ids=lambda d: d.name)
def test_catalog_queries_are_scoped_to_the_current_schema(dialect: SqlDialect) -> None:
    """Unscoped catalog queries would leak another tenant's tables (ADR-0006)."""
    for query in (tables_query(dialect), columns_query(dialect), primary_keys_query(dialect)):
        assert dialect.current_schema_expression in query
    assert dialect.current_schema_expression in foreign_keys_query(dialect)


def test_the_two_foreign_key_catalog_shapes_are_both_expressible() -> None:
    """MySQL denormalises the target onto key_column_usage; the standard does not.

    Modelled as a property of the profile rather than as a dialect check, so any
    database can declare either shape.
    """
    assert "referenced_table_name" in foreign_keys_query(MYSQL)
    assert "constraint_column_usage" in foreign_keys_query(POSTGRESQL)


def test_aliases_resolve_to_the_same_profile() -> None:
    assert get_dialect("postgres") is POSTGRESQL
    assert get_dialect("mssql") is SQLSERVER
    assert get_dialect("dm8") is DAMENG


def test_an_unknown_dialect_names_what_is_available() -> None:
    with pytest.raises(DialectError, match="未知 SQL 方言"):
        get_dialect("teradata")


def test_registering_a_dialect_requires_explicit_replacement() -> None:
    """Silently redefining `mysql` would change how every existing MySQL source is
    scanned, with no record of it having happened."""
    register_dialect(SqlDialect(name="testdb", paramstyle="qmark"), replace=True)
    with pytest.raises(DialectError, match="已存在"):
        register_dialect(SqlDialect(name="testdb"))
    assert "testdb" in known_dialects()


@pytest.mark.parametrize(
    "invalid",
    [
        SqlDialect(name="bad style", paramstyle="format"),
        SqlDialect(name="badparam", paramstyle="pyformat"),
        SqlDialect(name="badlimit", row_limit_style="top_n"),
        SqlDialect(name="badquote", quote_open=""),
    ],
)
def test_an_invalid_profile_is_refused(invalid: SqlDialect) -> None:
    with pytest.raises(DialectError):
        register_dialect(invalid)


def test_resolve_accepts_a_name_or_a_profile() -> None:
    """The scanner used to take a string; both forms must work so existing call sites
    keep working while new code passes a profile."""
    assert resolve_dialect("mysql") is MYSQL
    assert resolve_dialect(MYSQL) is MYSQL


# -- The generic adapter, without a server --


def test_a_spec_needs_a_driver_module() -> None:
    with pytest.raises(DriverError, match="驱动模块"):
        DriverSpec(source_type="x", dialect=POSTGRESQL, module="").validate()


def test_a_missing_driver_reports_an_install_hint_not_an_import_error() -> None:
    """A missing driver is a configuration problem. An operator needs to know which
    package to install, not to read a traceback."""
    adapter = GenericSQLAdapter(
        DriverSpec(
            source_type="nosuchdb",
            dialect=POSTGRESQL,
            module="definitely_not_installed_driver",
            install_hint="请安装 definitely_not_installed_driver",
        )
    )
    status = adapter.test_connection("nosuchdb://localhost/db")
    assert status["reachable"] is False
    assert status["status"] == "driver_missing"
    assert "请安装" in status["message"]


def test_driver_missing_is_distinguished_from_unreachable() -> None:
    """One is fixed by installing a package, the other by fixing a network or
    credential. Collapsing them into "failed" sends people to the wrong place."""
    installed = GenericSQLAdapter(
        DriverSpec(source_type="fakepg", dialect=POSTGRESQL, module="sqlite3", connect_arguments=lambda uri: {})
    )
    # sqlite3 imports fine but `connect()` with no arguments fails, so this is the
    # unreachable case rather than the missing-driver case.
    status = installed.test_connection("fakepg://nowhere/db")
    assert status["status"] == "connection_error"


def test_the_default_uri_parser_covers_the_common_shape() -> None:
    arguments = default_connect_arguments("mydb://alice:secret@db.example:5433/analytics?sslmode=require")
    assert arguments["host"] == "db.example"
    assert arguments["port"] == 5433
    assert arguments["user"] == "alice"
    assert arguments["password"] == "secret"
    assert arguments["database"] == "analytics"
    # Query parameters pass through so a deployment can set driver options the platform
    # does not know about.
    assert arguments["sslmode"] == "require"


def test_a_driver_owning_its_connection_string_gets_it_verbatim() -> None:
    """Parsing and reassembling such a string only loses information."""
    uri = "postgresql://u:p@h:5432/db?application_name=x"
    assert dsn_connect_arguments(uri) == {"dsn": uri}


def test_oracle_arguments_build_a_service_dsn() -> None:
    """Oracle's DSN is `host:port/service_name`; `database` is not a keyword oracledb
    accepts, which is why the default parser cannot be used."""
    spec = next(item for item in BUNDLED_SPECS if item.source_type == "oracle")
    arguments = spec.connect_arguments("oracle://scott:tiger@dbhost:1521/ORCLPDB1")
    assert arguments["dsn"] == "dbhost:1521/ORCLPDB1"
    assert arguments["user"] == "scott"
    assert "database" not in arguments


def test_positional_rows_are_exposed_as_mappings() -> None:
    """The shared scanner reads rows by column name, which most drivers do not provide.

    Zipping with `cursor.description` in one place means a driver's row shape is never a
    reason to write a new adapter.
    """
    import sqlite3

    conn = sqlite3.connect(":memory:")
    conn.execute("create table t (a integer, b text)")
    conn.execute("insert into t values (1, 'x')")
    cursor = _MappingCursor(conn.cursor())
    cursor.execute("select a, b from t")
    assert cursor.fetchall() == [{"a": 1, "b": "x"}]


# -- The bundled catalogue --


def test_the_catalogue_is_declared_with_dialects_and_hints() -> None:
    """Declared rather than activated: each needs a driver the kernel does not depend on,
    and several need client libraries PyPI alone cannot provide."""
    items = {item["sourceType"]: item for item in describe_bundled_sql_sources()}
    assert {"oracle", "sqlserver", "dameng", "kingbase"} <= set(items)
    for item in items.values():
        assert item["dialect"] in known_dialects()
        assert item["installHint"], f"{item['sourceType']} 缺少安装提示"


def test_bundled_registration_reports_what_it_skipped() -> None:
    """A source type that silently did not appear would look like a platform bug rather
    than a missing driver."""
    outcome = register_bundled_sql_sources(replace=True)
    assert set(outcome) == {item.source_type for item in BUNDLED_SPECS}
    assert all(value in ("registered", "driver_missing") or value.startswith("error:") for value in outcome.values())


def test_registering_a_source_type_does_not_require_its_driver() -> None:
    """So the type appears in onboarding and the operator gets "install X" rather than
    wondering why the type is absent."""
    register_sql_source(
        DriverSpec(
            source_type="phantomdb",
            dialect=POSTGRESQL,
            module="not_installed_phantom_driver",
            install_hint="安装 phantom 驱动",
        ),
        replace=True,
    )
    assert "phantomdb" in supported_source_types()
    # Resolving the adapter must work; only using it should complain.
    adapter = get_adapter("phantomdb")
    assert adapter.source_type == "phantomdb"
    with pytest.raises(DriverError, match="phantom"):
        adapter.scan("phantomdb://host/db")


# -- End to end against a real server --


def _postgres_uri() -> str:
    return os.environ.get("ONTOLOGY_TEST_POSTGRES_URI", "postgresql://localhost:5432/")


@pytest.fixture
def declared_postgres(tmp_path):
    """PostgreSQL onboarded as a *new* source type, through `DriverSpec` alone.

    The point of routing a database we already support through the generic path: if the
    generic path were broken, the bespoke PostgreSQL adapter passing its own tests would
    hide it. Here nothing bespoke is involved -- only a declaration.
    """
    psycopg = pytest.importorskip("psycopg")
    base = _postgres_uri()
    database = "ontology_generic_ci"
    try:
        with psycopg.connect(base + "postgres", autocommit=True, connect_timeout=3) as conn:
            conn.execute(f"drop database if exists {database}")
            conn.execute(f"create database {database}")
    except Exception as error:  # pragma: no cover - environment dependent
        pytest.skip(f"PostgreSQL 不可用: {error}")

    uri = base + database
    with psycopg.connect(uri, autocommit=True) as conn:
        conn.execute(
            """
            create table customers (
                id integer primary key,
                name text not null,
                credit_status text not null
            )
            """
        )
        conn.execute(
            """
            create table contracts (
                id integer primary key,
                customer_id integer not null references customers(id),
                amount numeric not null,
                status text not null
            )
            """
        )
        conn.execute("insert into customers values (1, '甲公司', 'normal')")
        conn.execute("insert into contracts values (1, 1, 500, 'effective')")

    # A source type the platform has no bespoke adapter for.
    register_sql_source(
        DriverSpec(
            source_type="declared_pg",
            dialect=POSTGRESQL,
            module="psycopg",
            # psycopg names the connection string `conninfo`, so it goes positionally.
            connect_arguments=whole_uri,
            passes_uri_positionally=True,
            install_hint="需要 psycopg",
        ),
        replace=True,
    )
    return uri


def test_a_declared_database_scans_through_the_generic_adapter(declared_postgres) -> None:
    adapter = get_adapter("declared_pg")
    status = adapter.test_connection(declared_postgres)
    assert status["reachable"] is True, status

    tables = {table.name: table for table in adapter.scan(declared_postgres)}
    assert {"customers", "contracts"} <= set(tables)
    contracts = tables["contracts"]
    assert contracts.primary_key == "id"
    assert contracts.row_count == 1
    # Foreign key discovery is what relation semantics are inferred from, so a generic
    # adapter that scanned columns but not keys would produce a model with no relations.
    assert [(fk.column_name, fk.target_table) for fk in contracts.foreign_keys] == [("customer_id", "customers")]
    # Column profiling must survive the portable limit clause.
    status_column = next(column for column in contracts.columns if column.name == "status")
    assert status_column.profile.samples == ["effective"]


def test_a_declared_database_reaches_a_verdict(declared_postgres, tmp_path) -> None:
    """The full claim: declaration alone gets metadata scanning, ontology drafting and
    assessment -- not merely a connection."""
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.metadata import register_data_source, scan_data_source
    from ontology_platform.ontology import generate_ontology_draft
    from ontology_platform.semantic_kernel import assess_instance

    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "声明式接入的库", "declared_pg", declared_postgres, domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology_id = generate_ontology_draft(platform_db, source.id)["ontology"]["id"]

    with connect(platform_db) as conn:
        object_code = conn.execute(
            """
            select bo.code from business_object bo
            join source_table st on st.id = bo.source_table_id
            where bo.ontology_id = %s and st.table_name = 'contracts'
            """.replace("%s", "?"),
            (ontology_id,),
        ).fetchone()["code"]

    result = assess_instance(platform_db, ontology_id, object_code, "1")
    assert result["decision"]["status"] in {"approved", "review", "blocked"}
    assert result["ruleResults"], "声明式接入的数据源未产出任何规则判定"


def test_relations_are_inferred_for_a_declared_database(declared_postgres, tmp_path) -> None:
    """Relation semantics come from the scanned foreign keys, so this proves the generic
    scanner feeds the rest of the model rather than just returning tables."""
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.metadata import register_data_source, scan_data_source
    from ontology_platform.ontology import generate_ontology_draft, summarize_ontology

    platform_db = tmp_path / "platform2.sqlite3"
    initialize_platform_db(platform_db)
    source = register_data_source(platform_db, "声明式接入的库", "declared_pg", declared_postgres, domain="合同管理")
    scan_data_source(platform_db, source.id)
    ontology_id = generate_ontology_draft(platform_db, source.id)["ontology"]["id"]
    with connect(platform_db) as conn:
        detail = summarize_ontology(conn, ontology_id)
    assert detail["relations"], "未从外键推断出任何关系"
    assert all(relation["inferenceReason"] for relation in detail["relations"])
