#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"

stop_component() {
  local name="$1" pid_file="$2"
  if [[ ! -f "$pid_file" ]]; then
    echo "[es-service-stop] $name not running (missing $pid_file)"
    return
  fi
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    echo "[es-service-stop] Stopping $name (PID $pid)"
    kill "$pid" >/dev/null 2>&1 || true
    wait "$pid" 2>/dev/null || true
  else
    echo "[es-service-stop] $name PID $pid not active"
  fi
  rm -f "$pid_file"
}

stop_component "ES Service API" "$RUN_DIR/es-service-api.pid"
stop_component "ES Service Celery" "$RUN_DIR/es-service-celery.pid"
stop_component "ES Service gRPC" "$RUN_DIR/es-service-grpc.pid"

echo "[es-service-stop] Shutdown sequence completed."
