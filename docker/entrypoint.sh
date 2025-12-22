#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/venv/bin:$PATH"

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
    exec celery -A rag_converter.celery_app.celery_app worker -l "${CELERY_LOG_LEVEL:-info}" "$@"
    ;;
  flower)
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
