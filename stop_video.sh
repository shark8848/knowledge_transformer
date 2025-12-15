#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[video-stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[video-stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[video-stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "Video API" "$RUN_DIR/video-api.pid"
stop_component "Video Worker" "$RUN_DIR/video-worker.pid"
stop_component "Video Flower" "$RUN_DIR/video-flower.pid"

echo "[video-stop] Video shutdown completed."
