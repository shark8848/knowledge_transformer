#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="$ROOT_DIR/.run"
API_PORT="${ES_SERVICE_API_PORT:-8085}"
GRPC_PORT="${ES_SERVICE_GRPC_PORT:-9105}"
PYTHONPATH="$ROOT_DIR/src"
export PYTHONPATH

SCRIPT_TAG="es-service-show"
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

PYTHON=$(resolve_bin python)

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

es_endpoint() {
  "$PYTHON" - <<'PY'
from es_service.config import get_settings
print(get_settings().es.endpoint)
PY
}

check_es() {
  local endpoint="$1"
  if command -v curl >/dev/null 2>&1 && curl -fsS "$endpoint/_cluster/health" >/dev/null 2>&1; then
    echo "healthy"
  else
    echo "unreachable"
  fi
}

celery_workers() {
  "$PYTHON" - <<'PY'
from es_service.tasks import celery_app
try:
    replies = celery_app.control.ping(timeout=1) or []
    print(f"{len(replies)} workers responding")
except Exception as exc:  # pragma: no cover
    print(f"unable to reach workers ({exc.__class__.__name__})")
PY
}

ES_ENDPOINT=$(es_endpoint)

echo "== ES Service Process Status =="
printf "%-22s %s\n" "ES Service API" "$(is_running "$RUN_DIR/es-service-api.pid")"
printf "%-22s %s\n" "ES Service Celery" "$(is_running "$RUN_DIR/es-service-celery.pid")"
printf "%-22s %s\n" "ES Service gRPC" "$(is_running "$RUN_DIR/es-service-grpc.pid")"
printf "%-22s %s\n" "FastAPI /healthz" "$(check_http "http://127.0.0.1:${API_PORT}/healthz")"
printf "%-22s %s\n" "gRPC port" "0.0.0.0:${GRPC_PORT}"

echo "\n== Dependencies =="
printf "%-22s %s\n" "Elasticsearch" "$(check_es "$ES_ENDPOINT")" 
printf "%-22s %s\n" "Celery workers" "$(celery_workers)"
printf "%-22s %s\n" "ES endpoint" "$ES_ENDPOINT"
