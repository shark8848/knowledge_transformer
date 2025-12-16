#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
HOST="${MINERU_HOST:-0.0.0.0}"
PORT="${MINERU_PORT:-8100}"

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

echo "== MinerU Status =="
printf "%-18s %s\n" "MinerU API" "$(is_running "$RUN_DIR/mineru-api.pid")"
printf "%-18s %s\n" "Endpoint" "http://${HOST}:${PORT}"
printf "%-18s %s\n" "Health" "$(check_http "http://${HOST}:${PORT}/docs")"
