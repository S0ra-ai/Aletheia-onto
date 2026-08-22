"""Multi-tenant isolation: separate schema plus a tenant_id column.

Implements the model fixed in [ADR-0006](../../docs/adr/0006-tenant-isolation-model.md):
a schema per tenant, **and** a `tenant_id` column on the tables that carry tenant
data. The two layers exist because their failure modes do not overlap:

- The **schema** stops a query that forgets its tenant filter -- the rows are simply
  not visible on that connection.
- The **tenant_id** turns a mis-routed connection into a visible error instead of a
  silent cross-tenant read.

Either layer alone is one mistake away from a leak. A shared-table design relies on
every single query remembering `where tenant_id = ?`, and a missed filter is
invisible in single-tenant test data -- which is exactly why that option was
rejected.

## Dialect differences

| Dialect | Isolation unit | Applied by |
|---|---|---|
| PostgreSQL | schema | `set search_path` on connect |
| MySQL | database | `use <db>` on connect |
| SQLite | file | one file per tenant |

SQLite has no schema concept, so a tenant maps to its own database file. That keeps
the development experience identical while still being genuinely isolated.

## Fail-closed

`require_tenant()` raises when a tenant cannot be established. Defaulting to "all
tenants" or "the first tenant" would turn a routing bug into a data leak, which is
the same reasoning as ADR-0002: refuse rather than guess.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from .context import DEFAULT_TENANT, PlatformContext, current_context
from .database import connect, last_insert_id

logger = logging.getLogger(__name__)

# Tenant identifiers become schema and database names, so they are restricted to
# what is safe as an SQL identifier. Validated rather than quoted because
# `set search_path` and `use` cannot take a bind parameter -- the value has to be
# interpolated, so it must be proven safe first.
TENANT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,38}$")

SCHEMA_PREFIX = "tenant_"

# Tables holding tenant-owned data. Reference and platform-global tables are
# deliberately excluded: industry_blueprint is shared vocabulary, and
# platform_user / user_session / model_config are platform-level concerns whose
# rows are not tenant data.
TENANT_SCOPED_TABLES: tuple[str, ...] = (
    "data_source",
    "ontology",
    "business_object",
    "business_rule",
    "semantic_mapping",
    "decision_record",
    "inference_result",
    "knowledge_document",
    "knowledge_entry",
    "conversation",
    "audit_log",
)


class TenantError(ValueError):
    """Raised when a tenant identifier is invalid or cannot be established."""


def validate_tenant(tenant: str) -> str:
    """Check a tenant identifier and return it normalised.

    Strict because the value is interpolated into DDL and `set search_path`; an
    unvalidated identifier there is an injection point that no amount of parameter
    binding elsewhere would cover.
    """
    normalized = (tenant or "").strip().lower()
    if not normalized:
        raise TenantError("租户标识不能为空")
    if not TENANT_PATTERN.match(normalized):
        raise TenantError(f"租户标识不合法: {tenant!r}。只允许小写字母开头，字母、数字与下划线，最长 39 字符。")
    return normalized


def schema_for(tenant: str) -> str:
    """The schema (PostgreSQL) or database (MySQL) name for a tenant.

    Prefixed so a tenant cannot collide with a system schema such as `public` or
    `information_schema`.
    """
    return f"{SCHEMA_PREFIX}{validate_tenant(tenant)}"


def require_tenant(context: Optional[PlatformContext] = None) -> str:
    """The tenant for this operation, or an error.

    Fail-closed on purpose: falling back to "any tenant" would turn a routing bug
    into a cross-tenant read, which is the failure this whole module exists to
    prevent.
    """
    resolved = context if context is not None else current_context()
    if resolved is None:
        raise TenantError("未绑定平台上下文，无法确定租户")
    return validate_tenant(resolved.tenant)


def tenant_context(base: PlatformContext, tenant: str, *, sqlite_root: Optional[Path] = None) -> PlatformContext:
    """Derive a context bound to one tenant.

    For SQLite the connection URI is rewritten to a per-tenant file, because SQLite
    has no schema to route to. For the server dialects the URI is unchanged and the
    schema carries the isolation.
    """
    validated = validate_tenant(tenant)
    schema = schema_for(validated)
    if base.db_type == "sqlite":
        current = Path(base.connection_uri)
        root = sqlite_root or current.parent
        target = root / f"{current.stem}-{validated}{current.suffix or '.sqlite3'}"
        return PlatformContext(db_type="sqlite", connection_uri=str(target), tenant=validated, schema=schema)
    return PlatformContext(
        db_type=base.db_type,
        connection_uri=base.connection_uri,
        tenant=validated,
        schema=schema,
    )


def provision_tenant(base: PlatformContext, tenant: str) -> dict[str, Any]:
    """Create a tenant's schema and its base tables.

    Idempotent: provisioning an existing tenant re-runs the schema creation, which
    is what makes it safe to call on every deployment.
    """
    context = tenant_context(base, tenant)
    if context.db_type in ("postgresql", "postgres"):
        _create_postgres_schema(base, context.schema)
    elif context.db_type == "mysql":
        _create_mysql_database(base, context.schema)
    context.initialize()
    _ensure_tenant_columns(context)
    return {
        "tenant": context.tenant,
        "schema": context.schema,
        "dbType": context.db_type,
        "connectionUri": context.describe()["connectionUri"],
        "status": "provisioned",
    }


def _create_postgres_schema(base: PlatformContext, schema: str) -> None:
    with base.connect() as conn:
        with conn.cursor() as cur:
            # Identifier already validated by schema_for(); it cannot be bound.
            cur.execute(f'create schema if not exists "{schema}"')
        conn.commit()


def _create_mysql_database(base: PlatformContext, schema: str) -> None:
    with base.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(f"create database if not exists `{schema}` character set utf8mb4")
        conn.commit()


def _ensure_tenant_columns(context: PlatformContext) -> list[str]:
    """Add the tenant_id column to tenant-scoped tables.

    The second isolation layer. Existing rows are backfilled with the context's
    tenant, so an upgrade of a single-tenant deployment lands in a consistent
    state rather than with nulls that later queries would silently skip.
    """
    applied: list[str] = []
    column_type = {
        "sqlite": "text not null default ''",
        "postgresql": "text not null default ''",
        "postgres": "text not null default ''",
        "mysql": "varchar(64) not null default ''",
    }.get(context.db_type, "text not null default ''")

    with context.connect() as conn:
        for table in TENANT_SCOPED_TABLES:
            if not _table_exists(conn, table, context.db_type):
                continue
            if _column_exists(conn, table, "tenant_id", context.db_type):
                continue
            try:
                conn.execute(f"alter table {table} add column tenant_id {column_type}")
                conn.execute(
                    f"update {table} set tenant_id = ? where tenant_id = ''",
                    (context.tenant,),
                )
                applied.append(table)
            except Exception as error:
                logger.warning("为表 %s 添加 tenant_id 失败: %s", table, error)
    return applied


def _table_exists(conn: Any, table: str, db_type: str) -> bool:
    try:
        if db_type == "sqlite":
            row = conn.execute("select name from sqlite_master where type = 'table' and name = ?", (table,)).fetchone()
            return row is not None
        query = (
            "select table_name from information_schema.tables where table_name = %s and table_schema = current_schema()"
        )
        if db_type == "mysql":
            query = (
                "select table_name from information_schema.tables where table_name = %s and table_schema = database()"
            )
        with conn.cursor() as cur:
            cur.execute(query, (table,))
            return cur.fetchone() is not None
    except Exception as error:
        logger.debug("检查表 %s 是否存在失败: %s", table, error)
        return False


def _column_exists(conn: Any, table: str, column: str, db_type: str) -> bool:
    try:
        if db_type == "sqlite":
            rows = conn.execute(f"pragma table_info({table})").fetchall()
            return any(row["name"] == column for row in rows)
        query = (
            "select column_name from information_schema.columns "
            "where table_name = %s and column_name = %s and table_schema = current_schema()"
        )
        if db_type == "mysql":
            query = (
                "select column_name from information_schema.columns "
                "where table_name = %s and column_name = %s and table_schema = database()"
            )
        with conn.cursor() as cur:
            cur.execute(query, (table, column))
            return cur.fetchone() is not None
    except Exception as error:
        logger.debug("检查列 %s.%s 失败: %s", table, column, error)
        return False


def list_tenants(base: PlatformContext) -> list[dict[str, Any]]:
    """Discover provisioned tenants by inspecting schemas or files."""
    prefix = SCHEMA_PREFIX
    found: list[str] = []
    try:
        # PostgreSQL and MySQL both expose information_schema.schemata, so one
        # branch serves both; only SQLite needs a different discovery mechanism.
        if base.db_type in ("postgresql", "postgres", "mysql"):
            with base.connect() as conn, conn.cursor() as cur:
                cur.execute(
                    "select schema_name from information_schema.schemata where schema_name like %s",
                    (f"{prefix}%",),
                )
                found = [_row_first(row) for row in cur.fetchall()]
        else:
            current = Path(base.connection_uri)
            pattern = f"{current.stem}-*{current.suffix or '.sqlite3'}"
            found = [f"{prefix}{path.stem[len(current.stem) + 1 :]}" for path in sorted(current.parent.glob(pattern))]
    except Exception as error:
        logger.warning("枚举租户失败: %s", error)
        return []
    return [{"tenant": name[len(prefix) :], "schema": name} for name in sorted(set(found)) if name.startswith(prefix)]


def _row_first(row: Any) -> str:
    if isinstance(row, dict):
        return str(next(iter(row.values())))
    return str(row[0])


def scope_query(
    query: str, params: Iterable[Any], table_alias: str = "", *, tenant: str = ""
) -> tuple[str, tuple[Any, ...]]:
    """Append a tenant predicate to a query.

    Provided for callers that read tenant-scoped tables directly. The schema
    already isolates them; this adds the second layer, so a mis-routed connection
    returns nothing instead of another tenant's rows.
    """
    resolved = validate_tenant(tenant or require_tenant())
    column = f"{table_alias}.tenant_id" if table_alias else "tenant_id"
    separator = " and " if re.search(r"\bwhere\b", query, re.IGNORECASE) else " where "
    return f"{query}{separator}({column} = ? or {column} = '')", (*tuple(params), resolved)


def assert_tenant_row(row: Any, *, tenant: str = "") -> None:
    """Verify a fetched row belongs to the expected tenant.

    The second layer's detection half. If schema routing ever sends a connection to
    the wrong place, this converts a silent cross-tenant read into an exception at
    the point of use.
    """
    if row is None:
        return
    expected = validate_tenant(tenant or require_tenant())
    try:
        actual = row["tenant_id"]
    except (KeyError, IndexError, TypeError):
        return
    # An empty value means the row predates tenancy, which is legitimate in an
    # upgraded single-tenant deployment.
    if actual and str(actual) != expected:
        raise TenantError(f"检测到跨租户数据访问：期望 {expected}，实际 {actual}。已阻止该操作。")


def stamp_tenant(values: dict[str, Any], *, tenant: str = "") -> dict[str, Any]:
    """Add the tenant to a row about to be written."""
    resolved = validate_tenant(tenant or require_tenant())
    return {**values, "tenant_id": resolved}


def tenant_statistics(context: PlatformContext) -> dict[str, Any]:
    """Row counts per tenant-scoped table, for verifying isolation."""
    counts: dict[str, int] = {}
    with context.connect() as conn:
        for table in TENANT_SCOPED_TABLES:
            if not _table_exists(conn, table, context.db_type):
                continue
            try:
                row = conn.execute(f"select count(*) as c from {table}").fetchone()
                counts[table] = int(row["c"] if row else 0)
            except Exception as error:
                logger.debug("统计表 %s 失败: %s", table, error)
    return {
        "tenant": context.tenant,
        "schema": context.schema,
        "tables": counts,
        "totalRows": sum(counts.values()),
    }


__all__ = [
    "DEFAULT_TENANT",
    "TENANT_SCOPED_TABLES",
    "TenantError",
    "assert_tenant_row",
    "connect",
    "last_insert_id",
    "list_tenants",
    "provision_tenant",
    "require_tenant",
    "schema_for",
    "scope_query",
    "stamp_tenant",
    "tenant_context",
    "tenant_statistics",
    "validate_tenant",
]
