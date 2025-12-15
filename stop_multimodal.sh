#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[mm-stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[mm-stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[mm-stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "Multimodal API" "$RUN_DIR/mm-api.pid"
stop_component "Multimodal Worker" "$RUN_DIR/mm-worker.pid"
stop_component "Multimodal Flower" "$RUN_DIR/mm-flower.pid"

echo "[mm-stop] Multimodal shutdown completed."
