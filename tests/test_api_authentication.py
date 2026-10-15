"""End-to-end authentication and authorization tests.

Every endpoint mutates governed business assets or triggers operations against
legacy systems, so these tests drive the real ASGI app through HTTP to prove
that anonymous access is rejected and that roles are actually enforced.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from ontology_platform.access_policy import required_capability
from ontology_platform.auth import (
    ROLE_CAPABILITIES,
    AuthenticationError,
    hash_password,
    resolve_principal,
    verify_password,
)
from ontology_platform.database import connect, initialize_platform_db

ADMIN_PASSWORD = "admin-password-123"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A live app instance backed by a throwaway SQLite platform database."""
    platform_db = tmp_path / "platform.sqlite3"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", ADMIN_PASSWORD)

    import ontology_platform.api as api_module
    import ontology_platform.database as database_module

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)

    with TestClient(api_module.app) as test_client:
        test_client.platform_db = platform_db  # type: ignore[attr-defined]
        yield test_client

    database_module._platform_adapter = None


def _token(client: TestClient, username: str, password: str) -> str:
    response = client.post("/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# -- Password hashing --


def test_passwords_are_salted_and_verified() -> None:
    digest, salt, iterations = hash_password("correct-horse-battery")
    assert digest != "correct-horse-battery"
    assert len(salt) >= 32
    assert iterations >= 100_000
    assert verify_password("correct-horse-battery", digest, salt, iterations) is True
    assert verify_password("wrong-password", digest, salt, iterations) is False


def test_identical_passwords_get_different_hashes() -> None:
    first, _, _ = hash_password("same-password-value")
    second, _, _ = hash_password("same-password-value")
    assert first != second, "每个用户必须使用独立盐值"


def test_short_passwords_are_rejected() -> None:
    with pytest.raises(ValueError):
        hash_password("short")


# -- Anonymous access --


def test_health_and_login_are_public(client: TestClient) -> None:
    assert client.get("/health").status_code == 200
    assert client.post("/auth/login", json={"username": "nobody", "password": "nope"}).status_code == 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/data-sources"),
        ("get", "/ontologies"),
        ("get", "/governance/audit-log"),
        ("get", "/model/status"),
        ("post", "/data-sources"),
        ("post", "/ontologies/1/publish"),
        ("post", "/automation/operations/submit_contract/execute"),
        ("get", "/auth/users"),
    ],
)
def test_endpoints_reject_anonymous_requests(client: TestClient, method: str, path: str) -> None:
    if method == "get":
        response = client.get(path)
    else:
        response = client.post(path, json={})
    assert response.status_code == 401
    assert response.json()["code"] == "unauthenticated"


def test_invalid_and_malformed_tokens_are_rejected(client: TestClient) -> None:
    assert client.get("/data-sources", headers=_auth("not-a-real-token")).status_code == 401
    assert client.get("/data-sources", headers={"Authorization": "Basic abc"}).status_code == 401


# -- Session lifecycle --


def test_login_returns_token_and_identity(client: TestClient) -> None:
    response = client.post("/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD})
    assert response.status_code == 200
    body = response.json()
    assert body["tokenType"] == "Bearer"
    assert body["user"]["roleCode"] == "admin"
    assert "platform:admin" in body["user"]["capabilities"]
    assert ADMIN_PASSWORD not in response.text


def test_tokens_are_stored_only_as_digests(client: TestClient) -> None:
    token = _token(client, "admin", ADMIN_PASSWORD)
    with connect(client.platform_db) as conn:  # type: ignore[attr-defined]
        rows = conn.execute("select token_hash from user_session").fetchall()
    stored = [row["token_hash"] for row in rows]
    assert stored
    assert token not in stored


def test_logout_revokes_the_token(client: TestClient) -> None:
    token = _token(client, "admin", ADMIN_PASSWORD)
    assert client.get("/auth/me", headers=_auth(token)).status_code == 200
    assert client.post("/auth/logout", headers=_auth(token)).status_code == 200
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401


def test_disabled_user_cannot_use_an_existing_token(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "analyst1", "password": "analyst-password", "roleCode": "analyst"},
    )
    analyst_token = _token(client, "analyst1", "analyst-password")
    assert client.get("/data-sources", headers=_auth(analyst_token)).status_code == 200

    response = client.patch(
        "/auth/users/analyst1/status",
        headers=_auth(admin_token),
        json={"status": "disabled"},
    )
    assert response.status_code == 200
    assert client.get("/data-sources", headers=_auth(analyst_token)).status_code == 401


def test_password_change_invalidates_sessions(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "expert1", "password": "expert-password", "roleCode": "business_expert"},
    )
    token = _token(client, "expert1", "expert-password")
    response = client.post(
        "/auth/change-password",
        headers=_auth(token),
        json={"currentPassword": "expert-password", "newPassword": "expert-new-password"},
    )
    assert response.status_code == 200
    assert client.get("/auth/me", headers=_auth(token)).status_code == 401
    assert _token(client, "expert1", "expert-new-password")


# -- Role based authorization --


def test_analyst_can_read_but_not_write(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "analyst2", "password": "analyst-password", "roleCode": "analyst"},
    )
    token = _token(client, "analyst2", "analyst-password")

    assert client.get("/data-sources", headers=_auth(token)).status_code == 200

    write = client.post(
        "/data-sources",
        headers=_auth(token),
        json={"name": "x", "sourceType": "sqlite", "connectionUri": "/tmp/x.sqlite3"},
    )
    assert write.status_code == 403
    assert write.json()["requiredCapability"] == "platform:write"


def test_business_expert_can_review_but_not_publish(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "expert2", "password": "expert-password", "roleCode": "business_expert"},
    )
    token = _token(client, "expert2", "expert-password")

    # 404 or 400 means the request passed authorization and reached the handler.
    review = client.post("/ontologies/999/mappings/review", headers=_auth(token), json={"status": "confirmed"})
    assert review.status_code != 403

    publish = client.post("/ontologies/999/publish", headers=_auth(token), json={})
    assert publish.status_code == 403
    assert publish.json()["requiredCapability"] == "governance:publish"


def test_operator_can_execute_but_not_model(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "operator1", "password": "operator-password", "roleCode": "operator"},
    )
    token = _token(client, "operator1", "operator-password")

    execute = client.post(
        "/automation/operations/submit_contract/execute",
        headers=_auth(token),
        json={"ontologyId": 1, "dataSourceId": 1, "instanceId": "1"},
    )
    assert execute.status_code != 403

    draft = client.post("/ontologies/draft", headers=_auth(token), json={"dataSourceId": 1})
    assert draft.status_code == 403


def test_non_admin_cannot_manage_users_or_model_config(client: TestClient) -> None:
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "engineer1", "password": "engineer-password", "roleCode": "ontology_engineer"},
    )
    token = _token(client, "engineer1", "engineer-password")

    assert client.get("/auth/users", headers=_auth(token)).status_code == 403
    assert client.post("/model/config", headers=_auth(token), json={"apiKey": "x"}).status_code == 403
    assert client.get("/model/config", headers=_auth(token)).status_code == 403


def test_unlisted_routes_default_to_admin_only() -> None:
    """Deny by default: a newly added route must not be silently public."""
    assert required_capability("POST", "/an/unlisted/route") == "platform:admin"
    assert required_capability("PUT", "/another/new/thing") == "platform:admin"


def test_authentication_is_on_unless_explicitly_disabled() -> None:
    """The default must be "authenticated", not "convenient".

    `ONTOLOGY_AUTH_DISABLED` exists for local development, and the whole API -- including
    writeback to legacy systems -- is reachable with no token while it is set. So the
    dangerous direction is a change that makes *absence* of the variable mean disabled:
    nothing would fail, every test would still pass, and the exposure would only be
    visible to whoever found the open port.

    Asserted per interpreter here rather than in a workflow step, which is where this
    check used to live -- a check that cannot run before pushing reports the problem
    after review has already started.

    Reloads `http_runtime`, which is where the switch is resolved. `api` re-exports it
    for its middleware, so reloading `api` alone would re-bind the old value and the
    assertions would pass without testing anything.
    """
    import ontology_platform.http_runtime as runtime

    assert runtime.AUTH_ENABLED, "认证不能默认关闭"
    # The middleware reads its own module-level copy, so the two must agree: a router
    # that thought authentication was off while the middleware thought it was on would
    # fail open.
    import ontology_platform.api as api_module

    assert api_module.AUTH_ENABLED is runtime.AUTH_ENABLED

    # Only the documented opt-in values disable it. A typo (`ONTOLOGY_AUTH_DISABLED=ture`)
    # must leave authentication on: guessing at intent here would mean guessing in favour
    # of exposure.
    with pytest.MonkeyPatch.context() as patch:
        for value, expected in (
            ("1", False),
            ("true", False),
            ("YES", False),
            ("ture", True),
            ("0", True),
            ("", True),
        ):
            patch.setenv("ONTOLOGY_AUTH_DISABLED", value)
            assert importlib.reload(runtime).AUTH_ENABLED is expected, (
                f"ONTOLOGY_AUTH_DISABLED={value!r} 时认证应为 {expected}"
            )

    # Reload once more with the variable gone, so a later test does not inherit a module
    # left in the disabled state -- that would silently weaken every assertion after it.
    importlib.reload(runtime)
    assert runtime.AUTH_ENABLED


def test_every_role_capability_is_a_known_capability() -> None:
    from ontology_platform.auth import ALL_CAPABILITIES

    for role, capabilities in ROLE_CAPABILITIES.items():
        unknown = capabilities - set(ALL_CAPABILITIES)
        assert unknown == set(), f"角色 {role} 含未知权限 {unknown}"


# -- Audit identity --


def test_audit_log_records_authenticated_actor_not_client_input(client: TestClient) -> None:
    """The client can no longer choose who an action is attributed to."""
    admin_token = _token(client, "admin", ADMIN_PASSWORD)
    client.post(
        "/auth/users",
        headers=_auth(admin_token),
        json={"username": "expert3", "password": "expert-password", "roleCode": "business_expert"},
    )
    token = _token(client, "expert3", "expert-password")

    # Even if a caller injects an actor field, it must be ignored.
    client.post(
        "/ontologies/999/mappings/review",
        headers=_auth(token),
        json={"status": "confirmed", "reviewer": "someone-else", "actor": "root"},
    )
    with connect(client.platform_db) as conn:  # type: ignore[attr-defined]
        actors = [row["actor"] for row in conn.execute("select actor from audit_log").fetchall()]
    assert "someone-else" not in actors
    assert "root" not in actors


def test_resolve_principal_rejects_empty_token(tmp_path: Path) -> None:
    with pytest.raises(AuthenticationError):
        resolve_principal(tmp_path / "missing.sqlite3", "")


def test_republishing_a_published_ontology_is_a_conflict_not_a_server_error(
    client: TestClient,
) -> None:
    """A refused governance rule is client-correctable, so it must not be a 500.

    /demo/bootstrap regenerates a draft for a fixed ontology name. Once that
    version is published, "已发布本体不可改" correctly refuses the second attempt
    (ADR-0002 territory: governance rules are enforced, not advisory). The bug
    was that the ValueError escaped as an opaque 500, telling the caller nothing
    about what to do next.
    """
    token = _token(client, "admin", ADMIN_PASSWORD)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.post("/demo/bootstrap", json={}, headers=headers)
    assert first.status_code == 200, first.text
    ontology_id = first.json()["ontology"]["ontology"]["id"]

    confirm = client.post(
        f"/ontologies/{ontology_id}/mappings/review",
        json={"status": "confirmed", "note": "为发布做准备"},
        headers=headers,
    )
    assert confirm.status_code == 200, confirm.text

    published = client.post(f"/ontologies/{ontology_id}/publish", json={"force": True}, headers=headers)
    assert published.status_code == 200, published.text

    again = client.post("/demo/bootstrap", json={}, headers=headers)
    assert again.status_code == 409, again.text
    assert "派生新版本" in again.json()["detail"]


class TestPasswordRecovery:
    """The way back in when the one-time bootstrap password was missed.

    `aletheia init` prints a generated password once. A deployment that missed it -- rotated
    logs, a scrolled terminal, a container that restarted -- had no way back short of editing
    password hashes by hand, which is not a documented procedure and not one anybody should
    invent.
    """

    @staticmethod
    def _platform_db(tmp_path: Path):
        """A platform database initialised the way `aletheia init` initialises one.

        `initialize_platform_db` alone creates the core tables; the auth schema is applied by
        `prepare_database`, which is the list the application's startup uses. Calling only the
        first left `platform_user` missing, which is the same mistake a deployment makes when
        it initialises by hand.
        """
        from ontology_platform.bootstrap import prepare_database

        platform_db = tmp_path / "platform.sqlite3"
        initialize_platform_db(platform_db)
        with connect(platform_db) as conn:
            prepare_database(conn)
        return platform_db

    def test_a_reset_works_without_the_old_password(self, tmp_path: Path) -> None:
        from ontology_platform.auth import create_user, login, reset_password

        platform_db = self._platform_db(tmp_path)
        create_user(platform_db, "operator", "Original-Pass-2026!", role_code="analyst")

        result = reset_password(platform_db, "operator", "Recovered-Pass-2026!")

        assert result["success"] is True
        assert login(platform_db, "operator", "Recovered-Pass-2026!")["token"]

    def test_the_old_password_stops_working(self, tmp_path: Path) -> None:
        from ontology_platform.auth import AuthenticationError, create_user, login, reset_password

        platform_db = self._platform_db(tmp_path)
        create_user(platform_db, "operator", "Original-Pass-2026!", role_code="analyst")
        reset_password(platform_db, "operator", "Recovered-Pass-2026!")

        with pytest.raises(AuthenticationError):
            login(platform_db, "operator", "Original-Pass-2026!")

    def test_existing_sessions_are_cut_off(self, tmp_path: Path) -> None:
        """A reset is what an operator does when an account may be compromised, so the
        sessions it holds are exactly the ones not to keep."""
        from ontology_platform.auth import (
            AuthenticationError,
            create_user,
            login,
            reset_password,
            resolve_principal,
        )

        platform_db = self._platform_db(tmp_path)
        create_user(platform_db, "operator", "Original-Pass-2026!", role_code="analyst")
        token = login(platform_db, "operator", "Original-Pass-2026!")["token"]
        assert resolve_principal(platform_db, token).username == "operator"

        result = reset_password(platform_db, "operator", "Recovered-Pass-2026!")

        assert result["revokedSessions"] >= 1
        with pytest.raises(AuthenticationError):
            resolve_principal(platform_db, token)

    def test_a_weak_password_is_refused(self, tmp_path: Path) -> None:
        """Recovery must not become the way to leave a privileged account weak."""
        from ontology_platform.auth import create_user, reset_password

        platform_db = self._platform_db(tmp_path)
        create_user(platform_db, "operator", "Original-Pass-2026!", role_code="analyst")

        with pytest.raises(ValueError, match="强度"):
            reset_password(platform_db, "operator", "123")

    def test_an_unknown_account_is_refused_by_name(self, tmp_path: Path) -> None:
        from ontology_platform.auth import reset_password

        platform_db = self._platform_db(tmp_path)

        with pytest.raises(ValueError, match="nobody"):
            reset_password(platform_db, "nobody", "Recovered-Pass-2026!")

    def test_the_reset_is_audited(self, tmp_path: Path) -> None:
        """A privileged action that left no trace is indistinguishable from one nobody took."""
        from ontology_platform.auth import create_user, reset_password
        from ontology_platform.database import connect

        platform_db = self._platform_db(tmp_path)
        create_user(platform_db, "operator", "Original-Pass-2026!", role_code="analyst")
        reset_password(platform_db, "operator", "Recovered-Pass-2026!", actor="cli")

        with connect(platform_db) as conn:
            row = conn.execute(
                "select actor, action, target_id from audit_log where action = 'reset_password'"
            ).fetchone()

        assert row is not None, "重置口令未写入审计"
        assert (row["actor"], row["target_id"]) == ("cli", "operator")


# -- Path tricks against the policy table --

# SECURITY.md names this threat directly: "whether path matching can be bypassed (case,
# encoding, trailing slash, path traversal) so that a low-privilege role reaches a
# high-privilege endpoint". Every form below has to land on the protected side -- or, where
# it does not, has to resolve to something harmless rather than to the API route it
# imitates.
#
# Percent-encoded forms are deliberately *not* listed here: ASGI servers decode `scope["path"]`
# before the application sees it, so `is_public` is never handed `%2f` in production and
# teaching it to decode would introduce a second decode -- the shape that turns `%252f`
# into a path separator. The encoded spellings are covered by the server-level test below,
# which is where they can actually occur.
PATH_TRICKS = (
    ("/API/ONTOLOGIES", False),
    ("/api/ontologies/", False),
    ("/api//ontologies", False),
    ("/api/./ontologies", False),
    ("/api/foo/../ontologies", False),
    ("/%61pi/ontologies", False),
    ("/api/../admin/backup/list", False),
    ("/admin/../api/ontologies", True),  # public, but it must not *be* the API route
    ("/admin/backup/list", False),
    ("/admin/backup/../backup/list", False),
)


@pytest.mark.parametrize(("path", "expected_public"), PATH_TRICKS)
def test_path_spelling_does_not_get_past_the_policy(path: str, expected_public: bool) -> None:
    from ontology_platform.access_policy import is_public

    assert is_public(path) is expected_public, f"{path} 的公开判定与预期不符"


@pytest.mark.parametrize(("path", "_expected"), PATH_TRICKS)
def test_no_path_spelling_reaches_a_protected_endpoint_without_a_token(
    client: TestClient, path: str, _expected: bool
) -> None:
    """The policy decides on the path as sent, so this asks the server, not the table.

    A form that the policy calls public is only safe if it also fails to resolve to the API
    route it imitates. `/admin/../api/ontologies` is the case that matters: it is public as a
    browser path, and the answer has to be the SPA shell rather than the ontology list.
    """
    response = client.get(path)
    if response.status_code == 200:
        body = response.text.lstrip()
        assert body.startswith("<!doctype html") or body.startswith("<html"), (
            f"{path} 在没有令牌时返回了 200，且内容不像 SPA 外壳：{body[:80]!r}"
        )
    else:
        assert response.status_code in (401, 403, 404), f"{path} -> {response.status_code}"


def test_the_backup_namespace_stays_protected_under_every_spelling(client: TestClient) -> None:
    """`/admin/backup/*` holds credentials and is excluded from the browser shell.

    Kept apart from the table above because a regression here is the one that leaks an
    archive rather than the one that merely mislabels a page.
    """
    for path in ("/admin/backup/list", "/admin/backup%2flist", "/admin/backup/./list", "/ADMIN/BACKUP/LIST"):
        response = client.get(path)
        assert response.status_code in (401, 403), f"{path} -> {response.status_code} {response.text[:80]}"
