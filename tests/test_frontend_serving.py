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
