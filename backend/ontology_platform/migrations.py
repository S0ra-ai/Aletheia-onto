"""Versioned schema migrations: the changes `SchemaBundle` cannot express.

`SchemaBundle` handles the two shapes that are idempotent by construction: create a table
if absent, add a column if absent. Both are safe to re-run because the catalog says
whether the work is already done.

Everything else is not. Renaming a column, narrowing a type, backfilling a value,
dropping a table that is no longer used, splitting one column into two -- none of those
can be derived from the catalog, because the catalog cannot tell "already migrated" from
"never had this shape". Running such a step twice corrupts data; skipping it leaves a
database the code no longer matches.

So this module records **which steps have run**, in the database itself.

## Why not Alembic

ROADMAP named Alembic as the destination and recorded the blocker as "a migration has to
belong to a distribution, so this waits for the package split". That reasoning was
incomplete, and the real blocker is more basic: **Alembic requires SQLAlchemy**, and the
kernel is dependency-free by design (`pyproject` asserts it, CI verifies it on a bare
install). Adopting Alembic would mean the ontology, rule engine and decision records
could no longer be embedded in someone else's application without dragging in an ORM.

What Alembic actually provides that this project lacks is narrow: a version ledger and
ordered application. Autogeneration is unusable here anyway -- the DDL is declared per
dialect as strings rather than as model metadata, so there is nothing to diff against.

This is therefore not a stopgap awaiting Alembic. It is the mechanism, sized to what the
problem needs: 150 lines, no dependencies, and the same three dialects the rest of the
platform supports.

## Every step declares its own dialects

No portable DDL abstraction. `alter table ... alter column` differs across all three
engines, and SQLite cannot alter a column at all -- the accepted approach there is
create-copy-drop-rename. A layer pretending otherwise would generate SQL that works on
the dialect it was tested against, which is how a migration corrupts one deployment and
not another.

Declaring per dialect makes the difference visible in review, where it can be checked.

## Failure stops the sequence

A migration that raises is not recorded, and no later migration runs. The alternative --
continue and report at the end -- would apply step 7 to a database that failed step 5,
and step 7's assumptions about the schema no longer hold. Stopping leaves a database that
is behind, which is recoverable; continuing leaves one that is inconsistent, which may
not be.

Stability: internal. Third-party plugins declare their own migrations through
`register_migrations`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .schema import SchemaBundle, dialect_of, statement_for, table_exists

logger = logging.getLogger(__name__)

__all__ = [
    "MIGRATIONS",
    "SCHEMA",
    "Migration",
    "MigrationError",
    "applied_versions",
    "apply_migrations",
    "init_migration_schema",
    "pending_migrations",
    "register_migrations",
]

SCHEMA = SchemaBundle(
    name="migrations",
    tables=[
        {
            "sqlite": (
                "create table if not exists schema_migration ("
                "version text primary key,"
                " description text not null default '',"
                " applied_at text not null default current_timestamp)"
            ),
            "postgresql": (
                "create table if not exists schema_migration ("
                "version text primary key,"
                " description text not null default '',"
                " applied_at timestamp not null default current_timestamp)"
            ),
            "mysql": (
                "create table if not exists schema_migration ("
                "version varchar(64) primary key,"
                " description text not null,"
                " applied_at datetime not null default current_timestamp)"
            ),
        }
    ],
    table_names=["schema_migration"],
)


class MigrationError(RuntimeError):
    """Raised when a migration fails, naming the version that stopped the sequence."""


@dataclass(frozen=True)
class Migration:
    """One irreversible schema change, applied at most once per database.

    `version` is the identity recorded in `schema_migration`, so it must never be reused
    or reordered: a database that already ran `0003` will skip any future migration that
    reuses that version, whatever it does.

    `statements` is keyed by dialect. A dialect absent from the mapping means "no work on
    this engine" rather than an error -- a PostgreSQL-only index has nothing to do on
    SQLite, and forcing an empty entry would make every migration list three keys to say
    one thing.

    `guard_table` skips the migration when the table is absent -- a plugin's migration has
    nothing to do on a deployment that never installed that plugin.

    `skip_when_empty` skips it when the named table has no rows. That is what makes a
    backfill safe on a *fresh* install: the column ships with the right default and there
    are no rows to reclassify, so running the update would be work with no subject. Checked
    rather than assumed, because "the table exists" is true on a fresh install too -- the
    base DDL creates it -- so a table probe alone would never skip anything.
    """

    version: str
    description: str
    statements: Mapping[str, Sequence[str]] = field(default_factory=dict)
    guard_table: str = ""
    skip_when_empty: str = ""

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise MigrationError("迁移必须有版本号")
        if not self.description.strip():
            # A migration nobody can identify from the ledger is a migration nobody can
            # reason about during an incident.
            raise MigrationError(f"迁移 {self.version} 必须有描述")

    def statements_for(self, dialect: str) -> tuple[str, ...]:
        return tuple(self.statements.get(dialect, ()))


# The platform's own migrations, in application order.
MIGRATIONS: list[Migration] = [
    Migration(
        version="0001",
        description="回填 platform_user.identity_source：把「无口令即 SSO」的约定变成声明",
        # SSO provisioning writes `password_hash = ''` to mean "this account has no
        # password", and `verify_password` returns False on an empty hash, so a password
        # login against an SSO account fails. That works, and it works *by coincidence* --
        # the protection is a side effect of one function's guard clause rather than a
        # property of the record.
        #
        # The column makes it a declaration. This is exactly the shape `SchemaBundle`
        # cannot express: the column addition is idempotent, but **the backfill is not**.
        # Re-running it would relabel any account whose password was legitimately removed
        # later, and the catalog cannot distinguish "not yet backfilled" from "backfilled,
        # then changed".
        #
        # Existing rows are classified by the only evidence available: an empty hash means
        # the account was provisioned by SSO, because nothing else produces one.
        statements={
            "sqlite": [
                "update platform_user set identity_source = 'sso' where (password_hash is null or password_hash = '')",
                "update platform_user set identity_source = 'local'"
                " where password_hash is not null and password_hash <> ''",
            ],
            "postgresql": [
                "update platform_user set identity_source = 'sso' where (password_hash is null or password_hash = '')",
                "update platform_user set identity_source = 'local'"
                " where password_hash is not null and password_hash <> ''",
            ],
            "mysql": [
                "update platform_user set identity_source = 'sso' where (password_hash is null or password_hash = '')",
                "update platform_user set identity_source = 'local'"
                " where password_hash is not null and password_hash <> ''",
            ],
        },
        guard_table="platform_user",
        # Skipped on a fresh install: the column ships defaulting to `local` and there are
        # no rows to reclassify. A table probe alone would never skip, because the base DDL
        # creates `platform_user` on every install.
        skip_when_empty="platform_user",
    ),
]

_PLUGIN_MIGRATIONS: list[Migration] = []


def register_migrations(migrations: Sequence[Migration]) -> None:
    """Add a plugin's migrations to the sequence.

    Appended after the platform's own, because a plugin's schema depends on the platform's
    and not the reverse. Versions must be unique across everything registered: a plugin
    reusing a platform version would be silently skipped on any database that ran it.
    """
    known = {migration.version for migration in (*MIGRATIONS, *_PLUGIN_MIGRATIONS)}
    for migration in migrations:
        if migration.version in known:
            raise MigrationError(f"迁移版本重复: {migration.version}")
        known.add(migration.version)
        _PLUGIN_MIGRATIONS.append(migration)


def _all_migrations() -> tuple[Migration, ...]:
    return (*MIGRATIONS, *_PLUGIN_MIGRATIONS)


def init_migration_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


def applied_versions(conn: Any) -> set[str]:
    """Versions this database has already run.

    An absent ledger reads as "nothing applied" rather than as an error: that is exactly
    the state of a database created before migrations existed, and every such database
    must be able to catch up.
    """
    if not table_exists(conn, "schema_migration"):
        return set()
    rows = conn.execute("select version from schema_migration").fetchall()
    return {row["version"] if hasattr(row, "keys") else row[0] for row in rows}


def pending_migrations(conn: Any) -> list[Migration]:
    applied = applied_versions(conn)
    return [migration for migration in _all_migrations() if migration.version not in applied]


def apply_migrations(conn: Any) -> list[dict[str, Any]]:
    """Run every unapplied migration, in order, stopping at the first failure.

    Each migration is recorded in the same transaction as its own statements where the
    dialect allows it, so a crash between "changed the schema" and "recorded that we did"
    cannot happen silently. On a crash *before* the record, the migration is retried --
    which is why a migration should be written to tolerate a partial previous attempt
    wherever the dialect cannot make it atomic.
    """
    init_migration_schema(conn)
    dialect = dialect_of(conn)
    results: list[dict[str, Any]] = []

    for migration in pending_migrations(conn):
        statements = migration.statements_for(dialect)
        if migration.guard_table and not table_exists(conn, migration.guard_table):
            # The feature owning this table is not installed. Recorded so it is not retried
            # on every boot forever.
            _record(conn, migration, dialect, skipped=True)
            results.append({"version": migration.version, "status": "skipped", "reason": "表不存在"})
            continue
        if migration.skip_when_empty and _is_empty(conn, migration.skip_when_empty):
            # Fresh install: nothing to backfill, because the column shipped with the
            # correct default and there are no rows.
            _record(conn, migration, dialect, skipped=True)
            results.append({"version": migration.version, "status": "skipped", "reason": "无数据需回填"})
            continue
        if not statements:
            _record(conn, migration, dialect, skipped=True)
            results.append({"version": migration.version, "status": "skipped", "reason": f"{dialect} 无需变更"})
            continue

        try:
            for statement in statements:
                _execute(conn, statement, dialect)
            _record(conn, migration, dialect)
        except Exception as error:
            # Not recorded, and the sequence stops: applying step 7 to a database that
            # failed step 5 means step 7's assumptions about the schema no longer hold.
            logger.error("迁移 %s 失败，已停止后续迁移: %s", migration.version, error)
            raise MigrationError(
                f"迁移 {migration.version}（{migration.description}）失败，后续迁移未执行: {error}"
            ) from error

        results.append({"version": migration.version, "status": "applied", "description": migration.description})

    return results


def _execute(conn: Any, statement: str, dialect: str) -> None:
    if dialect == "sqlite":
        conn.execute(statement)
    else:
        with conn.cursor() as cursor:
            cursor.execute(statement)


def _is_empty(conn: Any, table: str) -> bool:
    """Whether a table has no rows.

    A table that cannot be read counts as empty: the alternative is failing a migration
    because of a probe, which turns a skippable step into a stopped upgrade.
    """
    if not table_exists(conn, table):
        return True
    try:
        row = conn.execute(f"select count(*) as total from {table}").fetchone()
    except Exception as error:  # pragma: no cover - driver-specific
        logger.debug("迁移探测表 %s 行数失败，按空表处理: %s", table, error)
        return True
    if row is None:
        return True
    total = row["total"] if hasattr(row, "keys") else row[0]
    return int(total) == 0


def _record(conn: Any, migration: Migration, dialect: str, *, skipped: bool = False) -> None:
    description = migration.description + ("（跳过）" if skipped else "")
    insert = statement_for(
        {
            "sqlite": "insert into schema_migration (version, description) values (?, ?)",
            "postgresql": "insert into schema_migration (version, description) values (%s, %s)",
            "mysql": "insert into schema_migration (version, description) values (%s, %s)",
        },
        dialect,
    )
    if dialect == "sqlite":
        conn.execute(insert, (migration.version, description))
    else:
        with conn.cursor() as cursor:
            cursor.execute(insert, (migration.version, description))
    if hasattr(conn, "commit"):
        conn.commit()
