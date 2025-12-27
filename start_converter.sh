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
HOST_ID="${HOSTNAME:-$(hostname)}"
CONVERTER_WORKER_NAME="${CONVERTER_WORKER_NAME:-docker-converter-service@${HOST_ID}}"

TEST_ARTIFACTS_DIR_DEFAULT="$ROOT_DIR/tests/artifacts/conversions"
export RAG_TEST_ARTIFACTS_DIR="${RAG_TEST_ARTIFACTS_DIR:-$TEST_ARTIFACTS_DIR_DEFAULT}"

mkdir -p "$RUN_DIR" "$LOG_DIR" "$RAG_TEST_ARTIFACTS_DIR"

FLOWER_PORT="${FLOWER_PORT:-5555}"
FLOWER_UNAUTHENTICATED_API="${FLOWER_UNAUTHENTICATED_API:-true}"

SCRIPT_TAG="converter-start"
resolve_bin() {
  local name="$1"
  for cand in "/opt/venv/bin/$name" "$ROOT_DIR/.venv/bin/$name" "$(command -v "$name" 2>/dev/null)"; do
    if [[ -n "$cand" && -x "$cand" ]]; then
      echo "$cand"
      return
    fi
  done
  echo "[$SCRIPT_TAG] Missing executable: $name" >&2
  exit 1
}

UVICORN=$(resolve_bin uvicorn)
CELERY=$(resolve_bin celery)
PYTHON=$(resolve_bin python)

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
    echo "[converter-start] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[converter-start] Launching $name ..."
  RAG_CONFIG_FILE="$CONFIG_FILE" nohup "${cmd[@]}" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[converter-start] $name PID $(<"$pid_file")"
}

start_component "Converter FastAPI" "$RUN_DIR/api.pid" "$LOG_DIR/rag-converter-api.log" \
  "$UVICORN" rag_converter.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "Converter Celery" "$RUN_DIR/celery.pid" "$LOG_DIR/rag-converter-celery.log" \
  "$CELERY" -A rag_converter.celery_app.celery_app worker -l "$CELERY_LOG_LEVEL" -n "$CONVERTER_WORKER_NAME" -Q conversion

start_component "Converter Flower" "$RUN_DIR/flower.pid" "$LOG_DIR/rag-converter-flower.log" \
  env FLOWER_UNAUTHENTICATED_API="$FLOWER_UNAUTHENTICATED_API" \
  "$CELERY" -A rag_converter.celery_app.celery_app flower --port="$FLOWER_PORT" --url_prefix="/flower"

start_component "TestReport" "$RUN_DIR/test-report.pid" "$LOG_DIR/rag-converter-test-report.log" \
  env TEST_REPORT_PATH="$TEST_REPORT_PATH" TEST_REPORT_PORT="$TEST_REPORT_PORT" TEST_REPORT_HOST="$TEST_REPORT_HOST" \
  "$PYTHON" "$ROOT_DIR/test_report_server.py"

start_component "APIDocs" "$RUN_DIR/api-docs.pid" "$LOG_DIR/rag-converter-api-docs.log" \
  env API_DOCS_PORT="$API_DOCS_PORT" API_DOCS_HOST="$API_DOCS_HOST" API_DOCS_TITLE="$API_DOCS_TITLE" \
      API_DOCS_CONFIG="$API_DOCS_CONFIG" API_DOCS_ALWAYS_REFRESH="$API_DOCS_ALWAYS_REFRESH" \
      API_DOCS_FAVICON="$API_DOCS_FAVICON" API_DOCS_TARGET_URL="$API_DOCS_TARGET_URL" \
  "$PYTHON" "$ROOT_DIR/api_docs_server.py"

echo "[converter-start] All components launched. Logs stored in $LOG_DIR"
