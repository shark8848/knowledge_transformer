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

check_es() {
  local endpoint="$1"
  local curl_opts=()
  [[ "$ES_VERIFY" == "false" ]] && curl_opts+=(-k)
  if [[ -n "$ES_USER" && -n "$ES_PASS" ]]; then
    curl_opts+=(-u "$ES_USER:$ES_PASS")
  fi
  if command -v curl >/dev/null 2>&1; then
    local code
    code=$(curl -o /dev/null -sS -w "%{http_code}" "${curl_opts[@]}" "$endpoint/_cluster/health" || true)
    if [[ "$code" =~ ^2 ]]; then
      echo "[start-all] ES healthy at $endpoint"
      return 0
    fi
    echo "[start-all] Waiting for ES at $endpoint (status=${code:-n/a}) ..."
    return 1
  fi
  echo "[start-all] curl not available for ES check"
  return 1
}

run_script() {
  local script_path="$1" label="$2"; shift 2
  if [[ ! -x "$script_path" ]]; then
    echo "[start-all] Skipping $label (missing or not executable: $script_path)" >&2
    return
  fi
  echo "[start-all] Starting $label ..."
  "$script_path" "$@" || echo "[start-all] Warning: $label exited with non-zero status" >&2
}

# Ensure ES is reachable before dependent services
es_ready=false
for i in {1..20}; do
  if check_es "$ES_ENDPOINT"; then
    es_ready=true
    break
  fi
  sleep 2
done
if [[ "$es_ready" != true ]]; then
  echo "[start-all] Elasticsearch not reachable after retries, continuing but dependent services may fail." >&2
fi


# Start core services first to satisfy dependencies.
run_script "$ROOT_DIR/start_converter.sh" "converter"
run_script "$ROOT_DIR/start_slicer.sh" "slicer"
# ES write + search services (dependencies for downstream pipeline/vector/search)
run_script "$ROOT_DIR/start_es_service.sh" "es_service"
run_script "$ROOT_DIR/start_es_search_service.sh" "es_search_service"
# Generic LLM service (independent provider)
run_script "$ROOT_DIR/start_llm.sh" "llm"
# Vector service (embeddings/rerank)
run_script "$ROOT_DIR/start_vector.sh" "vector"
# Pipeline handles downstream orchestration; disable its dependency autostart to avoid duplication.
DEPEND_START_CONVERTER=false DEPEND_START_SLICER=false \
  run_script "$ROOT_DIR/start_pipeline.sh" "pipeline"
# UI service (Gradio frontend)
run_script "$ROOT_DIR/start_ui.sh" "ui"

# ASR and multimodal are independent entrypoints used by video.
run_script "$ROOT_DIR/start_asr.sh" "asr"
run_script "$ROOT_DIR/start_multimodal.sh" "multimodal"

# Video service depends on asr/multimodal availability.
run_script "$ROOT_DIR/start_video.sh" "video"

# MinerU OCR/structure service (optional standalone)
run_script "$ROOT_DIR/start_mineru.sh" "mineru"

echo "[start-all] Done." 
