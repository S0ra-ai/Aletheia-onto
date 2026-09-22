#!/bin/bash
# Production startup script for Aletheia platform

set -e

# Configuration
HOST="${ONTOLOGY_HOST:-0.0.0.0}"
PORT="${ONTOLOGY_PORT:-8000}"
WORKERS="${ONTOLOGY_WORKERS:-4}"
LOG_LEVEL="${ONTOLOGY_LOG_LEVEL:-info}"

# Check required environment variables
if [ -z "$ONTOLOGY_ADMIN_PASSWORD" ]; then
    echo "警告: ONTOLOGY_ADMIN_PASSWORD 未设置，将生成随机密码"
fi

# Create the configured state directory if one was supplied. The CLI resolves its own
# default (`~/.aletheia`) when this variable is absent; creating a relative `data/`
# directory here would make an installed deployment depend on its working directory.
if [ -n "${ONTOLOGY_DATA_DIR:-}" ]; then
    mkdir -p "$ONTOLOGY_DATA_DIR"
fi

# Start the server
echo "启动 Aletheia 平台..."
echo "  主机: $HOST"
echo "  端口: $PORT"
echo "  工作进程: $WORKERS"
echo "  日志级别: $LOG_LEVEL"

# Keep the production script on the same seam as `aletheia serve`: it performs the
# deployment preflight before exposing a non-loopback listener and keeps platform-db
# path handling identical to the CLI.
exec aletheia serve \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level "$LOG_LEVEL"
