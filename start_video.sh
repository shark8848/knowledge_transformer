#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
VIDEO_API_PORT="${VIDEO_API_PORT:-9200}"
VIDEO_FLOWER_PORT="${VIDEO_FLOWER_PORT:-5560}"
VIDEO_CELERY_LOG_LEVEL="${VIDEO_CELERY_LOG_LEVEL:-info}"
VIDEO_QUEUE="${VIDEO_QUEUE:-video}"
HOST_ID="${HOSTNAME:-$(hostname)}"
VIDEO_WORKER_NAME="${VIDEO_WORKER_NAME:-docker-video-service@${HOST_ID}}"
export PYTHONPATH="$ROOT_DIR/src"

SCRIPT_TAG="video-start"
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

mkdir -p "$RUN_DIR" "$LOG_DIR"

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
  "$UVICORN" video_service.app:app --host 0.0.0.0 --port "$VIDEO_API_PORT"

start_component "Video Worker" "$RUN_DIR/video-worker.pid" "$LOG_DIR/video-worker.log" \
  "$CELERY" -A video_service.celery_app:video_celery worker -l "$VIDEO_CELERY_LOG_LEVEL" \
  -Q "$VIDEO_QUEUE" -n "$VIDEO_WORKER_NAME"

# Flower disabled outside rag_converter container
# start_component "Video Flower" "$RUN_DIR/video-flower.pid" "$LOG_DIR/video-flower.log" \
#   "$CELERY" -A video_service.celery_app:video_celery flower --port="$VIDEO_FLOWER_PORT" --url_prefix="/video-flower"

echo "[video-start] Video components launched. Logs: $LOG_DIR"
