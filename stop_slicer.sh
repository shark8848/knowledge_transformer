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

stop_component "Slicer API" "$RUN_DIR/slicer-api.pid"
stop_component "Slicer Worker" "$RUN_DIR/slicer-worker.pid"
stop_component "Slicer Flower" "$RUN_DIR/slicer-flower.pid"

echo "[stop] Slicer shutdown completed."
