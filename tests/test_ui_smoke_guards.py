"""The render check's own guards, which exist because it once passed without looking.

`scripts/ui_smoke.py` drives a browser against a running instance and reports columns that
render blank for every row. Three times it reported a clean run for a sweep that examined
nothing: once because the instance served a different build, once because it had no token,
once because an empty token rendered the login page on every route. Each was fixed, and a
guard that is never exercised is the same claim as the check it protects.

Two of them are pure enough to test without a browser -- they only ask the instance two
questions -- so they are tested here rather than left to the afternoon somebody happens to
run the script. The third, "no row was rendered at all", is asserted on the run's own
summary in the CI job, where there are rows to count.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    """Import `scripts/ui_smoke.py` by path: it is a script, not a package module."""
    spec = importlib.util.spec_from_file_location("ui_smoke_under_test", ROOT / "scripts" / "ui_smoke.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stub_instance():
    """A server that answers the two questions the guards ask, and nothing else."""

    class Handler(BaseHTTPRequestHandler):
        seed_body = "seeding"
        token_ok = True

        def do_GET(self):
            if self.path.startswith("/assets/seed.html"):
                if Handler.seed_body is None:
                    self.send_error(404)
                    return
                self._send(200, Handler.seed_body)
            elif self.path == "/auth/me":
                if Handler.token_ok:
                    self._send(200, json.dumps({"username": "admin", "roleCode": "admin"}))
                else:
                    self._send(401, json.dumps({"detail": "缺少访问令牌"}))
            else:
                self.send_error(404)

        def _send(self, status: int, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):  # keep the test output readable
            return

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", Handler
    finally:
        server.shutdown()


def test_a_seed_page_that_is_served_passes(stub_instance) -> None:
    base_url, _handler = stub_instance
    assert _load_script().seed_is_the_build_just_written(f"{base_url}/assets/seed.html") == ""


def test_a_missing_seed_page_is_named(stub_instance) -> None:
    """The 404 that made sixteen routes render nothing.

    A server started with `ALETHEIA_FRONTEND_DIST` elsewhere serves its own copy of the
    build; the seed page this script writes is not in it, so every route lands on the login
    page and the report reads "0 tables, 0 rows" from top to bottom.
    """
    base_url, handler = stub_instance
    handler.seed_body = None
    reason = _load_script().seed_is_the_build_just_written(f"{base_url}/assets/seed.html")
    assert "not reachable" in reason
    assert "seed.html" in reason


def test_a_seed_page_from_another_build_is_named(stub_instance) -> None:
    base_url, handler = stub_instance
    handler.seed_body = "<!doctype html>some other page"
    reason = _load_script().seed_is_the_build_just_written(f"{base_url}/assets/seed.html")
    assert "different build" in reason
    assert "ALETHEIA_FRONTEND_DIST" in reason, "提示必须说出是哪一种配错，而不是只说拿不到"


def test_a_token_that_authenticates_reports_who(stub_instance) -> None:
    base_url, _handler = stub_instance
    assert _load_script().token_authenticates(base_url, "good") == "sweeping as admin (admin)"


def test_a_token_that_does_not_authenticate_is_refused(stub_instance) -> None:
    """The failure I produced myself, and did not notice for twenty-five routes.

    An empty token -- a password reset refused by the strength policy, with its output sent
    to /dev/null -- rendered the login page everywhere and the sweep still concluded "no
    wholly-empty columns found".
    """
    base_url, handler = stub_instance
    handler.token_ok = False
    reason = _load_script().token_authenticates(base_url, "bad")
    assert reason.startswith("the token does not authenticate")
    assert "nothing would be rendered" in reason


def test_an_unreachable_instance_is_refused() -> None:
    """A port nobody is listening on is not a clean sweep either."""
    reason = _load_script().token_authenticates("http://127.0.0.1:9", "whatever")
    assert reason.startswith("the token does not authenticate")


# -- The route list against the router --


def _app_routes() -> set[str]:
    """Every path the frontend router serves, ids normalised to `*`.

    Read from `App.tsx` because that is the only place the routes exist. A list kept beside
    it would be a second copy, which is how the sweep came to hold `/admin/backup` while the
    application served `/admin/data-backup`: a path that reads correct, is not a route, and
    renders nothing.
    """
    source = (ROOT / "frontend" / "src" / "App.tsx").read_text(encoding="utf-8")
    routes = set()
    for path in re.findall(r'<Route\s+path="([^"]+)"', source):
        # `login` is not behind the authenticated layout, and `*` is the not-found page --
        # neither is a screen with data to show. `/` is the layout itself, whose index
        # redirects to the workbench, which is swept under its own path.
        if path.strip("/") in ("login", "*", ""):
            continue
        # The layout route is `/`, and every child is relative to the `/admin` basename the
        # production build sets.
        normalised = path.strip("/")
        routes.add("/admin/" + normalised if normalised else "/admin")
    # A detail path is compared by shape, not by parameter name: the router writes `:id` and
    # the sweep writes `{ontology}`, and neither spelling is the thing being asserted.
    return {re.sub(r"/:[A-Za-z_]+", "/*", path) for path in routes}


def _swept_routes() -> set[str]:
    """The sweep's routes as router paths: id placeholders to `*`, tabs dropped."""
    module = _load_script()
    paths = set()
    for route in list(module.ROUTES) + list(module.ID_ROUTES):
        path = route.split("?", 1)[0]
        path = re.sub(r"\{(ontology|source)\}", "*", path)
        path = re.sub(r"/\d+(?=/|$)", "/*", path)
        paths.add(path)
    # `/admin/ontology/{ontology}?tab=objects` normalises to `/admin/ontology/*`, and so does
    # the router's `/admin/ontology/:id`.
    return {re.sub(r"/:[A-Za-z_]+", "/*", path) for path in paths}


def test_every_screen_the_router_serves_is_swept() -> None:
    """A screen nobody sweeps is a screen whose columns nobody has looked at.

    Checked against `App.tsx` rather than against a list beside it. `/admin/demo` and
    `/admin/model` had never been visited -- not misspelled, simply absent -- and nothing
    said so: a route list is only as complete as the memory of whoever last edited it.
    """
    missing = _app_routes() - _swept_routes()
    assert not missing, f"以下页面从未被渲染检查访问过：{sorted(missing)}"


def test_every_swept_route_is_a_screen_the_router_serves() -> None:
    """The other direction, which is the one that cost a table nobody had ever read.

    `/admin/backup` was in the list for as long as the list existed. It is the API's
    namespace, so a navigation to it is answered with a 401 body: the sweep printed
    `0 table(s), 0 row(s)` and moved on, while the real backup screen at `/admin/data-backup`
    -- a table with four columns -- was never loaded.
    """
    unknown = _swept_routes() - _app_routes()
    assert not unknown, f"渲染检查在扫这些路径，但它们不是前端路由：{sorted(unknown)}"


def test_a_page_that_failed_to_render_is_recognised() -> None:
    """A crashed screen and a tableless screen print the same line, unless this is read.

    `/admin/graph` has no table on purpose; a `/admin/graph` whose render throws has no table
    either. Both are `0 table(s), 0 row(s)`, and one of them is a defect -- so the sweep reads
    the text the application renders when a screen did not load, and reports it as its own
    finding rather than leaving it to the table count.
    """
    module = _load_script()
    assert module.failure_marker('<div class="ant-result-title">页面加载失败</div>') == "页面加载失败"
    assert module.failure_marker("<h1>页面不存在</h1>") == "页面不存在"
    assert module.failure_marker('<table class="ant-table"><th>备份名称</th></table>') == ""


def test_every_excused_route_is_one_the_sweep_visits() -> None:
    """A key that matches no route excuses nothing -- the route it was meant for fails as
    unexpected instead, and the reason written beside it describes a path that is not swept."""
    module = _load_script()
    unknown = set(module.NO_TABLE_ROUTES) - set(module.ROUTES) - set(module.ID_ROUTES)
    assert not unknown, f"NO_TABLE_ROUTES 里这些键不对应任何被扫的路由：{sorted(unknown)}"
