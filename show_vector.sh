#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
FLOWER_PORT="${VECTOR_FLOWER_PORT:-5562}"
export PYTHONPATH="$ROOT_DIR/src"

# Load local environment overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
  FLOWER_PORT="${VECTOR_FLOWER_PORT:-$FLOWER_PORT}"
fi

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[vector-show] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/python"

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

echo "== Vector Process Status =="
printf "%-18s %s\n" "Vector Worker" "$(is_running "$RUN_DIR/vector-worker.pid")"
printf "%-18s %s\n" "Vector Flower" "$(is_running "$RUN_DIR/vector-flower.pid")"
printf "%-18s %s\n" "Flower UI" "http://127.0.0.1:${FLOWER_PORT}"
