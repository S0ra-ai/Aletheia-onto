"""The `/v1` prefix: every route served twice, with identical protection.

Without a version prefix there is nowhere to put a breaking change -- the first
external caller freezes the current shape permanently. Serving both the bare and
versioned form means existing callers keep working while new ones pin a version.

The property that actually matters is not that `/v1` exists. It is that the versioned
copy is **exactly as protected as the bare one**. A `/v1` tree that skipped the
authorization middleware would be an unauthenticated copy of the entire API, which is
a far worse outcome than having no versioning at all.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.access_policy import (
    PUBLIC_PATHS,
    VERSION_PREFIXES,
    is_public,
    required_capability,
    strip_version_prefix,
)


def _routes():
    """Every route the app declares, bare form only.

    Read from `declared_routes()` rather than `app.routes`: FastAPI 0.141 expands
    `include_router` lazily, so the app holds placeholder objects instead of routes and
    a reflective walk silently returns nothing. Silently is what makes it dangerous --
    every assertion in this module iterates routes, so an empty list turns the whole
    file into a suite that passes by checking nothing.
    """
    from ontology_platform.api import declared_routes

    routes = declared_routes()
    # The guard the lazy-expansion change would have needed: an enumeration that can
    # return nothing must be asserted non-empty at the source.
    assert len(routes) > 100, f"仅枚举到 {len(routes)} 条路由，说明枚举方式已失效"
    return routes


def test_every_route_is_also_served_under_the_version_prefix() -> None:
    """Asserted by routing a request, not by inspecting a list.

    The earlier version compared declared paths against declared `/v1` paths. That
    passed while `/v1` was in fact unreachable: the routes were registered through a
    mechanism the comparison could not see. Asking the app to resolve the path is the
    only check that fails when the prefix stops working.
    """
    from ontology_platform.api import app
    from starlette.routing import Match

    prefix = VERSION_PREFIXES[0]
    unreachable = []
    for route in _routes():
        target = f"{prefix}{_concrete(route.path)}"
        method = sorted(route.methods or {"GET"})[0]
        scope = {"type": "http", "method": method, "path": target, "headers": [], "query_string": b""}
        if not any(candidate.matches(scope)[0] is Match.FULL for candidate in app.routes):
            unreachable.append(f"{method} {target}")
    assert not unreachable, f"以下路由的 {prefix} 版本无法路由到: {unreachable[:5]}"


def test_the_versioned_copy_needs_the_same_capability() -> None:
    """The whole point of stripping the prefix in one place.

    A policy table that only matched the bare form would leave every `/v1` route to the
    deny-by-default fallback -- admin-only. That fails safe, so it would not be caught
    by a smoke test, only by someone finding their `/v1` calls rejected.
    """
    prefix = VERSION_PREFIXES[0]
    for route in _routes():
        if route.path.startswith(prefix):
            continue
        for method in sorted(route.methods or ()):
            if method in ("HEAD", "OPTIONS"):
                continue
            assert required_capability(method, f"{prefix}{route.path}") == required_capability(method, route.path), (
                f"{method} {route.path} 与其 {prefix} 版本所需能力不一致"
            )


@pytest.mark.parametrize("path", sorted(PUBLIC_PATHS))
def test_public_paths_stay_public_when_versioned(path) -> None:
    """Otherwise the versioned login endpoint would demand a token to obtain one."""
    prefix = VERSION_PREFIXES[0]
    assert is_public(path)
    assert is_public(f"{prefix}{path}")


def test_a_protected_path_does_not_become_public_when_versioned() -> None:
    """The dangerous direction. Failing closed on an unmatched route is survivable;
    treating a protected route as public is not."""
    prefix = VERSION_PREFIXES[0]
    for path in ("/auth/users", "/ontologies/1/publish", "/model/config"):
        assert not is_public(path)
        assert not is_public(f"{prefix}{path}")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/v1/ontologies/1", "/ontologies/1"),
        ("/ontologies/1", "/ontologies/1"),
        ("/v1", "/"),
        ("/v1/", "/"),
        # Not a prefix match: a route that merely starts with the same letters must be
        # left alone, or `/v1beta/...` would be silently rewritten.
        ("/v1beta/ontologies", "/v1beta/ontologies"),
        ("/versions/1", "/versions/1"),
    ],
)
def test_prefix_stripping_is_exact(raw, expected) -> None:
    assert strip_version_prefix(raw) == expected


def test_openapi_lists_each_operation_once() -> None:
    """Two copies of every operation would give generated clients two of everything."""
    from ontology_platform.api import app

    schema = app.openapi()
    versioned = [path for path in schema["paths"] if path.startswith(VERSION_PREFIXES[0])]
    assert not versioned, f"OpenAPI 中出现了重复的版本化路径: {versioned[:5]}"


def test_the_versioned_tree_is_behind_the_same_middleware() -> None:
    """The property worth protecting: `/v1` is not an unauthenticated copy of the API.

    One router included twice, rather than a sub-application mounted at `/v1` -- a
    sub-application does not inherit the parent's middleware, and the middleware is what
    authenticates every request.

    Checked by sending real unauthenticated requests, because that is the only form of
    evidence that distinguishes the two arrangements at runtime. A protected route must
    answer 401 on both forms; if the versioned tree bypassed the middleware it would
    reach the handler instead and answer 200, 404 or 422 -- anything but 401.
    """
    from fastapi.testclient import TestClient
    from ontology_platform.api import app

    prefix = VERSION_PREFIXES[0]
    protected = [route for route in _routes() if not is_public(_concrete(route.path))]
    assert len(protected) > 100, f"仅 {len(protected)} 条受保护路由，枚举可能已失效"

    leaked = []
    with TestClient(app) as client:
        for route in protected:
            real = _concrete(route.path)
            for method in sorted(route.methods or ()):
                if method in ("HEAD", "OPTIONS"):
                    continue
                for path in (real, f"{prefix}{real}"):
                    status = client.request(method, path).status_code
                    if status != 401:
                        leaked.append(f"{method} {path} -> {status}")
    assert not leaked, f"以下路由未鉴权即可到达（应为 401）: {leaked[:8]}"


# -- Policy coverage --

# Endpoints that genuinely require an administrator: users, tenants, roles, model
# configuration, tool authorisation and the demo bootstrap. Listed explicitly so a *new*
# endpoint cannot join them by accident.
#
# The deny-by-default fallback is correct as a safety net, but a feature silently landing
# on it is a bug of a specific kind: it ships locked to admins, so nobody but an admin ever
# finds out the policy entry is missing.
EXPECTED_ADMIN_ONLY = {
    "POST /auth/users",
    "PATCH /auth/users/1/status",
    "POST /demo/bootstrap",
    "POST /demo/bootstrap/equipment",
    "POST /agent/roles",
    "DELETE /agent/roles/contract",
    "POST /model/config",
    "DELETE /model/config",
    "POST /tenants",
    "POST /permissions/roles",
    "POST /permissions/policies",
    "POST /tools",
    "POST /tools/authorize",
}


def _concrete(path: str) -> str:
    """Substitute a plausible value per path parameter.

    The policy table matches real paths, so checking a route *template* would report every
    parameterised route as unmatched -- which is how an audit produces false positives and
    then gets ignored.
    """
    return re.sub(
        r"\{([^}]+)\}",
        lambda match: "contract" if ("code" in match.group(1) or "object" in match.group(1)) else "1",
        path,
    )


def test_no_new_endpoint_silently_lands_on_the_admin_default() -> None:
    """Deny-by-default is the right safety net, but landing on it silently is a bug.

    An endpoint with no policy entry ships locked to administrators, so the missing entry is
    invisible to everyone who would notice it.
    """
    from ontology_platform.access_policy import CAP_ADMIN

    prefix = VERSION_PREFIXES[0]
    unexpected = []
    for route in _routes():
        if route.path.startswith(prefix):
            continue
        real = _concrete(route.path)
        for method in sorted(route.methods or ()):
            if method in ("HEAD", "OPTIONS", "GET") or is_public(real):
                continue
            entry = f"{method} {real}"
            if required_capability(method, real) == CAP_ADMIN and entry not in EXPECTED_ADMIN_ONLY:
                unexpected.append(entry)
    assert not unexpected, (
        "以下写操作端点没有策略条目，已落到「仅管理员」兜底: "
        + "、".join(sorted(unexpected))
        + "。请在 access_policy.RULES 中登记，或加入 EXPECTED_ADMIN_ONLY 并说明理由。"
    )


def test_the_admin_allowlist_does_not_outlive_its_endpoints() -> None:
    """Otherwise the allowlist becomes permission for a future endpoint that happens to
    match a stale entry."""
    prefix = VERSION_PREFIXES[0]
    live = {
        f"{method} {_concrete(route.path)}"
        for route in _routes()
        if not route.path.startswith(prefix)
        for method in (route.methods or ())
    }
    stale = EXPECTED_ADMIN_ONLY - live
    assert not stale, f"EXPECTED_ADMIN_ONLY 中的条目已不存在对应端点: {sorted(stale)}"


def test_the_newest_capability_endpoints_are_registered_not_defaulted() -> None:
    """The features added most recently are the likeliest to have been forgotten."""
    from ontology_platform.access_policy import CAP_READ, CAP_WRITE

    assert required_capability("GET", "/source-types") == CAP_READ
    assert required_capability("GET", "/writeback-channels") == CAP_READ
    assert required_capability("POST", "/ontologies/1/objects/contract/instances/1/versions") == CAP_WRITE
    assert required_capability("PUT", "/ontologies/1/objects/contract/parent") == CAP_WRITE
