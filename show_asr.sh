#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
API_PORT="${ASR_API_PORT:-8200}"
FLOWER_PORT="${ASR_FLOWER_PORT:-5558}"
export PYTHONPATH="$ROOT_DIR/src"

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

echo "== ASR Process Status =="
printf "%-18s %s\n" "ASR API" "$(is_running "$RUN_DIR/asr-api.pid")"
printf "%-18s %s\n" "ASR Worker" "$(is_running "$RUN_DIR/asr-worker.pid")"
printf "%-18s %s\n" "ASR Flower" "$(is_running "$RUN_DIR/asr-flower.pid")"
printf "%-18s %s\n" "API /healthz" "$(check_http "http://127.0.0.1:${API_PORT}/healthz")"
printf "%-18s %s\n" "API docs" "http://127.0.0.1:${API_PORT}/api/v1/docs"
printf "%-18s %s\n" "Flower UI" "http://127.0.0.1:${FLOWER_PORT}"
