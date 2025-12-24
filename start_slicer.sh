#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${SLICER_API_PORT:-8100}"
FLOWER_PORT="${SLICER_FLOWER_PORT:-5556}"
PROM_PORT="${SLICER_PROM_PORT:-9093}"
CELERY_LOG_LEVEL="${SLICER_CELERY_LOG_LEVEL:-info}"
HOST_ID="${HOSTNAME:-$(hostname)}"
SLICER_WORKER_NAME="${SLICER_WORKER_NAME:-docker-slicer-service@${HOST_ID}}"
export PYTHONPATH="$ROOT_DIR/src"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Default env overrides (can be overridden by caller)
export SLICE_celery__broker_url="${SLICE_celery__broker_url:-redis://localhost:6379/0}"
export SLICE_celery__result_backend="${SLICE_celery__result_backend:-redis://localhost:6379/1}"
export SLICE_monitoring__prometheus_port="${SLICE_monitoring__prometheus_port:-$PROM_PORT}"
export SLICE_monitoring__enable_metrics="${SLICE_monitoring__enable_metrics:-true}"

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
  local name="$1" pid_file="$2" log_file="$3"; shift 3
  if is_running "$pid_file"; then
    echo "[start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[start] $name PID $(<"$pid_file")"
}

start_component "Slicer API" "$RUN_DIR/slicer-api.pid" "$LOG_DIR/slicer-api.log" \
  "$VENV_BIN/uvicorn" slicer_service.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "Slicer Worker" "$RUN_DIR/slicer-worker.pid" "$LOG_DIR/slicer-worker.log" \
  "$VENV_BIN/celery" -A slicer_service.celery_app:celery_app worker -l "$CELERY_LOG_LEVEL" -n "$SLICER_WORKER_NAME"

# Flower disabled outside rag_converter container
# start_component "Slicer Flower" "$RUN_DIR/slicer-flower.pid" "$LOG_DIR/slicer-flower.log" \
#   "$VENV_BIN/celery" -A slicer_service.celery_app:celery_app flower --port="$FLOWER_PORT"

echo "[start] Slicer components launched. Logs: $LOG_DIR"
