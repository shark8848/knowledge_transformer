#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
HOST="${MINERU_HOST:-0.0.0.0}"
PORT="${MINERU_PORT:-8100}"
CMD="${MINERU_CMD:-mineru-api}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

require_bin() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "[mineru-start] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$CMD"

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
    echo "[mineru-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[mineru-start] Launching $name on ${HOST}:${PORT} ..."
  nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[mineru-start] $name PID $(<"$pid_file")"
}

start_component "MinerU API" "$RUN_DIR/mineru-api.pid" "$LOG_DIR/mineru-api.log" \
  "$CMD" --host "$HOST" --port "$PORT"

echo "[mineru-start] MinerU launched. Logs: $LOG_DIR"
