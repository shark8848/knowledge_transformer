#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
UI_PORT="${UI_PORT:-${PIPELINE_UI_PORT:-7860}}"

# Load env overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
  UI_PORT="${UI_PORT:-${PIPELINE_UI_PORT:-$UI_PORT}}"
fi

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

echo "== UI Service Status =="
printf "%-20s %s\n" "UI Service" "$(is_running "$RUN_DIR/ui-service.pid")"
printf "%-20s %s\n" "UI /" "$(check_http "http://127.0.0.1:${UI_PORT}/")"
