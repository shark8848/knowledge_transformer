#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[converter-stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[converter-stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[converter-stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "Converter FastAPI" "$RUN_DIR/api.pid"
stop_component "Converter Celery" "$RUN_DIR/celery.pid"
stop_component "Converter Flower" "$RUN_DIR/flower.pid"
stop_component "TestReport" "$RUN_DIR/test-report.pid"
stop_component "APIDocs" "$RUN_DIR/api-docs.pid"

echo "[converter-stop] Shutdown sequence completed."
