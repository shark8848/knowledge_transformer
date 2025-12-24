#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
PIPELINE_PORT="${PIPELINE_PORT:-9100}"
PIPELINE_LOG_LEVEL="${PIPELINE_LOG_LEVEL:-info}"
PIPELINE_FLOWER_PORT="${PIPELINE_FLOWER_PORT:-5557}"
PIPELINE_QUEUE="${PIPELINE_QUEUE:-pipeline}"
HOST_ID="${HOSTNAME:-$(hostname)}"
PIPELINE_WORKER_NAME="${PIPELINE_WORKER_NAME:-docker-pipeline-service@${HOST_ID}}"

# Optional: start dependent services (converter & slicer) if scripts exist.
DEPEND_START_CONVERTER="${DEPEND_START_CONVERTER:-true}"
DEPEND_START_SLICER="${DEPEND_START_SLICER:-true}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[pipeline-start] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/uvicorn"
require_bin "$VENV_BIN/celery"
require_bin "$VENV_BIN/python"

start_dep_script() {
  local script_path="$1" name="$2"
  if [[ -x "$script_path" ]]; then
    echo "[pipeline-start] Starting dependency: $name ($script_path)"
    "$script_path" || echo "[pipeline-start] Warning: $name failed to start"
  else
    echo "[pipeline-start] Skipped dependency $name (script not found or not executable)"
  fi
}

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
    echo "[pipeline-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[pipeline-start] Launching $name ..."
  nohup "${cmd[@]}" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[pipeline-start] $name PID $(<"$pid_file")"
}

# Start dependencies first
if [[ "$DEPEND_START_CONVERTER" == "true" ]]; then
  start_dep_script "$ROOT_DIR/start_converter.sh" "converter"
fi
if [[ "$DEPEND_START_SLICER" == "true" ]]; then
  start_dep_script "$ROOT_DIR/start_slicer.sh" "slicer"
fi

# Pipeline Celery worker
start_component "Pipeline Celery" "$RUN_DIR/pipeline-celery.pid" "$LOG_DIR/pipeline-celery.log" \
  "$VENV_BIN/celery" -A pipeline_service.celery_app:pipeline_celery worker -l "$PIPELINE_LOG_LEVEL" \
  -Q "$PIPELINE_QUEUE" -n "$PIPELINE_WORKER_NAME"

# Pipeline API
start_component "Pipeline API" "$RUN_DIR/pipeline-api.pid" "$LOG_DIR/pipeline-api.log" \
  "$VENV_BIN/uvicorn" pipeline_service.app:app --host 0.0.0.0 --port "$PIPELINE_PORT"

# Pipeline Flower disabled outside rag_converter container
# start_component "Pipeline Flower" "$RUN_DIR/pipeline-flower.pid" "$LOG_DIR/pipeline-flower.log" \
#   "$VENV_BIN/celery" -A pipeline_service.celery_app:pipeline_celery flower --port="$PIPELINE_FLOWER_PORT" --url_prefix="/pipeline-flower"

echo "[pipeline-start] Pipeline components launched. Logs: $LOG_DIR"
