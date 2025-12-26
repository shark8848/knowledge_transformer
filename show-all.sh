#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load env overrides if present
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ROOT_DIR/.env"
  set +o allexport
fi

ES_ENDPOINT_DEFAULT="http://localhost:9200"
ES_ENDPOINT="${ES_SERVICE_ES__ENDPOINT:-$ES_ENDPOINT_DEFAULT}"
ES_USER="${ES_SERVICE_ES__USERNAME:-}"
ES_PASS="${ES_SERVICE_ES__PASSWORD:-}"
ES_VERIFY="${ES_SERVICE_ES__VERIFY_SSL:-false}"
RUN_DIR="$ROOT_DIR/.run"
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
MINIO_HEALTH_PATH="${MINIO_HEALTH_PATH:-/minio/health/live}"

check_es() {
  local endpoint="$1"
  local curl_opts=()
  [[ "$ES_VERIFY" == "false" ]] && curl_opts+=(-k)
  if [[ -n "$ES_USER" && -n "$ES_PASS" ]]; then
    curl_opts+=(-u "$ES_USER:$ES_PASS")
  fi
  local code
  if command -v curl >/dev/null 2>&1; then
    code=$(curl -o /dev/null -sS -w "%{http_code}" "${curl_opts[@]}" "$endpoint/_cluster/health" || true)
    if [[ "$code" =~ ^2 ]]; then
      echo "healthy ($endpoint)"
      return
    fi
    if [[ -n "$code" ]]; then
      echo "unreachable (${endpoint}) status=$code"
      return
    fi
  fi
  echo "unreachable ($endpoint)"
}

check_redis() {
  if command -v redis-cli >/dev/null 2>&1; then
    if redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping >/dev/null 2>&1; then
      echo "healthy (${REDIS_HOST}:${REDIS_PORT})"
    else
      echo "unreachable (${REDIS_HOST}:${REDIS_PORT})"
    fi
  else
    echo "unknown (redis-cli missing)"
  fi
}

check_minio() {
  local url="$MINIO_ENDPOINT$MINIO_HEALTH_PATH"
  if command -v curl >/dev/null 2>&1 && curl -fsS -k "$url" >/dev/null 2>&1; then
    echo "reachable ($url)"
  else
    echo "unreachable ($url)"
  fi
}

run_script() {
  local script_path="$1" label="$2"
  if [[ ! -x "$script_path" ]]; then
    echo "[show-all] Skipping $label (missing or not executable: $script_path)" >&2
    return
  fi
  echo "[show-all] === $label ==="
  "$script_path" || echo "[show-all] Warning: $label exited with non-zero status" >&2
  echo ""
}

run_script "$ROOT_DIR/show_converter.sh" "converter"
run_script "$ROOT_DIR/show_slicer.sh" "slicer"
run_script "$ROOT_DIR/show_pipeline.sh" "pipeline"
run_script "$ROOT_DIR/show_ui.sh" "ui"
run_script "$ROOT_DIR/show_llm.sh" "llm"
run_script "$ROOT_DIR/show_vector.sh" "vector"
run_script "$ROOT_DIR/show_es_service.sh" "es_service"
run_script "$ROOT_DIR/show_es_search_service.sh" "es_search_service"
run_script "$ROOT_DIR/show_asr.sh" "asr"
run_script "$ROOT_DIR/show_multimodal.sh" "multimodal"
run_script "$ROOT_DIR/show_video.sh" "video"
run_script "$ROOT_DIR/show_mineru.sh" "mineru"

echo "[show-all] Done." 

# Overall summary (API / Celery)
is_running() {
  local pid_file="$1"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid=$(<"$pid_file")
    if kill -0 "$pid" >/dev/null 2>&1; then
      echo "running"
      return
    fi
  fi
  echo "stopped"
}

summary_row() {
  local name="$1" api_pid="$2" celery_pid="$3"
  local api_status="n/a" celery_status="n/a"
  if [[ -n "$api_pid" ]]; then
    api_status=$(is_running "$RUN_DIR/$api_pid")
  fi
  if [[ -n "$celery_pid" ]]; then
    celery_status=$(is_running "$RUN_DIR/$celery_pid")
  fi
  printf "%-16s | %-8s | %-8s\n" "$name" "$api_status" "$celery_status"
}

echo "[show-all] == Summary =="
printf "%-16s | %-8s | %-8s\n" "Service" "API" "Celery"
printf -- "-----------------+----------+---------\n"
summary_row "converter" "api.pid" "celery.pid"
summary_row "slicer" "slicer-api.pid" "slicer-worker.pid"
summary_row "pipeline" "pipeline-api.pid" "pipeline-celery.pid"
summary_row "ui" "ui-service.pid" ""
summary_row "llm" "" "llm-worker.pid"
summary_row "vector" "" "vector-worker.pid"
summary_row "es_service" "es-service-api.pid" "es-service-celery.pid"
summary_row "es_search" "es-search-service-api.pid" "es-search-service-celery.pid"
summary_row "asr" "asr-api.pid" "asr-worker.pid"
summary_row "multimodal" "mm-api.pid" "mm-worker.pid"
summary_row "video" "video-api.pid" "video-worker.pid"
summary_row "mineru" "mineru-api.pid" ""

echo ""
echo "[show-all] == Dependencies =="
printf "%-22s %s\n" "Elasticsearch" "$(check_es "$ES_ENDPOINT")"
printf "%-22s %s\n" "Redis" "$(check_redis)"
printf "%-22s %s\n" "MinIO" "$(check_minio)"
