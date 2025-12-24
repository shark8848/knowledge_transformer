#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${MM_API_PORT:-8300}"
FLOWER_PORT="${MM_FLOWER_PORT:-5559}"
CELERY_LOG_LEVEL="${MM_CELERY_LOG_LEVEL:-info}"
MM_WORKER_QUEUES="${MM_WORKER_QUEUES:-mm,video_vision}"
HOST_ID="${HOSTNAME:-$(hostname)}"
MM_WORKER_NAME="${MM_WORKER_NAME:-docker-multimodal-service@${HOST_ID}}"
export PYTHONPATH="$ROOT_DIR/src"

# Load local environment overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Default env overrides (can be overridden by caller)
export MM_celery__broker_url="${MM_celery__broker_url:-redis://localhost:6379/0}"
export MM_celery__result_backend="${MM_celery__result_backend:-redis://localhost:6379/1}"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[mm-start] Missing executable: $1" >&2
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
  local name="$1" pid_file="$2" log_file="$3"; shift 3
  if is_running "$pid_file"; then
    echo "[mm-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[mm-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[mm-start] $name PID $(<"$pid_file")"
}

start_component "Multimodal API" "$RUN_DIR/mm-api.pid" "$LOG_DIR/mm-api.log" \
  "$VENV_BIN/uvicorn" multimodal_service.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "Multimodal Worker" "$RUN_DIR/mm-worker.pid" "$LOG_DIR/mm-worker.log" \
  "$VENV_BIN/celery" -A multimodal_service.celery_app:mm_celery worker -l "$CELERY_LOG_LEVEL" -Q "$MM_WORKER_QUEUES" -n "$MM_WORKER_NAME"

# Flower disabled outside rag_converter container
# start_component "Multimodal Flower" "$RUN_DIR/mm-flower.pid" "$LOG_DIR/mm-flower.log" \
#   "$VENV_BIN/celery" -A multimodal_service.celery_app:mm_celery flower --port="$FLOWER_PORT"

echo "[mm-start] Multimodal components launched. Logs: $LOG_DIR"
