"""Versioned migrations: the schema changes `SchemaBundle` cannot express.

`SchemaBundle` covers the two idempotent shapes -- create a table if absent, add a column
if absent -- because the catalog can answer whether the work is done. Nothing else is
safe to re-run: renaming a column, narrowing a type, backfilling a value, dropping a table
that is no longer used. The catalog cannot distinguish "not yet migrated" from "migrated,
then legitimately changed", so running such a step twice corrupts data.

ROADMAP recorded Alembic as the destination, blocked on the package split. The real
blocker was more basic: **Alembic requires SQLAlchemy**, and the kernel is dependency-free
by design -- CI verifies it on a bare install. What Alembic provides that this project
lacked is narrow (a version ledger and ordered application), and autogeneration is
unusable here anyway because the DDL is declared per dialect as strings.

The properties worth pinning down:

- **an existing deployment catches up**, including one created before migrations existed
- **a fresh install skips the backfill**, because the column ships with the right default
  and there are no rows to reclassify
- **re-running changes nothing**, which is what the ledger is for
- **a failure stops the sequence**, because applying step 7 to a database that failed
  step 5 means step 7's assumptions no longer hold
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.bootstrap import FEATURE_SCHEMAS, prepare_database
from ontology_platform.database import connect, initialize_platform_db
from ontology_platform.migrations import (
    MIGRATIONS,
    Migration,
    MigrationError,
    applied_versions,
    apply_migrations,
    pending_migrations,
    register_migrations,
)


def _legacy_database(path: Path, *, users: bool = True) -> Path:
    """A platform database as it existed before `identity_source` or the ledger.

    Hand-built rather than produced by an old release, because the property under test is
    "an existing deployment catches up" and the only honest way to check it is to start
    from a schema that genuinely lacks the column.
    """
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        create table platform_user (
            id integer primary key autoincrement,
            username text not null unique,
            display_name text not null default '',
            role_code text not null default 'analyst',
            password_hash text not null,
            password_salt text not null,
            iterations integer not null default 240000,
            status text not null default 'active',
            created_at text not null default current_timestamp,
            updated_at text not null default current_timestamp,
            last_login_at text
        );
        """
    )
    if users:
        connection.executescript(
            """
            insert into platform_user (username, password_hash, password_salt)
                values ('local.user', 'abc123', 'saltx');
            insert into platform_user (username, password_hash, password_salt, iterations)
                values ('sso.user', '', '', 0);
            """
        )
    connection.commit()
    connection.close()
    return path


# -- Declaration --


def test_a_migration_without_a_description_is_refused() -> None:
    """A migration nobody can identify from the ledger is one nobody can reason about
    during an incident."""
    with pytest.raises(MigrationError, match="必须有描述"):
        Migration(version="9999", description="")


def test_a_migration_without_a_version_is_refused() -> None:
    with pytest.raises(MigrationError, match="必须有版本号"):
        Migration(version="  ", description="something")


def test_a_duplicate_version_is_refused() -> None:
    """A plugin reusing a platform version would be silently skipped on any database that
    already ran it -- the schema change would simply never happen."""
    with pytest.raises(MigrationError, match="版本重复"):
        register_migrations([Migration(version=MIGRATIONS[0].version, description="clash")])


def test_every_platform_migration_declares_all_three_dialects() -> None:
    """A dialect missing from a migration silently does nothing on that engine.

    That is a legitimate shape for a PostgreSQL-only index, but not for a backfill: it
    would leave MySQL deployments with unmigrated data and no indication of it. So the
    platform's own migrations are required to be explicit about all three.
    """
    for migration in MIGRATIONS:
        for dialect in ("sqlite", "postgresql", "mysql"):
            assert migration.statements_for(dialect), f"迁移 {migration.version} 未声明 {dialect} 语句"


# -- Catching up an existing deployment --


def test_a_legacy_database_is_reclassified(tmp_path: Path) -> None:
    """The backfill that is not idempotent, and therefore needs the ledger.

    Accounts are classified by the only evidence available: an empty password hash means
    SSO provisioned the row, because nothing else produces one. Re-running this against a
    database where a password was legitimately removed later would relabel that account,
    which is exactly why it must run once.
    """
    database = _legacy_database(tmp_path / "legacy.sqlite3")
    initialize_platform_db(database)

    with connect(database) as conn:
        applied = prepare_database(conn)

    assert [(item["version"], item["status"]) for item in applied] == [("0001", "applied")]

    with connect(database) as conn:
        sources = {
            row["username"]: row["identity_source"]
            for row in conn.execute("select username, identity_source from platform_user").fetchall()
        }
    assert sources == {"local.user": "local", "sso.user": "sso"}


def test_re_running_applies_nothing(tmp_path: Path) -> None:
    """What the ledger exists for. Without it the backfill would run on every boot."""
    database = _legacy_database(tmp_path / "legacy.sqlite3")
    initialize_platform_db(database)
    with connect(database) as conn:
        prepare_database(conn)
        assert prepare_database(conn) == []


def test_a_database_predating_the_ledger_reads_as_nothing_applied(tmp_path: Path) -> None:
    """An absent ledger must not be an error: that is the state of every database created
    before migrations existed, and all of them have to be able to catch up."""
    database = _legacy_database(tmp_path / "legacy.sqlite3")
    with connect(database) as conn:
        assert applied_versions(conn) == set()
        assert [item.version for item in pending_migrations(conn)] == [item.version for item in MIGRATIONS]


# -- A fresh install has nothing to backfill --


def test_a_fresh_install_skips_the_backfill(tmp_path: Path) -> None:
    """The column ships defaulting to `local` and there are no rows to reclassify.

    Skipped rather than applied, and *recorded* as skipped: an unrecorded skip would be
    retried on every boot forever.
    """
    database = tmp_path / "fresh.sqlite3"
    initialize_platform_db(database)
    with connect(database) as conn:
        applied = prepare_database(conn)

    assert [(item["version"], item["status"]) for item in applied] == [("0001", "skipped")]
    with connect(database) as conn:
        assert applied_versions(conn) == {"0001"}


def test_a_table_probe_alone_would_never_skip(tmp_path: Path) -> None:
    """Why `skip_when_empty` exists rather than only `guard_table`.

    `platform_user` is created by `init_auth_schema`, which runs before migrations in the
    bootstrap sequence -- so by the time the backfill is considered, the table exists on a
    fresh install too. A table probe would report "present" and run the update against zero
    rows on every new deployment. Harmless for this migration, and the wrong mechanism: the
    next backfill might not be idempotent against an empty table.
    """
    database = tmp_path / "fresh.sqlite3"
    initialize_platform_db(database)
    with connect(database) as conn:
        from ontology_platform.schema import table_exists

        assert not table_exists(conn, "platform_user"), "认证表尚未建立"
        prepare_database(conn)
        assert table_exists(conn, "platform_user"), "引导序列应已创建该表"
        assert MIGRATIONS[0].skip_when_empty == "platform_user"


# -- Failure stops the sequence --


def test_a_failing_migration_stops_the_ones_after_it(tmp_path: Path) -> None:
    """Applying step 7 to a database that failed step 5 means step 7's assumptions about
    the schema no longer hold. Behind is recoverable; inconsistent may not be.
    """
    database = tmp_path / "fresh.sqlite3"
    initialize_platform_db(database)

    broken = Migration(
        version="t900",
        description="故意失败",
        statements={"sqlite": ["update table_that_does_not_exist set x = 1"]},
    )
    following = Migration(
        version="t901",
        description="不应被执行",
        statements={"sqlite": ["create table should_not_exist (id integer)"]},
    )
    register_migrations([broken, following])
    try:
        with connect(database) as conn:
            with pytest.raises(MigrationError, match="t900"):
                apply_migrations(conn)

        with connect(database) as conn:
            from ontology_platform.schema import table_exists

            recorded = applied_versions(conn)
            assert "t900" not in recorded, "失败的迁移不应被记录，否则永不重试"
            assert "t901" not in recorded
            assert not table_exists(conn, "should_not_exist"), "后续迁移不应执行"
    finally:
        # Registered migrations are process-global; leaving them would fail every later test.
        from ontology_platform import migrations as module

        module._PLUGIN_MIGRATIONS.clear()


# -- The single bootstrap sequence --


def test_migrations_run_after_every_feature_schema(tmp_path: Path) -> None:
    """Order is part of the contract: a backfill against a column this boot is adding must
    see the column already there."""
    from ontology_platform.migrations import init_migration_schema

    assert FEATURE_SCHEMAS[-1] is init_migration_schema, "迁移账本应在特性表之后建立"


def test_the_bootstrap_sequence_covers_every_feature_schema() -> None:
    """The list used to exist twice -- here and in the HTTP startup -- and a schema missing
    from one produces a database where a feature returns empty results rather than an
    error, which reads as a data problem long before anyone suspects a missing table.
    """
    import re

    api = (ROOT / "backend" / "ontology_platform" / "api.py").read_text(encoding="utf-8")
    cli = (ROOT / "backend" / "ontology_platform" / "cli.py").read_text(encoding="utf-8")

    assert "prepare_database" in api, "HTTP 启动应走统一的引导序列"
    assert "prepare_database" in cli, "CLI init 应走统一的引导序列"
    # And neither may keep its own list, or the two would drift again.
    for source, name in ((api, "api.py"), (cli, "cli.py")):
        stray = re.findall(r"init_\w+_schema\(conn\)", source)
        assert not stray, f"{name} 仍在自行枚举特性表: {stray}"
