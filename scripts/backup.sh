#!/bin/bash
# 本地 SQLite 平台库的自动备份脚本。
#
# 服务端数据库（PostgreSQL／MySQL）必须用其原生备份工具；这个脚本只处理
# aletheia-onto 的默认嵌入式库，避免把不兼容的连接交给物理备份实现。

set -e

# 与 deployment preflight 一样，运维脚本不猜测数据库位置。
PLATFORM_DB="${ONTOLOGY_PLATFORM_DB_FILE:?必须设置 ONTOLOGY_PLATFORM_DB_FILE}"
BACKUP_DIR="${ONTOLOGY_BACKUP_DIR:?必须设置 ONTOLOGY_BACKUP_DIR}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="backup_${TIMESTAMP}"

echo "=== Aletheia 自动备份 ==="
echo "时间: $(date)"
echo "备份到: $BACKUP_DIR"

# 创建备份目录
mkdir -p "$BACKUP_DIR"

# 直接调用随包发布的备份实现，不经过 HTTP，因此也不需要在 cron 中保存管理员令牌。
# `python3`, not `python`: this script runs from cron, whose PATH is minimal and where
# `python` frequently does not exist -- the failure was `line 25: python: command not found`,
# after the script had already announced the backup it was about to make. Point it at a
# virtualenv interpreter with PYTHON_BIN when the platform is installed in one.
PYTHON_BIN="${PYTHON_BIN:-python3}"
"$PYTHON_BIN" - "$PLATFORM_DB" "$BACKUP_NAME" "$BACKUP_DIR" <<'PY'
import sys

try:
    from ontology_platform.backup import create_backup
except ModuleNotFoundError:
    # A bare traceback in a cron log names the symptom and not the cause. The two causes are:
    # the platform is not installed for this interpreter, or PYTHON_BIN points at the wrong
    # one -- and both are one line to fix once the message says so.
    raise SystemExit(
        "备份失败：这个解释器里没有 ontology_platform 包。\n"
        "  要么装平台：pip install aletheia-onto（或 pip install -e 平台源码目录）\n"
        "  要么指对解释器：PYTHON_BIN=/path/to/venv/bin/python 再运行本脚本\n"
        f"  当前解释器：{sys.executable}"
    )

platform_db, backup_name, backup_dir = sys.argv[1:]
result = create_backup(platform_db, backup_name, backup_dir=backup_dir)
print(f"备份创建: {result['path']} ({result['size']} bytes)")
PY

# 清理旧备份
echo "清理 $RETENTION_DAYS 天前的备份..."
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

echo "备份完成!"
