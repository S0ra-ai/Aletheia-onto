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

import sys
from pathlib import Path

import pytest
from fastapi.routing import APIRoute

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
    from ontology_platform.api import app

    return [route for route in app.routes if isinstance(route, APIRoute)]


def test_every_route_is_also_served_under_the_version_prefix() -> None:
    prefix = VERSION_PREFIXES[0]
    paths = {route.path for route in _routes()}
    bare = {path for path in paths if not path.startswith(prefix)}
    # The docs and schema endpoints are served by FastAPI itself, not copied.
    bare -= {"/openapi.json", "/docs", "/redoc"}
    missing = [path for path in sorted(bare) if f"{prefix}{path}" not in paths]
    assert not missing, f"以下路由缺少 {prefix} 版本: {missing}"


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


def test_the_versioned_routes_share_the_bare_handlers() -> None:
    """Copied routes, not a mounted sub-application: a sub-app would not inherit the
    parent's middleware, and the middleware is what authenticates every request."""
    prefix = VERSION_PREFIXES[0]
    by_path = {route.path: route for route in _routes()}
    checked = 0
    for path, route in by_path.items():
        if path.startswith(prefix):
            continue
        versioned = by_path.get(f"{prefix}{path}")
        if versioned is None:
            continue
        assert versioned.endpoint is route.endpoint, path
        checked += 1
    assert checked > 100, f"仅校验了 {checked} 条路由，远少于预期"
