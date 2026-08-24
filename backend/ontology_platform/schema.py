"""One place to declare and apply per-dialect DDL.

Technical debt items 3 and 5. Six modules -- `auth`, `agent_roles`,
`workflow_permission`, `conversations`, `knowledge_documents`, `aggregation`,
`events` -- each reached into `database` for its *private* `_sqlite_ddl` /
`_postgresql_ddl` / `_mysql_ddl` helpers, from inside a function body to dodge a
circular import, and each re-implemented the same dispatch loop.

Two problems with that, and neither is stylistic:

- **The private reach is a cycle.** `auth` importing `database._sqlite_ddl` inside a
  function works today, but at packaging time (ROADMAP stage E) a cross-package cycle
  cannot be papered over with a function-local import.
- **The duplicated loop drifted.** Every copy had to remember that MySQL has no
  `create index if not exists`, and that a failed statement on PostgreSQL aborts the
  surrounding transaction. Some copies remembered; some did not.

This module owns both concerns. It depends only on the dialect name, so it sits below
`database` in the dependency order and any module may import it at the top level.

## Why not Alembic yet

Alembic is the destination (ROADMAP stage E, migrations owned per plugin). It is not
the step to take now: it needs the package split to be decided first, because a
migration has to belong to a distribution. `SchemaBundle` is the intermediate that
removes the cycle and the duplication without pre-committing to a layout.

Stability: internal. Third parties should declare tables through their plugin's own
bundle, not call this directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

logger = logging.getLogger(__name__)

SQLITE = "sqlite"
POSTGRESQL = "postgresql"
MYSQL = "mysql"

# psycopg reports the dialect as `postgres` in some configurations; both names must
# select the same DDL or a PostgreSQL deployment would silently get SQLite types.
_DIALECT_ALIASES = {"postgres": POSTGRESQL}


def normalize_dialect(db_type: str | None) -> str:
    """Canonical dialect name, defaulting to SQLite.

    SQLite is the default because it is the zero-configuration platform database; an
    unknown dialect getting SQLite DDL is the same behaviour the previous per-module
    helpers had via `next(iter(stmt.values()))`.
    """
    name = (db_type or SQLITE).strip().lower()
    return _DIALECT_ALIASES.get(name, name)


def dialect_of(conn: Any) -> str:
    """The dialect a platform connection speaks.

    Read off the adapter rather than passed in, so a caller cannot apply MySQL DDL to
    a PostgreSQL connection by getting an argument wrong.
    """
    return normalize_dialect(getattr(getattr(conn, "_adapter", None), "db_type", SQLITE))


def statement_for(statements: Mapping[str, str], dialect: str) -> str:
    """Pick the DDL for one dialect.

    Falls back to the first declared variant when a dialect is missing, which is what
    the three private helpers did. A bundle should still declare all three: relying on
    the fallback means one backend silently gets another's column types.
    """
    canonical = normalize_dialect(dialect)
    if canonical in statements:
        return statements[canonical]
    if not statements:
        raise ValueError("DDL 声明为空")
    fallback = next(iter(statements.values()))
    logger.debug("方言 %s 缺少 DDL 声明，回退到首个变体", canonical)
    return fallback


@dataclass(frozen=True)
class ColumnAddition:
    """A column added to a table that already exists in deployed databases.

    Types are declared per dialect because `text` and `timestamp` are not portable, the
    same reason `database.ColumnMigration` exists. The catalog is probed before the DDL
    runs, so this is idempotent without depending on driver-specific error strings --
    catching the error instead would abort the surrounding transaction on PostgreSQL
    (ADR-0004).
    """

    table: str
    column: str
    sqlite_type: str
    postgresql_type: str
    mysql_type: str

    def ddl(self, dialect: str) -> str:
        column_type = {
            SQLITE: self.sqlite_type,
            POSTGRESQL: self.postgresql_type,
            MYSQL: self.mysql_type,
        }.get(normalize_dialect(dialect), self.sqlite_type)
        return f"alter table {self.table} add column {self.column} {column_type}"

    def apply(self, conn: Any, dialect: str) -> None:
        existing = _existing_columns(conn, self.table, dialect)
        if not existing:
            # The table is absent or unreadable. A fresh install already got the column
            # from the create statement, so there is nothing to migrate.
            return
        if self.column.lower() in existing:
            return
        conn.execute(self.ddl(dialect))
        if hasattr(conn, "commit"):
            conn.commit()


def _existing_columns(conn: Any, table: str, dialect: str) -> set[str]:
    """The columns a table currently has, lower-cased.

    Returns empty on failure rather than raising: a missing table is the common case
    during a first install, and it must not stop startup.
    """
    canonical = normalize_dialect(dialect)
    try:
        if canonical == SQLITE:
            return {str(row["name"]).lower() for row in conn.execute(f"pragma table_info({table})").fetchall()}
        scope = "database()" if canonical == MYSQL else "current_schema()"
        query = f"select column_name from information_schema.columns where table_name = %s and table_schema = {scope}"
        with conn.cursor() as cursor:
            cursor.execute(query, (table,))
            return {str(row[0]).lower() for row in cursor.fetchall()}
    except Exception as error:
        logger.debug("读取表 %s 的现有列失败: %s", table, error)
        return set()


@dataclass(frozen=True)
class SchemaBundle:
    """The tables and indexes one module owns.

    `tables` and `indexes` are separated because they fail differently: a
    `create table if not exists` is idempotent on all three dialects, while MySQL has
    no `create index if not exists` and raises on a re-run. Keeping them in one list
    forced every caller to sniff the statement text to decide whether an error was
    expected -- which is exactly the check that drifted between copies.

    `table_names` is declared alongside the DDL so `has_tables` can probe the catalog
    without a caller re-deriving the names. Interpolating a name constant into the DDL
    would keep them in sync too, but it makes every statement an f-string -- and a
    literal `'{}'` default then silently becomes a format placeholder. Declaring the
    names is the same guarantee without that trap.
    """

    name: str
    tables: Sequence[Mapping[str, str]] = ()
    indexes: Sequence[Mapping[str, str]] = ()
    table_names: Sequence[str] = ()
    # Columns added to a table after it shipped. `create table if not exists` does nothing
    # for an existing table, so without these a new field reaches only fresh installs --
    # and the feature then works on a developer's machine and not on an upgrade.
    columns: Sequence["ColumnAddition"] = ()

    def apply(self, conn: Any) -> None:
        """Create everything in this bundle. Idempotent -- startup runs it every boot."""
        dialect = dialect_of(conn)
        for statements in self.tables:
            conn.execute(statement_for(statements, dialect))
        for addition in self.columns:
            addition.apply(conn, dialect)
        for statements in self.indexes:
            _create_index(conn, statement_for(statements, dialect), dialect)

    def has_tables(self, conn: Any) -> bool:
        """Whether this bundle's tables are present.

        Used by features whose schema is optional: a missing table means "not
        configured", which must read as an empty result rather than an error.
        """
        if not self.table_names:
            raise ValueError(f"SchemaBundle {self.name!r} 未声明 table_names，无法探测")
        return all(table_exists(conn, name) for name in self.table_names)

    def verify_declared_names(self) -> None:
        """Check that every declared name actually appears in the DDL.

        This is what keeps the probe honest. A rename that updated the DDL but not the
        declared name would otherwise make `has_tables` report "not configured" for a
        table that exists -- and the feature would silently return empty results rather
        than fail.
        """
        ddl = " ".join(statements.get(SQLITE, "") for statements in self.tables)
        missing = [name for name in self.table_names if name not in ddl]
        if missing:
            raise ValueError(f"SchemaBundle {self.name!r} 声明的表名未出现在 DDL 中: {'、'.join(missing)}")


def _create_index(conn: Any, sql: str, dialect: str) -> None:
    """Create an index, tolerating "already exists" on MySQL only.

    Narrow on purpose. MySQL is the one dialect without `create index if not exists`,
    so it is the one place a re-run legitimately raises. Swallowing index errors on
    every dialect would hide a genuinely malformed index -- and on PostgreSQL the
    failed statement would have aborted the transaction anyway, so every later
    statement would fail regardless of what we swallowed here (ADR-0004).
    """
    if dialect != MYSQL:
        conn.execute(sql)
        return
    try:
        conn.execute(sql)
    except Exception as error:
        logger.debug("索引可能已存在，跳过: %s", error)


def apply_bundles(conn: Any, bundles: Iterable[SchemaBundle]) -> None:
    """Apply several bundles in declaration order.

    Order matters: a bundle whose tables reference another's must come after it.
    """
    for bundle in bundles:
        bundle.apply(conn)


def table_exists(conn: Any, table: str) -> bool:
    """Probe the catalog for a table.

    Catching the error instead is wrong on PostgreSQL: a failed statement aborts the
    surrounding transaction, so every later command on the same connection fails with
    InFailedSqlTransaction. This is the identical trap ADR-0004 records for schema
    migrations -- probe the catalog, never rely on the error.

    Lives here rather than in each feature module because the check had already been
    written twice with subtly different SQL, and a wrong probe reports "no table" for a
    table that exists -- which reads as "this feature is not configured" rather than as
    a failure.
    """
    dialect = dialect_of(conn)
    try:
        if dialect == SQLITE:
            row = conn.execute(
                "select name from sqlite_master where type = 'table' and name = ?",
                (table,),
            ).fetchone()
            return row is not None
        # `current_schema()` rather than a literal, so the probe follows the same
        # search path the tenant schema routing sets (ADR-0006).
        scope = "database()" if dialect == MYSQL else "current_schema()"
        query = f"select table_name from information_schema.tables where table_name = %s and table_schema = {scope}"
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            return cur.fetchone() is not None
    except Exception as error:  # pragma: no cover - defensive
        logger.debug("检查表 %s 是否存在失败: %s", table, error)
        return False
