#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/venv/bin:$PATH"
HOST_ID="${HOSTNAME:-$(hostname)}"

# Load runtime overrides if provided inside the container
if [ -f /app/.env ]; then
  echo "Sourcing environment from /app/.env"
  if command -v source >/dev/null 2>&1; then
    set -a
    # shellcheck disable=SC1091
    source /app/.env
    set +a
  else
    # Fallback for shells without 'source'
    set -a
    # shellcheck disable=SC1091
    . /app/.env
    set +a
  fi
fi

# Derive default PORT from service-specific env when not explicitly provided
if [ -z "${PORT:-}" ]; then
  case "${SERVICE_NAME:-}" in
    video)
      PORT="${VIDEO_API_PORT:-9200}"
      ;;
    ui)
      PORT="${UI_PORT:-7860}"
      ;;
    multimodal)
      PORT="${MM_API_PORT:-8300}"
      ;;
    asr)
      PORT="${ASR_API_PORT:-8200}"
      ;;
    pipeline)
      PORT="${PIPELINE_API_PORT:-9100}"
      ;;
    meta)
      PORT="${META_API_PORT:-9000}"
      ;;
    slicer)
      PORT="${SLICER_API_PORT:-9001}"
      ;;
    vector)
      PORT="${VECTOR_API_PORT:-9002}"
      ;;
    *)
      PORT="${PORT:-8000}"
      ;;
  esac
fi

# Default config file location
if [ -z "${RAG_CONFIG_FILE:-}" ] && [ -f /app/config/settings.yaml ]; then
  export RAG_CONFIG_FILE=/app/config/settings.yaml
fi

cmd="${1:-api}"
shift || true

case "$cmd" in
  api)
    exec uvicorn rag_converter.app:app --host 0.0.0.0 --port "${PORT:-8000}" "$@"
    ;;
  worker)
    worker_name="${CELERY_WORKER_NAME:-}"
    if [ -z "$worker_name" ]; then
      case "${SERVICE_NAME:-}" in
        video)
          worker_name="docker-video-service@${HOST_ID}"
          ;;
        asr|audio)
          worker_name="docker-audio-service@${HOST_ID}"
          ;;
        ocr)
          worker_name="docker-ocr-service@${HOST_ID}"
          ;;
        pipeline)
          worker_name="docker-pipeline-service@${HOST_ID}"
          ;;
        meta)
          worker_name="docker-meta-service@${HOST_ID}"
          ;;
        slicer)
          worker_name="docker-slicer-service@${HOST_ID}"
          ;;
        vector)
          worker_name="docker-vector-service@${HOST_ID}"
          ;;
        multimodal)
          worker_name="docker-multimodal-service@${HOST_ID}"
          ;;
        ui)
          worker_name="docker-ui-service@${HOST_ID}"
          ;;
        llm)
          worker_name="docker-llm-service@${HOST_ID}"
          ;;
        *)
          worker_name="docker-rag-service@${HOST_ID}"
          ;;
      esac
    fi
    exec celery -A rag_converter.celery_app.celery_app worker -n "$worker_name" -l "${CELERY_LOG_LEVEL:-info}" "$@"
    ;;
  flower)
    export FLOWER_UNAUTHENTICATED_API="${FLOWER_UNAUTHENTICATED_API:-true}"
    exec celery -A rag_converter.celery_app.celery_app flower --port="${FLOWER_PORT:-5555}" --url_prefix="${FLOWER_URL_PREFIX:-/flower}" "$@"
    ;;
  docs)
    exec python /app/api_docs_server.py "$@"
    ;;
  report)
    exec python /app/test_report_server.py "$@"
    ;;
  shell)
    exec bash "$@"
    ;;
  *)
    exec "$cmd" "$@"
    ;;
esac
