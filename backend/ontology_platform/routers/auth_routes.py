"""Authentication and user administration routes.

Login, logout, the caller's own identity, password change, user administration, and a
read-only view of the effective authorization policy.

`/auth/login` is the one route here that must be reachable without a token -- it is how
a token is obtained. That exemption lives in `access_policy.PUBLIC_PATHS`, not in this
module, so the set of unauthenticated routes can be reviewed in one place rather than
discovered by reading every router.

`/auth/access-policy` returns the policy rather than enforcing anything. An
authorization matrix nobody can read gets worked around instead of corrected.

Stability: internal. Routers are an implementation detail of the HTTP layer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from .. import http_runtime
from ..access_policy import PUBLIC_PATHS, describe_policy
from ..auth import (
    ROLE_CAPABILITIES,
    AuthenticationError,
    Principal,
    change_password,
    create_user,
    list_users,
    login,
    logout,
    set_user_status,
)
from ..http_runtime import bearer_token, current_principal, platform_db

router = APIRouter()


class LoginCreate(BaseModel):
    username: str
    password: str


class UserCreate(BaseModel):
    username: str
    password: str
    roleCode: str = "analyst"
    displayName: str = ""


class UserStatusUpdate(BaseModel):
    status: str


class PasswordChange(BaseModel):
    currentPassword: str
    newPassword: str


@router.post("/auth/login")
def auth_login(payload: LoginCreate) -> dict[str, object]:
    try:
        return login(platform_db(), payload.username, payload.password)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/auth/logout")
def auth_logout(request: Request) -> dict[str, object]:
    return logout(platform_db(), bearer_token(request))


@router.get("/auth/me")
def auth_me(principal: Principal = Depends(current_principal)) -> dict[str, object]:
    return principal.public_dict()


@router.post("/auth/change-password")
def auth_change_password(
    payload: PasswordChange,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return change_password(platform_db(), principal.username, payload.currentPassword, payload.newPassword)
    except AuthenticationError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/auth/users")
def auth_list_users() -> dict[str, object]:
    return {"items": list_users(platform_db()), "roles": sorted(ROLE_CAPABILITIES)}


@router.post("/auth/users")
def auth_create_user(
    payload: UserCreate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return create_user(
            platform_db(),
            payload.username,
            payload.password,
            payload.roleCode,
            payload.displayName,
            actor=principal.actor,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.patch("/auth/users/{username}/status")
def auth_set_user_status(
    username: str,
    payload: UserStatusUpdate,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return set_user_status(platform_db(), username, payload.status, actor=principal.actor)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/auth/access-policy")
def auth_access_policy() -> dict[str, object]:
    """Effective route-to-capability policy, for review."""
    return {
        # Read through the module, not through a `from ... import` copy bound at import
        # time. This endpoint is how an operator checks whether authentication is on; a
        # stale copy here would report "on" while the middleware ran with it off, which
        # is worse than not reporting it at all.
        "authEnabled": http_runtime.AUTH_ENABLED,
        "roles": {role: sorted(caps) for role, caps in ROLE_CAPABILITIES.items()},
        "rules": describe_policy(),
        "publicPaths": sorted(PUBLIC_PATHS),
    }
