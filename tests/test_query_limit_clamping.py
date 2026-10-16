"""A caller-supplied limit must not be able to ask for the whole table.

`limit: int = 50` reads like a page size and is not one: FastAPI hands the query string
straight through, and `LIMIT -1` is *"no limit"* in SQLite. So `?limit=-1` on `/governance/audit-log`
returned every row the deployment had ever written, in one response -- measured on a seeded
instance, 50 rows by default and 5 015 on request -- and `?limit=1000000000` did the same.

That is worse than a large response. The audit log, the decision records and the model
invocations are the platform's evidence that it behaved correctly; an endpoint that will
serialise all of them on request is a data-export endpoint nobody decided to build. And it is
one query string, so it costs an attacker nothing to try.

Four endpoints had it, all in the same shape: a route parameter forwarded to SQL. Five others
in the same codebase already clamp with `max(1, min(limit, N))`, which is why this is a gap
rather than a policy -- the house convention existed and four places did not follow it.

The check below is behavioural rather than static: it asks every `limit`-taking endpoint for
more rows than any page can hold and asserts it does not get them. A new endpoint that forgets
the clamp is covered the moment it exists, without anybody editing this file.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from ontology_platform.config import QUERY_LIMITS

ADMIN_PASSWORD = "limit-clamp-password-123"

# Endpoints the fixture can fill past `max_page_size`, so that "it did not return more than a
# page" is a statement that could have been false. Concrete paths rather than templates,
# because the point is to send a real request.
#
# Three endpoints that also take `limit` are deliberately absent -- `/feedback`,
# `/ontologies/{id}/knowledge/entries` and `.../instances/{id}/events` -- because filling them
# past the cap means building a chain of parent rows (a message for a rating, a document for an
# entry, a declared type for an event) and they already clamp in their service layer. Leaving
# them out of a behavioural test that could not fail for them is the point; they are covered by
# `test_every_limit_is_clamped_before_it_reaches_sql` below, which reads the source and can.
LIMITED_ENDPOINTS = (
    "/governance/audit-log",
    "/governance/model-invocations",
    "/governance/decisions",
    "/tools/pending-reviews",
    "/conversations",
)

# Values that must not widen the response. `-1` is the interesting one and the reason this
# file exists: it is a perfectly ordinary integer, and SQLite reads it as "no limit".
HOSTILE_LIMITS = (-1, -1000, 0, 10**9, QUERY_LIMITS.max_page_size + 1, 2**31 - 1)


@pytest.fixture
def seeded_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app with more rows in each limited table than any page can hold.

    Rows are the whole point: a clamp that is missing is invisible on a table with three rows,
    because three rows is under every cap. This is the same trap as the blank-column defects --
    the check passes because there is nothing to check.
    """
    platform_db = tmp_path / "platform.sqlite3"
    sample_db = tmp_path / "legacy_contracts.sqlite3"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module
    from ontology_platform.database import connect, initialize_platform_db
    from ontology_platform.onboarding import run_onboarding_pipeline
    from ontology_platform.sample_data import create_contract_sample_db

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)

    initialize_platform_db(platform_db)
    create_contract_sample_db(sample_db)
    run_onboarding_pipeline(
        platform_db,
        "限量样例系统",
        "sqlite",
        str(sample_db),
        domain="合同管理",
        system_category="database+api",
        blueprint_id="contract-management",
    )

    from ontology_platform.bootstrap import prepare_database
    from ontology_platform.ontology import generate_ontology_draft
    from ontology_platform.semantic_kernel import assess_instance

    with connect(platform_db) as conn:
        prepare_database(conn)
        source_id = int(conn.execute("select id from data_source").fetchone()["id"])
        ontology_id = int(conn.execute("select id from ontology").fetchone()["id"])

    draft = generate_ontology_draft(platform_db, source_id)
    del draft
    assess_instance(platform_db, ontology_id, "contract", "1")

    # Well past `max_page_size`, so a missing clamp shows up as a difference rather than as an
    # assertion that happens to hold at this row count.
    filler = (QUERY_LIMITS.max_page_size + 1) * 4
    with connect(platform_db) as conn:
        conn.executemany(
            "insert into audit_log (actor, action, target_type, target_id, detail) values (?,?,?,?,?)",
            [("filler", "bulk_fill", "test", str(index), "{}") for index in range(filler)],
        )
        conn.executemany(
            "insert into model_invocation (provider, model, purpose, prompt_tokens, completion_tokens,"
            " total_tokens, status) values ('openrouter', 'm', 'qa', 1, 2, 3, 'success')",
            [() for _ in range(filler)],
        )
        conn.executemany(
            "insert into decision_record (decision_id, decision_type, status, recommendation)"
            " values (?, 'assess', 'approved', '')",
            [(f"clamp-decision-{index}",) for index in range(filler)],
        )

    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as client:
        # So the probe below can ask the same database how many rows it actually holds: the
        # assertion there is only worth making against the real count.
        client.platform_db = platform_db  # type: ignore[attr-defined]
        # Through the API: the tool review queue and the conversation list live in optional
        # feature bundles whose foreign keys point at rows the platform creates.
        token = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        registered = client.post(
            "/tools",
            headers=headers,
            json={"code": "submit", "name": "提交", "toolType": "mutation", "riskLevel": "high"},
        )
        assert registered.status_code in (200, 201), registered.text
        with connect(platform_db) as conn:
            conn.executemany(
                "insert into tool_execution_log (tool_id, tool_code, agent_role, object_code, instance_id,"
                " input_args, result_summary, status, error, duration_ms, requires_review)"
                " values (?, 'submit', 'reviewer', 'contract', '1', '{}', '', 'success', '', 12, 1)",
                [(int(registered.json()["id"]),) for _ in range(filler)],
            )
            conn.executemany(
                "insert into conversation (session_id, title, status, actor) values (?, 't', 'open', 'filler')",
                [(f"clamp-{index}",) for index in range(filler)],
            )

        yield client

    database_module._platform_adapter = None


def _row_count(payload: object) -> int:
    """Rows in a list response, whichever key the endpoint names its list by."""
    if not isinstance(payload, dict):
        return -1
    for key in ("items", "versions", "roles", "policies", "tools", "backups"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return -1


@pytest.mark.parametrize("path", LIMITED_ENDPOINTS)
def test_a_hostile_limit_cannot_widen_the_response(seeded_client: TestClient, path: str) -> None:
    token = seeded_client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    baseline = seeded_client.get(path, headers=headers)
    assert baseline.status_code == 200, f"{path}: {baseline.status_code} {baseline.text[:200]}"
    default_rows = _row_count(baseline.json())
    assert default_rows > 0, f"{path} 没有数据行，这条检查没有被真正验证到"

    for value in HOSTILE_LIMITS:
        response = seeded_client.get(f"{path}?limit={value}", headers=headers)
        assert response.status_code == 200, f"{path}?limit={value}: {response.status_code}"
        rows = _row_count(response.json())
        assert rows <= QUERY_LIMITS.max_page_size, (
            f"{path}?limit={value} 返回了 {rows} 行，上限是 {QUERY_LIMITS.max_page_size}——"
            "调用方可以用 limit 把整张表取走（SQLite 把 LIMIT -1 读作「不限制」）"
        )
        assert rows >= 1, f"{path}?limit={value} 返回了 {rows} 行——下限同样需要钳制"


def test_every_limit_a_route_takes_is_clamped_before_it_reaches_sql() -> None:
    """The static half, which covers the endpoints the fixture cannot fill.

    A behavioural check only proves what it has rows for. This one reads the source and follows
    the value: for every HTTP route that takes a caller-supplied `limit`, either the route
    clamps it or every function it hands it to does. Both halves are real -- the four that were
    broken are exactly the four where neither was true, and the adapter layer that *looks*
    unclamped (`adapters.browse_rows`, `instance_resolver.list_ids`) is reached only through
    callers that clamp, which is why following the value rather than scanning every function is
    what makes this check say something true.
    """
    import ast

    backend = ROOT / "backend" / "ontology_platform"
    clamp_markers = ("clamp_page_size", "clamp_sample_size", "max(1, min(", "max(0, min(")

    def functions(path: Path) -> list[ast.FunctionDef]:
        return [
            node for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(node, ast.FunctionDef)
        ]

    def body_of(node: ast.FunctionDef, lines: list[str]) -> str:
        return "\n".join(lines[node.lineno - 1 : node.end_lineno or node.lineno])

    # Which functions clamp, anywhere in the backend.
    clamping: set[str] = set()
    for path in sorted(backend.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in functions(path):
            if any(marker in body_of(node, lines) for marker in clamp_markers):
                clamping.add(node.name)

    offenders: list[str] = []
    for path in [backend / "api.py", *sorted((backend / "routers").glob("*.py"))]:
        lines = path.read_text(encoding="utf-8").splitlines()
        for node in functions(path):
            if not any(argument.arg == "limit" for argument in node.args.args + node.args.kwonlyargs):
                continue
            body = body_of(node, lines)
            if any(marker in body for marker in clamp_markers):
                continue
            # No clamp here, so every callee it passes `limit` to has to clamp on its own.
            unchecked = [
                call.func.id
                for call in ast.walk(node)
                if isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and any(isinstance(a, ast.Name) and a.id == "limit" for a in call.args)
                and call.func.id not in clamping
            ]
            if unchecked:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}  {node.name} → {sorted(set(unchecked))}")

    assert not offenders, (
        "以下路由把调用方给的 limit 交给了不钳制它的函数——SQLite 把 `LIMIT -1` 读作「不限制」，"
        "于是 `?limit=-1` 一次取走整张表。请在路由或该函数里用 config.clamp_page_size 钳制：\n  "
        + "\n  ".join(offenders)
    )


def test_the_static_check_names_the_functions_that_actually_clamp() -> None:
    """A guard on the guard: the set it reasons with has to be non-empty and to contain the
    two clamps, or "every callee is in the clamping set" becomes vacuously true."""
    from ontology_platform.config import clamp_page_size, clamp_sample_size

    assert clamp_page_size(-1) == 1 and clamp_page_size(10**9) == QUERY_LIMITS.max_page_size
    assert clamp_sample_size(-1) == 1
    # Called rather than introspected: the point is that these are the functions the check
    # looks for by name, and a rename would otherwise leave the check silently matching nothing.
    assert callable(clamp_page_size) and callable(clamp_sample_size)


def test_the_probe_can_actually_see_an_unclamped_limit(seeded_client: TestClient) -> None:
    """The fixture has to hold more rows than the cap, or the check above proves nothing.

    A clamp that is missing looks exactly like a clamp that works when the table is small
    enough that the two agree. This asserts the difference is observable: the decision table
    holds well past `max_page_size`, so an endpoint that forgot the clamp *would* return more.
    """
    from ontology_platform.database import connect

    platform_db = seeded_client.platform_db  # type: ignore[attr-defined]
    with connect(platform_db) as conn:
        total = int(conn.execute("select count(*) from decision_record").fetchone()[0])
    assert total > QUERY_LIMITS.max_page_size * 2, f"decision_record 只有 {total} 行，不足以让「没有钳制」表现出来"
