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
from ontology_platform.database import connect

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

    published = client.post(
        f"/ontologies/{ontology_id}/publish", json={"force": True}, headers=headers
    )
    assert published.status_code == 200, published.text

    again = client.post("/demo/bootstrap", json={}, headers=headers)
    assert again.status_code == 409, again.text
    assert "派生新版本" in again.json()["detail"]
