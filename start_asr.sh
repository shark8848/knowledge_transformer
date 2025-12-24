#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${ASR_API_PORT:-8200}"
FLOWER_PORT="${ASR_FLOWER_PORT:-5558}"
CELERY_LOG_LEVEL="${ASR_CELERY_LOG_LEVEL:-info}"
ASR_WORKER_QUEUES="${ASR_WORKER_QUEUES:-asr,video_asr}"
HOST_ID="${HOSTNAME:-$(hostname)}"
ASR_WORKER_NAME="${ASR_WORKER_NAME:-docker-audio-service@${HOST_ID}}"
export PYTHONPATH="$ROOT_DIR/src"

mkdir -p "$RUN_DIR" "$LOG_DIR"

# Default env overrides (can be overridden by caller)
export ASR_celery__broker_url="${ASR_celery__broker_url:-redis://localhost:6379/0}"
export ASR_celery__result_backend="${ASR_celery__result_backend:-redis://localhost:6379/1}"

SCRIPT_TAG="asr-start"
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

UVICORN=$(resolve_bin uvicorn)
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
    echo "[asr-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[asr-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[asr-start] $name PID $(<"$pid_file")"
}

start_component "ASR API" "$RUN_DIR/asr-api.pid" "$LOG_DIR/asr-api.log" \
  "$UVICORN" asr_service.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "ASR Worker" "$RUN_DIR/asr-worker.pid" "$LOG_DIR/asr-worker.log" \
  "$CELERY" -A asr_service.celery_app:asr_celery worker -l "$CELERY_LOG_LEVEL" -Q "$ASR_WORKER_QUEUES" -n "$ASR_WORKER_NAME"

# Flower disabled outside rag_converter container
# start_component "ASR Flower" "$RUN_DIR/asr-flower.pid" "$LOG_DIR/asr-flower.log" \
#   "$CELERY" -A asr_service.celery_app:asr_celery flower --port="$FLOWER_PORT"

echo "[asr-start] ASR components launched. Logs: $LOG_DIR"
