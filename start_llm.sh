#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
FLOWER_PORT="${LLM_FLOWER_PORT:-5560}"
CELERY_LOG_LEVEL="${LLM_CELERY_LOG_LEVEL:-info}"
LLM_WORKER_QUEUES="${LLM_WORKER_QUEUES:-llm}"
export PYTHONPATH="$ROOT_DIR/src"

# Load local environment overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
  FLOWER_PORT="${LLM_FLOWER_PORT:-$FLOWER_PORT}"
  CELERY_LOG_LEVEL="${LLM_CELERY_LOG_LEVEL:-$CELERY_LOG_LEVEL}"
  LLM_WORKER_QUEUES="${LLM_WORKER_QUEUES:-$LLM_WORKER_QUEUES}"
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Default env overrides (caller can override)
export LLM_celery__broker_url="${LLM_celery__broker_url:-redis://localhost:6379/0}"
export LLM_celery__result_backend="${LLM_celery__result_backend:-redis://localhost:6379/1}"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[llm-start] Missing executable: $1" >&2
    exit 1
  fi
}

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
    echo "[llm-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[llm-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[llm-start] $name PID $(<"$pid_file")"
}

start_component "LLM Worker" "$RUN_DIR/llm-worker.pid" "$LOG_DIR/llm-worker.log" \
  "$VENV_BIN/celery" -A llm_service.celery_app:llm_celery worker -l "$CELERY_LOG_LEVEL" -Q "$LLM_WORKER_QUEUES"

start_component "LLM Flower" "$RUN_DIR/llm-flower.pid" "$LOG_DIR/llm-flower.log" \
  "$VENV_BIN/celery" -A llm_service.celery_app:llm_celery flower --port="$FLOWER_PORT"

echo "[llm-start] LLM components launched. Logs: $LOG_DIR"
