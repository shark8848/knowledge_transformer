#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
CONFIG_FILE="${RAG_CONFIG_FILE:-$ROOT_DIR/config/settings.yaml}"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${API_PORT:-8000}"
CELERY_LOG_LEVEL="${CELERY_LOG_LEVEL:-info}"
TEST_REPORT_PORT="${TEST_REPORT_PORT:-8088}"
TEST_REPORT_HOST="${TEST_REPORT_HOST:-0.0.0.0}"
TEST_REPORT_PATH="${TEST_REPORT_PATH:-$ROOT_DIR/test-report.html}"
API_DOCS_PORT="${API_DOCS_PORT:-8090}"
API_DOCS_HOST="${API_DOCS_HOST:-0.0.0.0}"
API_DOCS_TITLE="${API_DOCS_TITLE:-Knowledge Transformer API Docs}"
API_DOCS_CONFIG="${API_DOCS_CONFIG:-$CONFIG_FILE}"
API_DOCS_ALWAYS_REFRESH="${API_DOCS_ALWAYS_REFRESH:-false}"
API_DOCS_FAVICON="${API_DOCS_FAVICON:-}"
API_DOCS_TARGET_URL="${API_DOCS_TARGET_URL:-http://127.0.0.1:${API_PORT}}"

TEST_ARTIFACTS_DIR_DEFAULT="$ROOT_DIR/tests/artifacts/conversions"
export RAG_TEST_ARTIFACTS_DIR="${RAG_TEST_ARTIFACTS_DIR:-$TEST_ARTIFACTS_DIR_DEFAULT}"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$RAG_TEST_ARTIFACTS_DIR"

FLOWER_PORT="${FLOWER_PORT:-5555}"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[start] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$VENV_BIN/uvicorn"
require_bin "$VENV_BIN/celery"
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
  local name="$1" pid_file="$2" log_file="$3" cmd=("${@:4}")
  if is_running "$pid_file"; then
    echo "[start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[start] Launching $name ..."
  RAG_CONFIG_FILE="$CONFIG_FILE" nohup "${cmd[@]}" \
    >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[start] $name PID $(<"$pid_file")"
}

start_component "FastAPI" "$RUN_DIR/api.pid" "$LOG_DIR/api.log" \
  "$VENV_BIN/uvicorn" rag_converter.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "Celery" "$RUN_DIR/celery.pid" "$LOG_DIR/celery.log" \
  "$VENV_BIN/celery" -A rag_converter.celery_app.celery_app worker -l "$CELERY_LOG_LEVEL"

start_component "Flower" "$RUN_DIR/flower.pid" "$LOG_DIR/flower.log" \
  "$VENV_BIN/celery" -A rag_converter.celery_app.celery_app flower --port="$FLOWER_PORT" --url_prefix="/flower"

start_component "TestReport" "$RUN_DIR/test-report.pid" "$LOG_DIR/test-report.log" \
  env TEST_REPORT_PATH="$TEST_REPORT_PATH" TEST_REPORT_PORT="$TEST_REPORT_PORT" TEST_REPORT_HOST="$TEST_REPORT_HOST" \
  "$VENV_BIN/python" "$ROOT_DIR/test_report_server.py"

start_component "APIDocs" "$RUN_DIR/api-docs.pid" "$LOG_DIR/api-docs.log" \
  env API_DOCS_PORT="$API_DOCS_PORT" API_DOCS_HOST="$API_DOCS_HOST" API_DOCS_TITLE="$API_DOCS_TITLE" \
      API_DOCS_CONFIG="$API_DOCS_CONFIG" API_DOCS_ALWAYS_REFRESH="$API_DOCS_ALWAYS_REFRESH" \
      API_DOCS_FAVICON="$API_DOCS_FAVICON" API_DOCS_TARGET_URL="$API_DOCS_TARGET_URL" \
  "$VENV_BIN/python" "$ROOT_DIR/api_docs_server.py"

echo "[start] All components launched. Logs stored in $LOG_DIR"
