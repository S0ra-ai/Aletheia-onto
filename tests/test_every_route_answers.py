"""Every route, called once. None of them may crash.

Why this is weaker than it looks, and what covers the rest
---------------------------------------------------------

An empty body short-circuits at request validation: most handlers answer 422 before
running a line, so a route can pass this and still raise on real input. It is not a
substitute for driving the API properly, and the write contract in
`test_frontend_type_agreement.py` is where that happens -- thirty endpoints called with
bodies a screen actually sends.

What it does cover is the shape of failure this check can see: an import that fails, a
dependency that raises, a route whose handler runs before validation. Those are cheap to
find here and expensive to find in production, and the sweep takes about a second.

It exists because two 500s were found **by accident** -- I was probing request bodies for
the write contract and hit `/data-sources/{id}/initialize` and `/ontologies/draft` on a
seeded instance. Neither had a test, and neither had ever been called with a valid body by
anything but a person clicking a button. "Nobody has tried this" is what this removes.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

# Statuses that prove the handler ran or was refused on purpose. A 5xx is the only failure
# this check looks for: a 4xx is the API answering, and asserting more would make it a
# contract test, which it is deliberately not.
ACCEPTED = range(200, 500)


@pytest.fixture
def seeded_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """The app over an instance with data in it.

    Seeded because that is the difference that matters: on an empty database every route
    that failed for me answered 404 instead of 500.
    """
    import ontology_platform.cli as cli
    import ontology_platform.database as database_module

    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "sample.sqlite3"

    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "route-sweep-password")
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    cli.main(["--platform-db", str(platform_db), "demo", "--sample-db", str(sample_db), "--quiet"])

    api_module = importlib.reload(__import__("ontology_platform.api", fromlist=["app"]))
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)
    with TestClient(api_module.app) as client:
        # Authenticated, or every route answers 401 at the middleware and no handler runs --
        # which is how this sweep reported a clean bill of health on its first version while
        # testing nothing but the access policy.
        login = client.post("/auth/login", json={"username": "admin", "password": "route-sweep-password"})
        assert login.status_code == 200, login.text
        client.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        yield client
    database_module._platform_adapter = None


def test_no_route_crashes_on_an_empty_request(seeded_app: TestClient) -> None:
    import ontology_platform.api as api_module

    failures: list[str] = []
    routes = api_module.declared_routes()

    for route in routes:
        path = route.path
        for parameter in list(route.param_convertors or {}):
            path = path.replace("{" + parameter + "}", "1")
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            try:
                response = seeded_app.request(method, path, json={})
            except Exception as error:
                failures.append(f"{method} {route.path} raised {type(error).__name__}: {error}")
                continue
            if response.status_code not in ACCEPTED:
                failures.append(f"{method} {route.path} -> {response.status_code} {response.text[:120]}")

    assert len(routes) > 100, f"只枚举到 {len(routes)} 条路由，路由注册方式或已改变"
    assert not failures, "以下路由在空请求下崩了：\n  " + "\n  ".join(failures)
