#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
API_PORT="${MM_API_PORT:-8300}"
FLOWER_PORT="${MM_FLOWER_PORT:-5559}"
export PYTHONPATH="$ROOT_DIR/src"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[mm-show] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/python"

is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(<"$pid_file")
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "running (PID $pid)"
      return
    fi
  fi
  echo "stopped"
}

check_http() {
  local url="$1"
  if command -v curl >/dev/null 2>&1 && curl -fsS "$url" >/dev/null 2>&1; then
    echo "healthy"
  else
    echo "unreachable"
  fi
}

echo "== Multimodal Process Status =="
printf "%-22s %s\n" "Multimodal API" "$(is_running "$RUN_DIR/mm-api.pid")"
printf "%-22s %s\n" "Multimodal Worker" "$(is_running "$RUN_DIR/mm-worker.pid")"
printf "%-22s %s\n" "Multimodal Flower" "$(is_running "$RUN_DIR/mm-flower.pid")"
printf "%-22s %s\n" "API /healthz" "$(check_http "http://127.0.0.1:${API_PORT}/healthz")"
printf "%-22s %s\n" "API docs" "http://127.0.0.1:${API_PORT}/api/v1/docs"
printf "%-22s %s\n" "Flower UI" "http://127.0.0.1:${FLOWER_PORT}"
