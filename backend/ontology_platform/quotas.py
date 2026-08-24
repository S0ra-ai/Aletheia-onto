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

    Counted from the tenant's own tables rather than from a stored counter. A counter
    drifts from the rows it counts, and a drifted counter either blocks a tenant who is
    under their limit or lets one past it -- both are worse than a count that costs a
    query.
    """
    tenant = validate_tenant(tenant)
    limits = tenant_quotas(base, tenant)
    context = tenant_context(base, tenant)

    usage: dict[str, Any] = {}
    with context.connect() as conn:
        for resource, (table, description) in sorted(QUOTA_RESOURCES.items()):
            current = _count(conn, table)
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
    context = tenant_context(base, tenant)
    with context.connect() as conn:
        current = _count(conn, table)

    if current + requested > limit:
        raise QuotaExceeded(tenant, resource, limit, current, requested)


def _count(conn: Any, table: str) -> int:
    """Row count, or 0 when the table is absent.

    A missing table means the feature was never used, which is zero rows -- not an
    error. Raising here would make a quota check fail on a tenant provisioned before the
    table existed, and a quota check that errors is a quota check that gets removed.
    """
    try:
        row = conn.execute(f"select count(*) as total from {table}").fetchone()
    except Exception as error:
        logger.debug("配额统计跳过表 %s: %s", table, error)
        return 0
    return int(row["total"]) if row else 0


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
