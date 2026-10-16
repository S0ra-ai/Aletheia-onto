"""Tenant quotas: a ceiling a tenant cannot raise for itself.

ROADMAP stage B's last open item. Isolation was done -- schema routing plus a
`tenant_id` column, with cross-tenant access blocked -- but nothing limited how much
one tenant could consume. On a shared deployment that is not a billing question; it is
an availability one. A single tenant ingesting an unbounded document set fills the
platform database, and the tenant that then cannot write is a *different* tenant, who
has no way to discover why.

## Quotas live in the base database, never in the tenant's own

This is the design's load-bearing decision. A quota stored in the tenant's schema is a
quota the tenant can edit: the same connection that writes their data would reach the
row that limits it. Storing limits in the base database means raising a limit requires
platform-level access, which is what makes the limit mean anything.

The consequence is that quota checks read from a different connection than the write
they gate. That cost is accepted deliberately -- the alternative is a limit enforced by
asking the limited party to respect it.

## Checked before the write, and refused rather than truncated

A quota discovered *after* a write has to undo it, and undoing a partially ingested
document leaves the tenant unsure what actually landed. So the check runs first, and
exceeding it raises.

Refusal names the limit, the current usage, and what to do -- because "quota exceeded"
with no numbers is indistinguishable from a bug, and the tenant's next action is to
retry the same request.

## An unset quota is unlimited, not zero

Deliberate, and the direction matters. A default of zero would make every existing
deployment stop accepting writes the moment this module ships -- a silent outage caused
by adding a feature nobody opted into. Unlimited-by-default means quotas apply exactly
where someone declared them.

That is the one place this module is not fail-closed, and the reason is that the failure
being prevented is resource exhaustion rather than unauthorised access. Refusing writes
for every tenant that has no declared quota does not protect anyone from anything.

Stability: experimental (ADR-0007).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .context import PlatformContext
from .schema import SchemaBundle
from .tenancy import TENANT_SCOPED_TABLES, TenantError, tenant_context, validate_tenant

logger = logging.getLogger(__name__)

__all__ = [
    "QUOTA_RESOURCES",
    "SCHEMA",
    "QuotaExceeded",
    "check_quota",
    "describe_quota_resources",
    "init_quota_schema",
    "quota_usage",
    "set_tenant_quota",
    "tenant_quotas",
    "verify_resources_are_tenant_scoped",
]

# What can be limited. Each maps to a tenant-scoped table, so usage is countable without
# maintaining a separate counter -- a counter would drift from the rows it counts, and a
# drifted counter either blocks a tenant under their limit or lets one past it.
QUOTA_RESOURCES: dict[str, tuple[str, str]] = {
    "data_sources": ("data_source", "接入的传统业务系统数量"),
    "ontologies": ("ontology", "本体数量（含各版本）"),
    "business_rules": ("business_rule", "业务规则数量"),
    "knowledge_documents": ("knowledge_document", "知识文档数量"),
    "knowledge_entries": ("knowledge_entry", "知识条目数量（切分后的条款）"),
    "conversations": ("conversation", "会话数量"),
    "decision_records": ("decision_record", "判定留痕数量"),
}

SCHEMA = SchemaBundle(
    name="quotas",
    tables=[
        {
            "sqlite": (
                "create table if not exists tenant_quota ("
                "id integer primary key autoincrement,"
                " tenant text not null,"
                " resource text not null,"
                " limit_value integer not null,"
                " note text not null default '',"
                " unique(tenant, resource))"
            ),
            "postgresql": (
                "create table if not exists tenant_quota ("
                "id serial primary key,"
                " tenant text not null,"
                " resource text not null,"
                " limit_value integer not null,"
                " note text not null default '',"
                " unique(tenant, resource))"
            ),
            "mysql": (
                "create table if not exists tenant_quota ("
                "id integer primary key auto_increment,"
                " tenant varchar(64) not null,"
                " resource varchar(64) not null,"
                " limit_value integer not null,"
                " note text not null,"
                " unique(tenant, resource))"
            ),
        }
    ],
    table_names=["tenant_quota"],
)


class QuotaExceeded(TenantError):
    """Raised when a write would take a tenant past a declared limit.

    A subclass of `TenantError` so a caller that already handles tenant problems handles
    this one, while a caller that wants to report the numbers can catch it specifically.
    """

    def __init__(self, tenant: str, resource: str, limit: int, current: int, requested: int):
        self.tenant = tenant
        self.resource = resource
        self.limit = limit
        self.current = current
        self.requested = requested
        description = QUOTA_RESOURCES.get(resource, ("", resource))[1]
        super().__init__(
            f"租户 {tenant} 的「{description}」配额不足："
            f"上限 {limit}，当前 {current}，本次请求 {requested}。"
            f"请减少本次写入量，或由平台管理员调整配额。"
        )


def init_quota_schema(conn: Any) -> None:
    SCHEMA.apply(conn)


def describe_quota_resources() -> list[dict[str, str]]:
    """Every limitable resource with the table it counts.

    The table is exposed because an operator setting a limit needs to know what is being
    counted: "ontologies" counts versions too, and someone who assumed otherwise would
    set a limit that a normal `derive` workflow exhausts.
    """
    return [
        {"resource": resource, "table": table, "description": description}
        for resource, (table, description) in sorted(QUOTA_RESOURCES.items())
    ]


def set_tenant_quota(
    base: PlatformContext,
    tenant: str,
    resource: str,
    limit: int,
    *,
    note: str = "",
) -> dict[str, Any]:
    """Declare a limit, in the **base** database.

    `base` rather than a tenant context, and that is the point: a quota written through
    the tenant's own connection would be a quota the tenant can rewrite.
    """
    tenant = validate_tenant(tenant)
    if resource not in QUOTA_RESOURCES:
        raise TenantError(f"未知配额资源 {resource}，支持: {'、'.join(sorted(QUOTA_RESOURCES))}")
    if limit < 0:
        # A negative limit has no meaning, and stored it would read as "unlimited" or
        # "blocked" depending on which comparison ran first.
        raise TenantError(f"配额上限不能为负数: {limit}")

    with base.connect() as conn:
        init_quota_schema(conn)
        conn.execute(
            "delete from tenant_quota where tenant = ? and resource = ?",
            (tenant, resource),
        )
        conn.execute(
            "insert into tenant_quota (tenant, resource, limit_value, note) values (?, ?, ?, ?)",
            (tenant, resource, limit, note),
        )

    return {"tenant": tenant, "resource": resource, "limit": limit, "note": note}


def tenant_quotas(base: PlatformContext, tenant: str) -> dict[str, int]:
    """Declared limits for one tenant. Absent means unlimited, not zero."""
    tenant = validate_tenant(tenant)
    with base.connect() as conn:
        if not SCHEMA.has_tables(conn):
            return {}
        rows = conn.execute(
            "select resource, limit_value from tenant_quota where tenant = ?",
            (tenant,),
        ).fetchall()
    return {row["resource"]: int(row["limit_value"]) for row in rows}


def quota_usage(base: PlatformContext, tenant: str) -> dict[str, Any]:
    """Current usage against declared limits, for one tenant.

    Counted from the rows themselves rather than from a stored counter. A counter drifts from
    the rows it counts, and a drifted counter either blocks a tenant who is under their limit
    or lets one past it -- both are worse than a count that costs a query.

    Counted from the same store `check_quota` counts, which is the store the application
    writes to. These two disagreed once: the report read the tenant's own store and showed
    「当前 0」 while the check counted ten rows in the platform store, so an administrator
    sizing a limit was reading a number that described a database nobody was writing to.
    """
    tenant = validate_tenant(tenant)
    limits = tenant_quotas(base, tenant)

    usage: dict[str, Any] = {}
    for resource, (table, description) in sorted(QUOTA_RESOURCES.items()):
        current = _tenant_rows(base, tenant, table)
        limit = limits.get(resource)
        usage[resource] = {
            "table": table,
            "description": description,
            "current": current,
            "limit": limit,
            # `remaining` is None for an unlimited resource rather than a large
            # number, so a caller cannot render "unlimited" as a misleading figure.
            "remaining": None if limit is None else max(0, limit - current),
            "exceeded": limit is not None and current > limit,
        }

    return {"tenant": tenant, "resources": usage}


def check_quota(
    base: PlatformContext,
    tenant: str,
    resource: str,
    *,
    requested: int = 1,
) -> None:
    """Raise if writing `requested` more rows would exceed the limit.

    Called *before* the write. A quota discovered afterwards has to undo it, and undoing
    a partially ingested document leaves the tenant unsure what actually landed.

    An undeclared quota permits the write. That is the one non-fail-closed decision here,
    and it is deliberate: defaulting to zero would stop every existing deployment from
    accepting writes the moment this ships, and refusing writes for tenants nobody set a
    limit for protects no one.
    """
    if resource not in QUOTA_RESOURCES:
        raise TenantError(f"未知配额资源 {resource}，支持: {'、'.join(sorted(QUOTA_RESOURCES))}")

    limit = tenant_quotas(base, tenant).get(resource)
    if limit is None:
        return

    table = QUOTA_RESOURCES[resource][0]
    current = _tenant_rows(base, tenant, table)

    if current + requested > limit:
        raise QuotaExceeded(tenant, resource, limit, current, requested)


def _tenant_rows(base: PlatformContext, tenant: str, table: str) -> int:
    """How many rows of `table` this tenant has, counted wherever they are.

    Two stores can hold them, and the ceiling has to see both:

    - the store the caller handed in -- the platform database for every HTTP route, which is
      where the application writes. Counting only the tenant's own store made the quota
      decorative: **a limit of one permitted three data sources**, and only a limit of zero
      ever refused anything, because `0 + 1 > 0`.
    - the tenant's own store (`tenant_context`): for SQLite a separate file, for the server
      dialects a schema. That is where the library API writes when its caller passes a tenant
      context, and where `add_workflow_state`-style embedded callers have always written.

    Summed rather than chosen between, because the two mistakes are not equal: over-counting a
    tenant refuses a write they could have made and tells them why, while under-counting lets
    one tenant fill the shared database -- which is what this ceiling exists to prevent.

    A table carrying `tenant_id` (a shared-schema deployment that added the column) is filtered
    by it, so one tenant's rows are not counted against another's allowance.
    """
    total = 0
    with base.connect() as conn:
        total += _count(conn, table, tenant=tenant)

    scoped = tenant_context(base, tenant)
    if scoped.connection_uri != base.connection_uri or scoped.schema != base.schema:
        # A SQLite tenant store is a file, and opening one that is not there *creates* it --
        # so a read-only usage report would leave an empty `platform-<tenant>.sqlite3` behind
        # for every tenant an administrator merely looked at. An absent file is zero rows,
        # which is what the handler below would have answered anyway.
        if scoped.db_type == "sqlite" and not Path(scoped.connection_uri).exists():
            return total
        try:
            with scoped.connect() as conn:
                # Unfiltered: the store is wholly this tenant's -- its own file, or its own
                # schema -- so every row in it belongs to the tenant the ceiling is for. The
                # filter above exists for a *shared* store, where the column is what separates
                # one tenant's rows from another's; applying it here would miss the rows an
                # embedded caller wrote through a plain path, which carry no tenant stamp.
                total += _count(conn, table)
        except Exception as error:
            # A tenant that was never provisioned has no store; that is zero rows, not a
            # failure to answer -- and a quota check that errors is a quota check that gets
            # removed.
            logger.debug("配额统计跳过租户库 %s: %s", tenant, error)
    return total


def _count(conn: Any, table: str, *, tenant: str = "") -> int:
    """Row count, or 0 when the table is absent.

    A missing table means the feature was never used, which is zero rows -- not an
    error. Raising here would make a quota check fail on a tenant provisioned before the
    table existed, and a quota check that errors is a quota check that gets removed.

    `tenant` filters the count when the table has a `tenant_id` column: a shared-schema
    deployment that added it must not count one tenant's rows against another's allowance.
    Where the column is absent -- every SQLite deployment, and any server deployment that
    never provisioned tenants -- the store itself belongs to one tenant, so all of its rows
    are that tenant's.
    """
    try:
        if tenant and _has_column(conn, table, "tenant_id"):
            row = conn.execute(f"select count(*) as total from {table} where tenant_id = ?", (tenant,)).fetchone()
        else:
            row = conn.execute(f"select count(*) as total from {table}").fetchone()
    except Exception as error:
        logger.debug("配额统计跳过表 %s: %s", table, error)
        return 0
    return int(row["total"]) if row else 0


def _has_column(conn: Any, table: str, column: str) -> bool:
    """Whether the table has this column, across the three dialects.

    Asked of the live catalog rather than of a list in this file: the column is added by
    `tenancy._ensure_tenant_columns` on a deployment that provisions tenants, and a list here
    would be right on exactly the deployments where somebody remembered to update it.
    """
    try:
        rows = conn.execute(f"select * from {table} limit 0")
        description = getattr(rows, "description", None)
        if description:
            return any(getattr(entry, "name", entry[0]) == column for entry in description)
    except Exception:
        return False
    return False


def verify_resources_are_tenant_scoped() -> None:
    """Every limitable resource must count a tenant-scoped table.

    Enforced rather than assumed. A resource pointing at a platform-global table --
    `industry_blueprint`, `platform_user` -- would count *every* tenant's rows on a
    shared-schema dialect, so one tenant's usage would consume another's quota and the
    tenant hitting the limit would have done nothing to cause it.

    Called at import so the mistake surfaces at startup, and asserted again by
    `tests/test_tenant_quotas.py` so it surfaces at review.
    """
    stray = {resource: table for resource, (table, _) in QUOTA_RESOURCES.items() if table not in TENANT_SCOPED_TABLES}
    if stray:
        raise TenantError(f"以下配额资源指向非租户表，会跨租户计数: {stray}")


verify_resources_are_tenant_scoped()
