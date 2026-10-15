"""SQLite 平台库备份与恢复。

备份是运维功能的最后防线，但它本身不能成为一条注入路径。这里显式限制备份名、
拒绝归档目录穿越，并且只按精确成员名读取 tar；不解压整个归档。

备份包含数据源连接串、密码哈希和业务元数据，因此恢复接口必须保持管理员权限，
备份文件默认以 `0600` 权限落盘。
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import sqlite3
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import PlatformContext, PlatformDb

logger = logging.getLogger(__name__)

# 环境变量在 import 时求值，使部署可以通过常规配置移动备份目录。
# 目录本身延迟创建：导入一个库不应隐式写文件系统。
BACKUP_DIR = Path(os.environ.get("ONTOLOGY_BACKUP_DIR", Path.home() / ".aletheia" / "backups")).expanduser()

BACKUP_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,119}$")
CONFIG_MEMBER_SUFFIX = "config.json"
DATABASE_MEMBER_SUFFIX = "platform.db"


class BackupError(ValueError):
    """备份名、归档成员或平台库不适合执行请求的操作。"""


def _safe_name(backup_name: str) -> str:
    """校验备份名，使其永远只能指向备份目录下的一个普通归档文件。"""
    if not BACKUP_NAME_PATTERN.fullmatch(backup_name):
        raise BackupError(
            "备份名不合法：需为 1-120 位字母／数字／下划线／连字符／点，且以字母或数字开头（不能包含路径分隔符）。"
        )
    return backup_name


def _backup_directory(backup_dir: Path | str | None = None) -> Path:
    return Path(backup_dir or BACKUP_DIR).expanduser()


def _sqlite_path(platform_db: PlatformDb) -> Path:
    """解析平台库位置。

    备份是物理 SQLite 快照，不支持把 PostgreSQL/MySQL context 混进这个实现；
    显式报错比生成一个损坏的归档更安全。
    """
    if isinstance(platform_db, PlatformContext):
        if platform_db.db_type != "sqlite":
            raise BackupError("内置备份仅支持 SQLite 平台库；服务端数据库请使用其原生备份工具。")
        path = Path(platform_db.connection_uri)
    elif isinstance(platform_db, Path):
        path = platform_db
    elif isinstance(platform_db, str):
        path = Path(platform_db)
    else:
        raise BackupError("platform_db 必须是 SQLite 路径或 PlatformContext。")
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"平台库不存在: {path}")
    return path


def create_backup(
    platform_db: PlatformDb,
    backup_name: str | None = None,
    *,
    backup_dir: Path | str | None = None,
) -> dict[str, Any]:
    """先产出一致的 SQLite 快照，再原子写入 tar.gz。"""
    name = _safe_name(backup_name or f"backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}")
    db_path = _sqlite_path(platform_db)
    directory = _backup_directory(backup_dir)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"{name}.tar.gz"

    snapshot = directory / f".{name}.snapshot"
    temp_archive = directory / f".{name}.tmp"
    try:
        with sqlite3.connect(db_path) as source, sqlite3.connect(snapshot) as target:
            source.backup(target)

        from . import __version__

        config = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "database": db_path.name,
            "version": __version__,
        }
        config_bytes = json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8")
        with tarfile.open(temp_archive, "w:gz", format=tarfile.PAX_FORMAT) as tar:
            database_info = tar.gettarinfo(snapshot, arcname=f"{name}/{DATABASE_MEMBER_SUFFIX}")
            database_info.mode = 0o600
            with snapshot.open("rb") as source_file:
                tar.addfile(database_info, source_file)

            config_info = tarfile.TarInfo(name=f"{name}/{CONFIG_MEMBER_SUFFIX}")
            config_info.size = len(config_bytes)
            config_info.mode = 0o600
            tar.addfile(config_info, io.BytesIO(config_bytes))

        os.chmod(temp_archive, 0o600)
        os.replace(temp_archive, archive)
    finally:
        snapshot.unlink(missing_ok=True)
        temp_archive.unlink(missing_ok=True)

    logger.info("备份创建成功: %s", archive)
    _record(platform_db, "create_backup", name, {"path": str(archive), "size": archive.stat().st_size})
    return {
        "name": name,
        "path": str(archive),
        "size": archive.stat().st_size,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _record(platform_db: PlatformDb, action: str, target: str, detail: dict[str, Any]) -> None:
    """Leave a trace of a backup operation in the platform database's own audit log.

    Both operations were invisible to it: 41 other places write an audit row and this module
    wrote none. That is backwards for the pair that carries the most consequence -- a restore
    *replaces* the database, and afterwards the audit log inside it is the one from the backup,
    with nothing saying a restore happened at all. An auditor asking "when was this database
    replaced, and with what" had only the process log, which rotates.

    Never raises: the operation has already happened by the time this is called, and a failed
    audit write must not turn a completed restore into a reported failure.
    """
    from .database import connect
    from .tracing import current_request_id

    try:
        with connect(platform_db) as conn:
            conn.execute(
                "insert into audit_log (actor, action, target_type, target_id, detail) values (?, ?, ?, ?, ?)",
                (
                    "admin-api",
                    action,
                    "backup",
                    target,
                    json.dumps({**detail, "requestId": current_request_id()}, ensure_ascii=False),
                ),
            )
    except Exception as error:  # an audit failure must not undo the operation it describes
        logger.warning("审计写入失败（%s %s）: %s", action, target, error)


def list_backups(*, backup_dir: Path | str | None = None) -> list[dict[str, Any]]:
    """列出归档与其配置元数据；损坏的归档跳过并记录警告，不让列表接口整体失败。"""
    directory = _backup_directory(backup_dir)
    if not directory.exists():
        return []

    backups: list[dict[str, Any]] = []
    for archive in directory.glob("*.tar.gz"):
        name = archive.name.removesuffix(".tar.gz")
        try:
            with tarfile.open(archive, "r:gz") as tar:
                config_file = tar.extractfile(f"{name}/{CONFIG_MEMBER_SUFFIX}")
                if config_file is None:
                    raise BackupError("缺少 config.json")
                config = json.loads(config_file.read().decode("utf-8"))
        except (tarfile.TarError, KeyError, UnicodeError, json.JSONDecodeError, BackupError) as error:
            logger.warning("读取备份失败 %s: %s", archive.name, error)
            continue
        backups.append(
            {
                "name": name,
                "path": str(archive),
                "size": archive.stat().st_size,
                "created_at": config.get("created_at", archive.stat().st_mtime),
            }
        )
    return sorted(backups, key=lambda item: str(item["created_at"]), reverse=True)


def backup_archive_path(
    backup_name: str,
    *,
    backup_dir: Path | str | None = None,
) -> Path:
    """返回可下载归档的准确路径；调用方不应自行拼接用户输入。"""
    name = _safe_name(backup_name)
    directory = _backup_directory(backup_dir)
    archive = directory / f"{name}.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(f"备份文件不存在: {name}")
    if archive.parent != directory:
        raise BackupError("备份路径不在备份目录内")
    return archive


def restore_backup(
    backup_name: str,
    platform_db: PlatformDb,
    *,
    backup_dir: Path | str | None = None,
) -> dict[str, Any]:
    """把归档中的数据库成员原子恢复到目标路径。

    不调用 `extractall`：成员名在归档内由我们校验，不会受压缩包内路径影响。
    恢复前仍应停止服务；正在运行的进程可能持有旧数据库连接。

    **恢复之前先给当前平台库留一份快照。** 恢复是不可逆的：选错了一份归档，
    原来的库就被换掉了，而选错的方式很平凡——备份列表里有几十个名字相近的归档，
    界面上只能凭名字与时间辨认。快照失败则**拒绝恢复**（fail-closed），
    因为「先把现在这一份弄丢，再换上一份可能不对的」比不做这次恢复更糟。
    """
    name = _safe_name(backup_name)
    directory = _backup_directory(backup_dir)
    archive = directory / f"{name}.tar.gz"
    if not archive.is_file():
        raise FileNotFoundError(f"备份文件不存在: {name}")

    target = _sqlite_path(platform_db)
    safety_name = f"before-restore-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    try:
        create_backup(platform_db, safety_name, backup_dir=directory)
    except Exception as error:
        raise BackupError(
            f"恢复前的安全快照未能生成（{error}），因此没有执行恢复：恢复会直接替换当前平台库，先保住它才谈得上换。"
        ) from error

    temp_target: Path | None = None
    try:
        with tarfile.open(archive, "r:gz") as tar:
            database_member = tar.extractfile(f"{name}/{DATABASE_MEMBER_SUFFIX}")
            if database_member is None:
                raise BackupError("备份中找不到数据库文件")

            fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.restore-", dir=target.parent)
            temp_target = Path(temp_name)
            with os.fdopen(fd, "wb") as output:
                output.write(database_member.read())
                output.flush()
                os.fsync(output.fileno())
            os.chmod(temp_target, 0o600)

            with temp_target.open("rb") as restored:
                if restored.read(16) != b"SQLite format 3\x00":
                    raise BackupError("备份中的数据库不是有效的 SQLite 文件")

        os.replace(temp_target, target)
        temp_target = None
        for sidecar in (Path(f"{target}-wal"), Path(f"{target}-shm")):
            sidecar.unlink(missing_ok=True)
    finally:
        if temp_target is not None:
            temp_target.unlink(missing_ok=True)

    restored_at = datetime.now(timezone.utc).isoformat()
    logger.info("备份恢复成功: %s -> %s（恢复前快照 %s）", name, target, safety_name)
    # Written after the swap, so the record lives in the database that is now in use: the
    # replacement is the one event this log itself most needs to survive.
    _record(platform_db, "restore_backup", name, {"restoredAt": restored_at, "safetyCopy": safety_name})
    return {
        "name": name,
        "restored_at": restored_at,
        "database": str(target),
        # Named in the response so the screen can say it: the way back is only useful to
        # somebody who knows it exists.
        "safetyCopy": safety_name,
    }
