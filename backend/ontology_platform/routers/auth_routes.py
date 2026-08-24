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
from ..sso import (
    SsoError,
    declare_group_mapping,
    describe_sso,
    list_group_mappings,
    login_with_assertion,
    remove_group_mapping,
)

router = APIRouter()


class SsoLogin(BaseModel):
    assertion: str


class SsoGroupMapping(BaseModel):
    providerGroup: str
    roleCode: str
    note: str = ""


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


# -- SSO --


@router.get("/auth/sso")
def sso_status() -> dict[str, object]:
    """Whether SSO is usable, and what it would grant. Never the signing secret.

    Reports whether any group is mapped, because SSO that verifies correctly and maps
    nothing rejects every login -- and "configured but nobody can sign in" is otherwise
    indistinguishable from a signature problem.
    """
    return describe_sso(platform_db())


@router.post("/auth/sso/login")
def sso_login(payload: SsoLogin) -> dict[str, object]:
    """Exchange a verified provider assertion for a platform session.

    Public like `/auth/login`: it is how a token is obtained. What makes that safe is that
    the assertion is verified against a configured key before anything else happens -- an
    unverified token is a token the caller wrote themselves.

    An identity whose groups map to no platform role is refused rather than given a default
    one. A default would silently grant every employee read access to every business object
    the platform reaches.
    """
    try:
        return login_with_assertion(platform_db(), payload.assertion)
    except SsoError as error:
        raise HTTPException(status_code=401, detail=str(error)) from error


@router.get("/auth/sso/mappings")
def sso_mappings() -> dict[str, object]:
    return {"items": list_group_mappings(platform_db())}


@router.put("/auth/sso/mappings")
def declare_sso_mapping(
    payload: SsoGroupMapping,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    """Map a provider group to a platform role.

    This is where authority is decided, which is why it is separate from the provider: an
    OIDC token can carry any claim including `role: admin`, and trusting it would move the
    authorization boundary into someone else's configuration.
    """
    try:
        return declare_group_mapping(
            platform_db(),
            payload.providerGroup,
            payload.roleCode,
            note=payload.note,
            actor=principal.actor,
        )
    except SsoError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/auth/sso/mappings/{provider_group}")
def remove_sso_mapping(
    provider_group: str,
    principal: Principal = Depends(current_principal),
) -> dict[str, object]:
    try:
        return remove_group_mapping(platform_db(), provider_group, actor=principal.actor)
    except SsoError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
