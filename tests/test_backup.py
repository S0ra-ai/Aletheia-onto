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
