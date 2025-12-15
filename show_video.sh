#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
VIDEO_API_PORT="${VIDEO_API_PORT:-9200}"
VIDEO_FLOWER_PORT="${VIDEO_FLOWER_PORT:-5560}"
export PYTHONPATH="$ROOT_DIR/src"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[video-show] Missing executable: $1" >&2
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

echo "== Video Process Status =="
printf "%-18s %s\n" "Video API" "$(is_running "$RUN_DIR/video-api.pid")"
printf "%-18s %s\n" "Video Worker" "$(is_running "$RUN_DIR/video-worker.pid")"
printf "%-18s %s\n" "Video Flower" "$(is_running "$RUN_DIR/video-flower.pid")"
printf "%-18s %s\n" "API /healthz" "$(check_http "http://127.0.0.1:${VIDEO_API_PORT}/healthz")"
printf "%-18s %s\n" "Flower UI" "http://127.0.0.1:${VIDEO_FLOWER_PORT}"
