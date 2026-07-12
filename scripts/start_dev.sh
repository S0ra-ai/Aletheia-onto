#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"
mkdir -p "$LOG_DIR"
STARTED_PIDS=()

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts=30
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS --max-time 1 "$url" >/dev/null 2>&1; then
      echo "[ok] $name: $url"
      return 0
    fi
    sleep 0.3
  done
  echo "[error] $name 启动失败，请查看 $LOG_DIR" >&2
  return 1
}

start_if_unavailable() {
  local name="$1"
  local url="$2"
  local pid_file="$3"
  local log_file="$4"
  shift 4
  if curl -fsS --max-time 1 "$url" >/dev/null 2>&1; then
    echo "[skip] $name 已在运行"
    return 0
  fi
  nohup "$@" >"$log_file" 2>&1 &
  local pid=$!
  echo "$pid" >"$pid_file"
  STARTED_PIDS+=("$pid")
  wait_for_url "$name" "$url"
}

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "[error] 未找到 $ROOT/.venv，请先安装 requirements.txt" >&2
  exit 1
fi

start_if_unavailable \
  "本体平台后端" \
  "http://127.0.0.1:8000/health" \
  "$RUN_DIR/platform-backend.pid" \
  "$LOG_DIR/platform-backend.log" \
  "$ROOT/.venv/bin/uvicorn" ontology_platform.api:app --app-dir "$ROOT/backend" --host 127.0.0.1 --port 8000

start_if_unavailable \
  "Word合同测试网关" \
  "http://127.0.0.1:8001/api/health" \
  "$RUN_DIR/contract-gateway.pid" \
  "$LOG_DIR/contract-gateway.log" \
  "$ROOT/.venv/bin/python" "$ROOT/test-projects/contract-system/backend/main.py"

start_if_unavailable \
  "本体平台前端" \
  "http://127.0.0.1:3000/" \
  "$RUN_DIR/platform-frontend.pid" \
  "$LOG_DIR/platform-frontend.log" \
  npm --prefix "$ROOT/frontend" run dev -- --host 127.0.0.1

echo ""
echo "开发环境已就绪："
echo "  平台: http://127.0.0.1:3000"
echo "  后端: http://127.0.0.1:8000"
echo "  网关: http://127.0.0.1:8001"
echo "停止命令: $ROOT/scripts/stop_dev.sh"

if [[ "${DEV_FOREGROUND:-0}" == "1" && ${#STARTED_PIDS[@]} -gt 0 ]]; then
  cleanup() {
    for pid in "${STARTED_PIDS[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
  }
  trap cleanup EXIT INT TERM
  echo "前台监督模式已启用，按 Ctrl+C 停止本次启动的进程。"
  wait "${STARTED_PIDS[@]}"
fi
