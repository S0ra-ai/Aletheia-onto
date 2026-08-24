"""Tenant provisioning, isolation reporting, and quotas.

Provisioning and quotas share a module because they share the thing that makes both
meaningful: **both are platform-level operations, never tenant-level ones**. A tenant
that could provision itself could pick its own schema; a tenant that could edit its own
quota could raise it. Both therefore act through the *base* context rather than the
tenant's own, and both require platform-admin capability.

`/tenants/{tenant}/quota-usage` reports usage against limits. Usage is counted from the
tenant's own tables rather than from a stored counter -- a counter drifts from the rows
it counts, and a drifted counter either blocks a tenant who is under their limit or lets
one past it.

An undeclared quota is unlimited, not zero. Defaulting to zero would stop every existing
deployment from accepting writes the moment quotas shipped, which is a silent outage
caused by adding a feature nobody opted into.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import Principal
from ..context import resolve_context
from ..database import connect
from ..http_runtime import current_principal, platform_db
from ..quotas import (
    describe_quota_resources,
    quota_usage,
    set_tenant_quota,
    tenant_quotas,
)
from ..tenancy import (
    TenantError,
    list_tenants,
    provision_tenant,
    tenant_context,
    tenant_statistics,
)

router = APIRouter()


# -- Request models --


class QuotaSet(BaseModel):
    resource: str
    limit: int
    note: str = ""


class TenantCreate(BaseModel):
    tenant: str


def _tenant_base_context() -> Any:
    """The context tenants are provisioned from.

    Uses the process default, so provisioning targets whatever platform database
    the deployment is configured with rather than a hardcoded path.
    """
    return resolve_context(platform_db())


@router.get("/tenants")
def tenants() -> dict[str, object]:
    """Provisioned tenants.

    Multi-tenancy is opt-in: a single-tenant deployment provisions nothing and this
    returns an empty list, which is not an error.
    """
    base = _tenant_base_context()
    return {
        "items": list_tenants(base),
        "isolationModel": "separate-schema-plus-tenant-id",
        "dbType": base.db_type,
    }


@router.post("/tenants")
def create_tenant(
    payload: TenantCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Provision a tenant: create its schema and base tables.

    Idempotent, so it is safe to call on every deployment.
    """
    try:
        result = provision_tenant(_tenant_base_context(), payload.tenant)
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    with connect(platform_db()) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                principal.actor,
                "provision_tenant",
                "tenant",
                result["tenant"],
                json.dumps({"schema": result["schema"]}, ensure_ascii=False),
            ),
        )
    return result


@router.get("/tenants/{tenant}/statistics")
def tenant_stats(tenant: str) -> dict[str, object]:
    """Row counts for one tenant, for verifying isolation after provisioning."""
    try:
        return tenant_statistics(tenant_context(_tenant_base_context(), tenant))
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


# -- Quotas --


@router.get("/quota-resources")
def quota_resources() -> dict[str, object]:
    """What can be limited, and which table each resource counts.

    The table is exposed because an operator setting a limit needs to know what is being
    counted: `ontologies` counts versions too, so a limit that looks generous can be
    exhausted by a normal `derive` workflow.
    """
    return {"items": describe_quota_resources()}


@router.get("/tenants/{tenant}/quotas")
def tenant_quota_report(tenant: str) -> dict[str, object]:
    """Declared limits and current usage for one tenant.

    Both together, because a limit without usage cannot answer the question an operator
    actually has -- "is this tenant about to be blocked" -- and usage without limits
    cannot either.
    """
    try:
        base = _tenant_base_context()
        return {
            "declared": tenant_quotas(base, tenant),
            **quota_usage(base, tenant),
            "note": "未声明配额的资源为不限量；配额存放在基础库，租户无法自行修改。",
        }
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.put("/tenants/{tenant}/quotas")
def declare_tenant_quota(
    tenant: str,
    payload: QuotaSet,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Set one resource limit for one tenant.

    Written to the base database, which is what makes the limit binding: a quota stored
    in the tenant's own schema would be reachable by the same connection that writes the
    data it limits.
    """
    try:
        result = set_tenant_quota(
            _tenant_base_context(),
            tenant,
            payload.resource,
            payload.limit,
            note=payload.note,
        )
    except TenantError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    with connect(platform_db()) as conn:
        conn.execute(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
            (
                principal.actor,
                "set_tenant_quota",
                "tenant",
                tenant,
                json.dumps(result, ensure_ascii=False),
            ),
        )
    return result
