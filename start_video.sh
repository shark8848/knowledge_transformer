#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
VIDEO_API_PORT="${VIDEO_API_PORT:-9200}"
VIDEO_FLOWER_PORT="${VIDEO_FLOWER_PORT:-5560}"
VIDEO_CELERY_LOG_LEVEL="${VIDEO_CELERY_LOG_LEVEL:-info}"
VIDEO_QUEUE="${VIDEO_QUEUE:-video}"
export PYTHONPATH="$ROOT_DIR/src"

# Load .env if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +a
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[video-start] Missing executable: $1" >&2
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
    echo "[video-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[video-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[video-start] $name PID $(<"$pid_file")"
}

start_component "Video API" "$RUN_DIR/video-api.pid" "$LOG_DIR/video-api.log" \
  "$VENV_BIN/uvicorn" video_service.app:app --host 0.0.0.0 --port "$VIDEO_API_PORT"

start_component "Video Worker" "$RUN_DIR/video-worker.pid" "$LOG_DIR/video-worker.log" \
  "$VENV_BIN/celery" -A video_service.celery_app:video_celery worker -l "$VIDEO_CELERY_LOG_LEVEL" \
  -Q "$VIDEO_QUEUE" -n video@%h

start_component "Video Flower" "$RUN_DIR/video-flower.pid" "$LOG_DIR/video-flower.log" \
  "$VENV_BIN/celery" -A video_service.celery_app:video_celery flower --port="$VIDEO_FLOWER_PORT" --url_prefix="/video-flower"

echo "[video-start] Video components launched. Logs: $LOG_DIR"
