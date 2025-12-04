#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "FastAPI" "$RUN_DIR/api.pid"
stop_component "Celery" "$RUN_DIR/celery.pid"
stop_component "Flower" "$RUN_DIR/flower.pid"

echo "[stop] Shutdown sequence completed."
