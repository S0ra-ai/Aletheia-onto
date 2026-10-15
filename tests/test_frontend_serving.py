"""The production image must expose the bundled admin UI, not only the API."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(
    not (ROOT / "frontend" / "dist" / "index.html").is_file(),
    reason="源码检出未包含构建后的 frontend/dist；生产镜像构建会提供它",
)
def test_production_frontend_entry_and_spa_routes_are_served() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from ontology_platform.api import app

    with TestClient(app) as client:
        root = client.get("/", follow_redirects=False)
        entry = client.get("/admin/")
        route = client.get("/admin/workbench")

    assert root.status_code == 307
    assert root.headers["location"] == "/admin/"
    assert '<div id="root"></div>' in entry.text
    assert route.status_code == 200
    assert route.text == entry.text


def test_same_origin_api_prefix_is_public_and_protected_consistently() -> None:
    from fastapi.testclient import TestClient
    from ontology_platform.api import app

    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/ontologies").status_code == 401
        assert client.get("/admin/backup/list").status_code == 401


def test_unknown_api_path_never_falls_back_to_the_spa(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient
    from ontology_platform import api as api_module
    from ontology_platform.api import app

    monkeypatch.setattr(api_module, "AUTH_ENABLED", False)
    with TestClient(app) as client:
        response = client.get("/api/not-a-real-endpoint")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.skipif(
    not (ROOT / "frontend" / "dist" / "index.html").is_file(),
    reason="源码检出未包含构建后的 frontend/dist；生产镜像构建会提供它",
)
def test_every_spa_route_serves_the_shell_without_a_token() -> None:
    """The shell has to load before a token can exist, so no page may demand one.

    This is the property; the route list is the implementation of it. `/admin/backup` was on
    the list and is also an API namespace the access policy keeps out of the shell -- backup
    archives hold credentials -- so that page returned raw `{"detail":"缺少访问令牌"}` for a
    bookmark, a refresh or a new tab, while every other page returned the application. The
    collision is invisible from inside the app: clicking the nav entry routes on the client
    and never asks for the document.
    """
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from ontology_platform.api import app

    # Every lazy route declared in `App.tsx`, by URL.
    pages = (
        "/admin/workbench",
        "/admin/datasource",
        "/admin/ontology",
        "/admin/mapping",
        "/admin/rules",
        "/admin/semantic",
        "/admin/objects",
        "/admin/governance",
        "/admin/demo",
        "/admin/model",
        "/admin/workflow",
        "/admin/permission",
        "/admin/data-backup",
        "/admin/graph",
        "/admin/knowledge",
        "/admin/feedback",
        "/admin/chat",
    )

    with TestClient(app) as client:
        shell = client.get("/admin/").text
        refused = []
        for page in pages:
            response = client.get(page)
            if response.status_code != 200 or response.text != shell:
                refused.append(f"{page} -> {response.status_code} {response.headers.get('content-type')}")
        # And a path nobody declares still renders the application, which reports it.
        unknown = client.get("/admin/no-such-page")

    assert not refused, "这些页面在未认证时拿不到 SPA 外壳:\n" + "\n".join(refused)
    assert unknown.status_code == 200
