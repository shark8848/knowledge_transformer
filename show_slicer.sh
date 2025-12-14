#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
API_PORT="${SLICER_API_PORT:-8100}"
FLOWER_PORT="${SLICER_FLOWER_PORT:-5556}"
PROM_PORT="${SLICER_PROM_PORT:-9093}"
export PYTHONPATH="$ROOT_DIR/src"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[show] Missing executable: $1" >&2
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

echo "== Slicer Process Status =="
printf "%-18s %s\n" "Slicer API" "$(is_running "$RUN_DIR/slicer-api.pid")"
printf "%-18s %s\n" "Slicer Worker" "$(is_running "$RUN_DIR/slicer-worker.pid")"
printf "%-18s %s\n" "Slicer Flower" "$(is_running "$RUN_DIR/slicer-flower.pid")"
printf "%-18s %s\n" "API /healthz" "$(check_http "http://127.0.0.1:${API_PORT}/healthz")"
printf "%-18s %s\n" "API /metrics" "http://127.0.0.1:${API_PORT}/metrics"
printf "%-18s %s\n" "Worker metrics" "http://127.0.0.1:${PROM_PORT}/metrics"
printf "%-18s %s\n" "Flower UI" "http://127.0.0.1:${FLOWER_PORT}"
