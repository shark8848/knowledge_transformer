#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"
API_PORT="${ES_SEARCH_SERVICE_API_PORT:-8086}"
GRPC_PORT="${ES_SEARCH_SERVICE_GRPC_PORT:-9106}"
CELERY_LOG_LEVEL="${ES_SEARCH_SERVICE_CELERY_LOG_LEVEL:-info}"
HOST_ID="${HOSTNAME:-$(hostname)}"
WORKER_NAME="${ES_SEARCH_SERVICE_WORKER_NAME:-es-search-service@${HOST_ID}}"

# Load env overrides and bridge from ES_INDEX_SERVICE_* (or legacy ES_SERVICE_*) to ES_SEARCH_SERVICE_* so search service can reuse ES creds.
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
fi

# Fallback mapping to keep ES search in sync with ES service settings.
: "${ES_SEARCH_SERVICE_ES__ENDPOINT:=${ES_INDEX_SERVICE_ES__ENDPOINT:-${ES_SERVICE_ES__ENDPOINT:-}}}"
: "${ES_SEARCH_SERVICE_ES__USERNAME:=${ES_INDEX_SERVICE_ES__USERNAME:-${ES_SERVICE_ES__USERNAME:-}}}"
: "${ES_SEARCH_SERVICE_ES__PASSWORD:=${ES_INDEX_SERVICE_ES__PASSWORD:-${ES_SERVICE_ES__PASSWORD:-}}}"
: "${ES_SEARCH_SERVICE_ES__VERIFY_SSL:=${ES_INDEX_SERVICE_ES__VERIFY_SSL:-${ES_SERVICE_ES__VERIFY_SSL:-}}}"
: "${ES_SEARCH_SERVICE_ES__REQUEST_TIMEOUT_SEC:=${ES_INDEX_SERVICE_ES__REQUEST_TIMEOUT_SEC:-${ES_SERVICE_ES__REQUEST_TIMEOUT_SEC:-}}}"
: "${ES_SEARCH_SERVICE_ES__READ_ALIAS:=${ES_INDEX_SERVICE_ES__READ_ALIAS:-${ES_SERVICE_ES__READ_ALIAS:-}}}"
: "${ES_SEARCH_SERVICE_ES__DEFAULT_INDEX:=${ES_INDEX_SERVICE_ES__DEFAULT_INDEX:-${ES_SERVICE_ES__DEFAULT_INDEX:-}}}"
export ES_SEARCH_SERVICE_ES__ENDPOINT ES_SEARCH_SERVICE_ES__USERNAME ES_SEARCH_SERVICE_ES__PASSWORD \
  ES_SEARCH_SERVICE_ES__VERIFY_SSL ES_SEARCH_SERVICE_ES__REQUEST_TIMEOUT_SEC \
  ES_SEARCH_SERVICE_ES__READ_ALIAS ES_SEARCH_SERVICE_ES__DEFAULT_INDEX

mkdir -p "$RUN_DIR" "$LOG_DIR"

SCRIPT_TAG="es-search-service-start"
resolve_bin() {
  local name="$1"
  for cand in "/opt/venv/bin/$name" "$VENV_BIN/$name" "$(command -v "$name" 2>/dev/null)"; do
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
  local name="$1" pid_file="$2" log_file="$3"; shift 3
  if is_running "$pid_file"; then
    echo "[$SCRIPT_TAG] $name already running (PID $(<"$pid_file"))"
    return
  fi
  echo "[$SCRIPT_TAG] Launching $name ..."
  PYTHONPATH="$ROOT_DIR/src" nohup "$@" >>"$log_file" 2>&1 &
  echo $! >"$pid_file"
  echo "[$SCRIPT_TAG] $name PID $(<"$pid_file")"
}

start_component "ES Search Service API" "$RUN_DIR/es-search-service-api.pid" "$LOG_DIR/es-search-service-api.log" \
  "$UVICORN" es_search_service.app:app --host 0.0.0.0 --port "$API_PORT"

start_component "ES Search Service Celery" "$RUN_DIR/es-search-service-celery.pid" "$LOG_DIR/es-search-service-celery.log" \
  "$CELERY" -A es_search_service.tasks.celery_app worker -l "$CELERY_LOG_LEVEL" -n "$WORKER_NAME"

start_component "ES Search Service gRPC" "$RUN_DIR/es-search-service-grpc.pid" "$LOG_DIR/es-search-service-grpc.log" \
  "$PYTHON" -m es_search_service.grpc_server --port "$GRPC_PORT"

echo "[$SCRIPT_TAG] All components launched. Logs stored in $LOG_DIR"
