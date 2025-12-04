#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
CONFIG_FILE="${RAG_CONFIG_FILE:-$ROOT_DIR/config/settings.yaml}"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${API_PORT:-8000}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

FLOWER_PORT="${FLOWER_PORT:-5555}"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[start] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/uvicorn"
require_bin "$VENV_BIN/celery"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  rm -f "$pid_file"
  return 1
}

start_component() {
  local name="$1" pid_file="$2" log_file="$3" cmd=("${@:4}")
  if is_running "$pid_file"; then
    echo "[start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[start] Launching $name ..."
  RAG_CONFIG_FILE="$CONFIG_FILE" nohup "${cmd[@]}" \
    >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[start] $name PID $(<"$pid_file")"
}

start_component "FastAPI" "$RUN_DIR/api.pid" "$LOG_DIR/api.log" \
  "$VENV_BIN/uvicorn" rag_converter.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "Celery" "$RUN_DIR/celery.pid" "$LOG_DIR/celery.log" \
  "$VENV_BIN/celery" -A rag_converter.celery_app.celery_app worker -l "$CELERY_LOG_LEVEL"

start_component "Flower" "$RUN_DIR/flower.pid" "$LOG_DIR/flower.log" \
  "$VENV_BIN/celery" -A rag_converter.celery_app.celery_app flower --port="$FLOWER_PORT" --url_prefix="/flower"

echo "[start] All components launched. Logs stored in $LOG_DIR"
