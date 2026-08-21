"""Platform database durability and dialect tests.

The platform can store its own control-plane data in SQLite, MySQL or
PostgreSQL. Each driver has different transaction and SQL semantics, so these
tests exercise the write path on every engine that is reachable locally.
MySQL and PostgreSQL tests skip automatically when no server is available.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Iterator

import ontology_platform.database as database_module
import pytest
from ontology_platform.database import (
    COLUMN_MIGRATIONS,
    SCHEMA_DEFINITIONS,
    _adapt_sql,
    _apply_column_migrations,
    connect,
    initialize_platform_db,
)
from ontology_platform.workflow_permission import SCHEMA_SQL, init_workflow_and_permission_schema

# -- Dialect translation (no server required) --


def test_upsert_is_translated_to_mysql_on_duplicate_key() -> None:
    sql = """
        insert into data_source (name, domain)
        values (?, ?)
        on conflict(name) do update set
            domain = excluded.domain
    """
    adapted = _adapt_sql(sql, "mysql")
    assert "on duplicate key update" in adapted
    assert "on conflict" not in adapted
    assert "values(domain)" in adapted
    assert "excluded." not in adapted
    assert "?" not in adapted


def test_upsert_is_preserved_for_postgresql_and_sqlite() -> None:
    sql = "insert into t (a) values (?) on conflict(a) do update set a = excluded.a"
    postgres = _adapt_sql(sql, "postgresql")
    assert "on conflict" in postgres
    assert "excluded.a" in postgres
    assert "%s" in postgres and "?" not in postgres
    assert _adapt_sql(sql, "sqlite") == sql


def test_mysql_ddl_avoids_literal_defaults_on_text_columns() -> None:
    """MySQL rejects `text not null default ''` but accepts `default ('')`."""
    offenders = []
    for definitions in (SCHEMA_DEFINITIONS, SCHEMA_SQL):
        for statement in definitions:
            mysql_ddl = statement.get("mysql", "")
            for fragment in mysql_ddl.split(","):
                normalized = " ".join(fragment.split()).lower()
                if " text " in f" {normalized} " and "default '" in normalized:
                    offenders.append(normalized.strip())
    assert offenders == []


# -- SQLite durability --


def test_sqlite_enables_wal_and_busy_timeout(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        assert conn.execute("pragma journal_mode").fetchone()[0].lower() == "wal"
        assert int(conn.execute("pragma busy_timeout").fetchone()[0]) > 0


def test_platform_connection_rolls_back_on_error(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with pytest.raises(RuntimeError):
        with connect(platform_db) as conn:
            conn.execute(
                "insert into data_source (name, source_type, connection_uri) values (?, ?, ?)",
                ("rolled-back", "sqlite", str(tmp_path / "x.sqlite3")),
            )
            raise RuntimeError("boom")
    with connect(platform_db) as conn:
        total = conn.execute("select count(*) as total from data_source").fetchone()["total"]
    assert total == 0


def test_column_migrations_are_idempotent_and_catalog_driven(tmp_path: Path) -> None:
    platform_db = tmp_path / "platform.sqlite3"
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        # Fresh schema already has every column, so nothing should be applied.
        assert _apply_column_migrations(conn.raw(), "sqlite") == []

    # Simulate an older deployment that predates a column.
    with connect(platform_db) as conn:
        conn.execute("drop table business_rule")
        conn.execute(
            """
            create table business_rule (
                id integer primary key autoincrement,
                ontology_id integer not null references ontology(id),
                code text not null,
                name text not null,
                rule_type text not null,
                scope_object_code text not null,
                expression text not null,
                severity text not null,
                natural_language text not null,
                status text not null default 'published',
                unique(ontology_id, code)
            )
            """
        )
    initialize_platform_db(platform_db)
    with connect(platform_db) as conn:
        columns = {row["name"] for row in conn.execute("pragma table_info(business_rule)").fetchall()}
    expected = {m.column for m in COLUMN_MIGRATIONS if m.table == "business_rule"}
    assert expected.issubset(columns)


# -- Cross-engine write path --


def _mysql_dsn() -> str:
    return os.environ.get("ONTOLOGY_TEST_MYSQL_URI", "mysql://root@127.0.0.1:3306/")


def _postgres_dsn() -> str:
    return os.environ.get("ONTOLOGY_TEST_POSTGRES_URI", "postgresql://localhost:5432/")


def _reset_platform_module() -> None:
    database_module._platform_adapter = None
    database_module._platform_db_type = "sqlite"
    database_module._platform_db_uri = str(database_module.DEFAULT_PLATFORM_DB)


@pytest.fixture
def mysql_platform_db() -> Iterator[str]:
    pymysql = pytest.importorskip("pymysql")
    base = _mysql_dsn().rstrip("/")
    options = database_module._parse_mysql_uri(base + "/mysql")
    options.pop("database")
    database = f"ontology_test_{uuid.uuid4().hex[:10]}"
    try:
        conn = pymysql.connect(connect_timeout=3, **options)
    except Exception as error:  # pragma: no cover - depends on local services
        pytest.skip(f"MySQL 不可用: {error}")
    try:
        with conn.cursor() as cur:
            cur.execute(f"create database {database} character set utf8mb4 collate utf8mb4_unicode_ci")
        conn.commit()
        yield f"{base}/{database}"
    finally:
        try:
            with conn.cursor() as cur:
                cur.execute(f"drop database if exists {database}")
            conn.commit()
        finally:
            conn.close()
        _reset_platform_module()


@pytest.fixture
def postgres_platform_db() -> Iterator[str]:
    psycopg = pytest.importorskip("psycopg")
    base = _postgres_dsn().rstrip("/")
    database = f"ontology_test_{uuid.uuid4().hex[:10]}"
    try:
        admin = psycopg.connect(f"{base}/postgres", connect_timeout=3, autocommit=True)
    except Exception as error:  # pragma: no cover - depends on local services
        pytest.skip(f"PostgreSQL 不可用: {error}")
    try:
        admin.execute(f"create database {database}")
        yield f"{base}/{database}"
    finally:
        try:
            admin.execute(f"drop database if exists {database} with (force)")
        finally:
            admin.close()
        _reset_platform_module()


def _run_control_plane_flow(tmp_path: Path) -> dict[str, Any]:
    """Register, scan, model, publish and assess against the configured platform DB."""
    initialize_platform_db()
    with connect() as conn:
        init_workflow_and_permission_schema(conn)

    from ontology_platform.governance import (
        bulk_review_semantic_mappings,
        list_semantic_mappings,
        publish_ontology,
    )
    from ontology_platform.metadata import register_data_source, scan_data_source
    from ontology_platform.ontology import generate_ontology_draft
    from ontology_platform.sample_data import create_contract_sample_db
    from ontology_platform.semantic_kernel import assess_instance

    legacy_db = tmp_path / "legacy_contracts.sqlite3"
    create_contract_sample_db(legacy_db)
    source = register_data_source("", "合同管理样例系统", "sqlite", str(legacy_db), domain="合同管理")
    scan = scan_data_source("", source.id)
    ontology = generate_ontology_draft("", source.id)
    mappings = list_semantic_mappings("", ontology["id"])
    bulk_review_semantic_mappings("", ontology["id"], "confirmed", "业务专家", "批量确认")
    published = publish_ontology("", ontology["id"], "架构师")
    assessment = assess_instance("", ontology["id"], "contract", "1")
    return {
        "tables": len(scan["tables"]),
        "objects": len(ontology["objects"]),
        "mappings": len(mappings["items"]),
        "published": published["status"],
        "decision": assessment["decision"]["status"],
        "rules": len(assessment["ruleResults"]),
        "sourceId": source.id,
    }


def _assert_control_plane_flow(result: dict[str, Any]) -> None:
    assert result["tables"] == 4
    assert result["objects"] == 4
    assert result["mappings"] > 0
    assert result["published"] == "published"
    assert result["decision"] in {"approved", "review", "blocked"}
    assert result["rules"] > 0


def test_mysql_platform_database_persists_control_plane_writes(tmp_path: Path, mysql_platform_db: str) -> None:
    database_module.configure_platform_db("mysql", mysql_platform_db)
    result = _run_control_plane_flow(tmp_path)
    _assert_control_plane_flow(result)

    # A brand new connection must still see the data: pymysql does not commit
    # on context-manager exit, so this is the regression guard for lost writes.
    with connect() as conn:
        rows = conn.execute("select name from data_source").fetchall()
    assert [row["name"] for row in rows] == ["合同管理样例系统"]

    initialize_platform_db()
    with connect() as conn:
        total = conn.execute("select count(*) as total from data_source").fetchone()["total"]
    assert total == 1


def test_postgresql_platform_database_creates_schema_and_persists_writes(
    tmp_path: Path, postgres_platform_db: str
) -> None:
    database_module.configure_platform_db("postgresql", postgres_platform_db)
    initialize_platform_db()

    # Postgres aborts a transaction on the first failed statement; if schema
    # init and migrations share one transaction, no table survives.
    with connect() as conn:
        table_count = conn.execute(
            "select count(*) as total from information_schema.tables where table_schema = current_schema()"
        ).fetchone()["total"]
    assert table_count >= len(SCHEMA_DEFINITIONS)

    result = _run_control_plane_flow(tmp_path)
    _assert_control_plane_flow(result)

    with connect() as conn:
        rows = conn.execute("select name from data_source").fetchall()
    assert [row["name"] for row in rows] == ["合同管理样例系统"]

    initialize_platform_db()
    with connect() as conn:
        total = conn.execute("select count(*) as total from data_source").fetchone()["total"]
    assert total == 1


def _exercise_auth_lifecycle() -> None:
    """Create a user, log in, resolve the token, then revoke it."""
    from ontology_platform.auth import (
        AuthenticationError,
        create_user,
        init_auth_schema,
        login,
        logout,
        resolve_principal,
    )

    initialize_platform_db()
    with connect() as conn:
        init_auth_schema(conn)

    create_user("", "bob", "bob-password-1", "operator", "鲍勃")
    session = login("", "bob", "bob-password-1")
    principal = resolve_principal("", session["token"])
    assert principal.username == "bob"
    assert principal.role_code == "operator"

    logout("", session["token"])
    with pytest.raises(AuthenticationError):
        resolve_principal("", session["token"])


def test_auth_schema_and_sessions_work_on_mysql(mysql_platform_db: str) -> None:
    database_module.configure_platform_db("mysql", mysql_platform_db)
    _exercise_auth_lifecycle()


def test_auth_schema_and_sessions_work_on_postgresql(postgres_platform_db: str) -> None:
    database_module.configure_platform_db("postgresql", postgres_platform_db)
    _exercise_auth_lifecycle()
