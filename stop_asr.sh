#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[asr-stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[asr-stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[asr-stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "ASR API" "$RUN_DIR/asr-api.pid"
stop_component "ASR Worker" "$RUN_DIR/asr-worker.pid"
stop_component "ASR Flower" "$RUN_DIR/asr-flower.pid"

echo "[asr-stop] ASR shutdown completed."
