#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
UI_PORT="${UI_PORT:-${PIPELINE_UI_PORT:-7860}}"
UI_API_URL="${UI_API_URL:-${UI_PIPELINE_API_URL:-${PIPELINE_API_URL:-http://127.0.0.1:9100}}}"
export PYTHONPATH="$ROOT_DIR/src"

# Load local environment overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
  UI_PORT="${UI_PORT:-${PIPELINE_UI_PORT:-$UI_PORT}}"
  UI_API_URL="${UI_API_URL:-${UI_PIPELINE_API_URL:-${PIPELINE_API_URL:-$UI_API_URL}}}"
fi

mkdir -p "$RUN_DIR" "$LOG_DIR"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[ui-start] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/python"

is_running() {
  local pid_file="$1"
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid=$(<"$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    return 0
  fi
  rm -f "$pid_file"
  return 1
}

start_component() {
  local name="$1" pid_file="$2" log_file="$3"; shift 3
  if is_running "$pid_file"; then
    echo "[ui-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[ui-start] Launching $name ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[ui-start] $name PID $(<"$pid_file")"
}

start_component "UI Service" "$RUN_DIR/ui-service.pid" "$LOG_DIR/ui-service.log" \
  env GRADIO_SERVER_NAME="0.0.0.0" GRADIO_SERVER_PORT="$UI_PORT" UI_PIPELINE_API_URL="$UI_API_URL" \
  "$VENV_BIN/python" -m ui_service.ui

echo "[ui-start] UI service launched. Logs: $LOG_DIR"
