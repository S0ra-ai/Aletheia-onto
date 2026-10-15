"""Tests for the backup module."""

from __future__ import annotations

import importlib
import io
import sqlite3
import tarfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ontology_platform.access_policy import CAP_ADMIN, required_capability
from ontology_platform.backup import (
    BackupError,
    backup_archive_path,
    create_backup,
    list_backups,
    restore_backup,
)


def test_list_backups_empty(tmp_path: Path) -> None:
    """A fresh deployment has no backups to show."""
    assert list_backups(backup_dir=tmp_path / "missing") == []


def test_backup_round_trip_restores_a_consistent_sqlite_snapshot(tmp_path: Path) -> None:
    """A backup is usable only if restore returns the exact committed state."""
    db_path = tmp_path / "platform.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("create table evidence (value text)")
        conn.execute("insert into evidence values ('before')")

    created = create_backup(str(db_path), "runtime", backup_dir=tmp_path / "backups")
    assert Path(created["path"]).stat().st_mode & 0o777 == 0o600
    assert [item["name"] for item in list_backups(backup_dir=tmp_path / "backups")] == ["runtime"]

    with sqlite3.connect(db_path) as conn:
        conn.execute("update evidence set value = 'after'")

    restore_backup("runtime", str(db_path), backup_dir=tmp_path / "backups")
    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select value from evidence").fetchone()[0] == "before"


def test_download_path_is_validated_and_admin_only(tmp_path: Path) -> None:
    """Backups carry credentials, so download is never a generic read."""
    db_path = tmp_path / "platform.sqlite3"
    db_path.touch()
    backup_dir = tmp_path / "backups"
    created = create_backup(str(db_path), "download-me", backup_dir=backup_dir)

    archive = backup_archive_path("download-me", backup_dir=backup_dir)
    assert archive == Path(created["path"])
    with pytest.raises(BackupError):
        backup_archive_path("nested/name", backup_dir=backup_dir)

    assert required_capability("GET", "/admin/backup/list") == CAP_ADMIN
    assert required_capability("GET", "/admin/backup/download/download-me") == CAP_ADMIN


def test_backup_download_endpoint_streams_authenticated_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The admin backup page can download through the same bearer-token transport."""
    platform_db = tmp_path / "platform.sqlite3"
    backup_dir = tmp_path / "backups"
    monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
    monkeypatch.setenv("ONTOLOGY_ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "admin-password-123")

    import ontology_platform.api as api_module
    import ontology_platform.backup as backup_module
    import ontology_platform.database as database_module

    database_module._platform_adapter = None
    monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
    api_module = importlib.reload(api_module)
    monkeypatch.setattr(api_module, "DEFAULT_PLATFORM_DB", platform_db)
    monkeypatch.setattr(backup_module, "BACKUP_DIR", backup_dir)

    with TestClient(api_module.app) as client:
        assert client.get("/admin/backup/list").status_code == 401
        token = client.post(
            "/auth/login",
            json={"username": "admin", "password": "admin-password-123"},
        ).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = client.post("/admin/backup/create", headers=headers)
        assert created.status_code == 200, created.text
        name = created.json()["name"]

        downloaded = client.get(f"/admin/backup/download/{name}", headers=headers)
        assert downloaded.status_code == 200
        assert downloaded.headers["content-type"] == "application/gzip"
        assert downloaded.headers["content-disposition"] == f'attachment; filename="{name}.tar.gz"'
        assert downloaded.content[:2] == b"\x1f\x8b"


def test_backup_names_cannot_escape_the_backup_directory(tmp_path: Path) -> None:
    """Names become part of filesystem paths and archive member names."""
    db_path = tmp_path / "platform.sqlite3"
    db_path.touch()
    for name in ("../escape", "/absolute", "nested/name", ".", ".."):
        with pytest.raises(BackupError):
            create_backup(str(db_path), name, backup_dir=tmp_path / "backups")


def test_restore_does_not_extract_archive_members_outside_the_target(tmp_path: Path) -> None:
    """A malicious archive must fail closed without writing its supplied path."""
    archive_dir = tmp_path / "backups"
    archive_dir.mkdir()
    with tarfile.open(archive_dir / "evil.tar.gz", "w:gz") as tar:
        payload = b"not a database"
        info = tarfile.TarInfo(name="../outside.sqlite3")
        info.size = len(payload)
        tar.addfile(info, io.BytesIO(payload))

    target = tmp_path / "platform.sqlite3"
    target.write_bytes(b"SQLite format 3\x00")
    outside = tmp_path / "outside.sqlite3"

    with pytest.raises((BackupError, KeyError)):
        restore_backup("evil", str(target), backup_dir=archive_dir)

    assert not outside.exists()
    assert target.read_bytes().startswith(b"SQLite format 3\x00")


class TestBackupRoutesDistinguishClientErrors:
    """A mistyped name is not a server fault.

    `download_platform_backup` already answered 404 for a name that does not exist; its
    sibling `restore_platform_backup` did not, so the one path a user reaches by mistyping
    answered 500. That tells them nothing and files a client mistake under server faults.
    """

    @pytest.fixture
    def client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
        platform_db = tmp_path / "platform.sqlite3"
        sqlite3.connect(platform_db).close()
        monkeypatch.setenv("ONTOLOGY_BACKUP_DIR", str(tmp_path / "backups"))
        monkeypatch.setenv("ONTOLOGY_ADMIN_PASSWORD", "admin-password-123")
        monkeypatch.setenv("ONTOLOGY_ALLOWED_ORIGINS", "http://localhost:3000")
        monkeypatch.delenv("ONTOLOGY_AUTH_DISABLED", raising=False)
        monkeypatch.delenv("ONTOLOGY_RATE_LIMIT_PER_MINUTE", raising=False)

        import ontology_platform.api as api_module
        import ontology_platform.backup as backup_module
        import ontology_platform.database as database_module

        database_module._platform_adapter = None
        monkeypatch.setattr(database_module, "DEFAULT_PLATFORM_DB", platform_db)
        monkeypatch.setattr(backup_module, "BACKUP_DIR", tmp_path / "backups")
        reloaded = importlib.reload(api_module)
        monkeypatch.setattr(reloaded, "DEFAULT_PLATFORM_DB", platform_db)
        try:
            with TestClient(reloaded.app) as test_client:
                token = test_client.post(
                    "/auth/login", json={"username": "admin", "password": "admin-password-123"}
                ).json()["token"]
                test_client.headers["Authorization"] = f"Bearer {token}"
                yield test_client
        finally:
            database_module._platform_adapter = None

    def test_restoring_a_missing_backup_is_a_404_not_a_500(self, client: TestClient) -> None:
        response = client.post("/admin/backup/restore/nope-does-not-exist")
        assert response.status_code == 404, response.text
        assert "不存在" in response.json()["detail"]

    def test_downloading_a_missing_backup_is_still_a_404(self, client: TestClient) -> None:
        """The sibling that was already correct, kept correct."""
        assert client.get("/admin/backup/download/nope-does-not-exist").status_code == 404

    @pytest.mark.parametrize("name", [".hidden", "-leading-dash"])
    def test_a_name_that_is_not_a_backup_name_is_a_400(self, client: TestClient, name: str) -> None:
        """A single path segment that the backup-name pattern refuses.

        Traversal attempts (`..`, `a/b`) never reach the handler -- the router rejects them
        first -- so testing those would be testing the router. What matters here is that a
        name which *does* reach `restore_backup` and is refused produces a 400 that says so.
        """
        response = client.post(f"/admin/backup/restore/{name}")
        assert response.status_code == 400, response.text
        assert "备份名不合法" in response.json()["detail"]
