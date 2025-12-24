#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
FLOWER_PORT="${VECTOR_FLOWER_PORT:-5562}"
CELERY_LOG_LEVEL="${VECTOR_CELERY_LOG_LEVEL:-info}"
VECTOR_WORKER_QUEUES="${VECTOR_WORKER_QUEUES:-vector}"
HOST_ID="${HOSTNAME:-$(hostname)}"
VECTOR_WORKER_NAME="${VECTOR_WORKER_NAME:-docker-vector-service@${HOST_ID}}"
export PYTHONPATH="$ROOT_DIR/src"

# Load local environment overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
  FLOWER_PORT="${VECTOR_FLOWER_PORT:-$FLOWER_PORT}"
  CELERY_LOG_LEVEL="${VECTOR_CELERY_LOG_LEVEL:-$CELERY_LOG_LEVEL}"
  VECTOR_WORKER_QUEUES="${VECTOR_WORKER_QUEUES:-$VECTOR_WORKER_QUEUES}"
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Default env overrides (caller can override)
export VECTOR_celery__broker_url="${VECTOR_celery__broker_url:-redis://localhost:6379/0}"
export VECTOR_celery__result_backend="${VECTOR_celery__result_backend:-redis://localhost:6379/1}"

SCRIPT_TAG="vector-start"
resolve_bin() {
  local name="$1"
  for cand in "/opt/venv/bin/$name" "$ROOT_DIR/.venv/bin/$name" "$(command -v "$name" 2>/dev/null)"; do
    if [[ -n "$cand" && -x "$cand" ]]; then
      echo "$cand"
      return
    fi
  done
  echo "[$SCRIPT_TAG] Missing executable: $name" >&2
  exit 1
}

CELERY=$(resolve_bin celery)

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
    echo "[vector-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[vector-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[vector-start] $name PID $(<"$pid_file")"
}

start_component "Vector Worker" "$RUN_DIR/vector-worker.pid" "$LOG_DIR/vector-worker.log" \
  "$CELERY" -A vector_service.celery_app:vector_celery worker -l "$CELERY_LOG_LEVEL" -Q "$VECTOR_WORKER_QUEUES" -n "$VECTOR_WORKER_NAME"

# Flower disabled outside rag_converter container
# start_component "Vector Flower" "$RUN_DIR/vector-flower.pid" "$LOG_DIR/vector-flower.log" \
#   "$CELERY" -A vector_service.celery_app:vector_celery flower --port="$FLOWER_PORT"

echo "[vector-start] Vector components launched. Logs: $LOG_DIR"
