#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
CONFIG_FILE="${RAG_CONFIG_FILE:-$ROOT_DIR/config/settings.yaml}"
RUN_DIR="$ROOT_DIR/.run"
API_PORT="${API_PORT:-8000}"
FLOWER_PORT="${FLOWER_PORT:-5555}"
TEST_REPORT_PORT="${TEST_REPORT_PORT:-8088}"
API_DOCS_PORT="${API_DOCS_PORT:-8090}"
PYTHONPATH="$ROOT_DIR/src"
export PYTHONPATH

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[show] Missing executable: $1" >&2
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

check_redis() {
  "$VENV_BIN/python" - "$CONFIG_FILE" <<'PY'
import sys
from urllib.parse import urlparse
import redis
from rag_converter.config import Settings

cfg = Settings.from_source(config_file=sys.argv[1])
url = urlparse(cfg.celery.broker_url)
client = redis.Redis(
    host=url.hostname or "localhost",
    port=url.port or 6379,
    db=int(url.path.lstrip('/') or 0) if url.path else 0,
    password=url.password,
    socket_timeout=2,
)
try:
    client.ping()
    print("healthy")
except Exception as exc:  # pragma: no cover
    print(f"unhealthy ({exc.__class__.__name__})")
PY
}

check_minio() {
  "$VENV_BIN/python" - "$CONFIG_FILE" <<'PY'
import sys
from urllib.parse import urlparse
from minio import Minio
from rag_converter.config import Settings

cfg = Settings.from_source(config_file=sys.argv[1])
parsed = urlparse(cfg.minio.endpoint)
client = Minio(
    (parsed.netloc or parsed.path),
    access_key=cfg.minio.access_key,
    secret_key=cfg.minio.secret_key,
    secure=(parsed.scheme == 'https'),
)
try:
    bucket = cfg.minio.bucket
    if bucket:
        client.bucket_exists(bucket)
    else:
        client.list_buckets()
    print("healthy")
except Exception as exc:  # pragma: no cover
    print(f"unhealthy ({exc.__class__.__name__})")
PY
}

celery_workers() {
  "$VENV_BIN/python" - "$CONFIG_FILE" <<'PY'
import sys
from rag_converter.config import Settings
from rag_converter.celery_app import celery_app

cfg = Settings.from_source(config_file=sys.argv[1])
# Ensure celery app picks up latest config if env differs.
celery_app.conf.broker_url = cfg.celery.broker_url
celery_app.conf.result_backend = cfg.celery.result_backend
try:
    replies = celery_app.control.ping(timeout=1) or []
    print(f"{len(replies)} workers responding")
except Exception as exc:  # pragma: no cover
    print(f"unable to reach workers ({exc.__class__.__name__})")
PY
}

echo "== Process Status =="
printf "%-18s %s\n" "FastAPI" "$(is_running "$RUN_DIR/api.pid")"
printf "%-18s %s\n" "Celery" "$(is_running "$RUN_DIR/celery.pid")"
printf "%-18s %s\n" "Flower" "$(is_running "$RUN_DIR/flower.pid")"
printf "%-18s %s\n" "TestReport" "$(is_running "$RUN_DIR/test-report.pid")"
printf "%-18s %s\n" "APIDocs" "$(is_running "$RUN_DIR/api-docs.pid")"
printf "%-18s %s\n" "FastAPI /healthz" "$(check_http "http://127.0.0.1:${API_PORT}/healthz")"
printf "%-18s %s\n" "API docs /" "$(check_http "http://127.0.0.1:${API_DOCS_PORT}/")"

PROM_PORT=$("$VENV_BIN/python" - "$CONFIG_FILE" <<'PY'
import sys
from rag_converter.config import Settings
print(Settings.from_source(config_file=sys.argv[1]).monitoring.prometheus_port)
PY
)
printf "%-18s %s\n" "API metrics" "http://127.0.0.1:${PROM_PORT}/metrics"
printf "%-18s %s\n" "Worker metrics" "http://127.0.0.1:$((PROM_PORT + 1))/metrics"
printf "%-18s %s\n" "Flower UI" "http://127.0.0.1:${FLOWER_PORT}/flower"
printf "%-18s %s\n" "Test report" "http://127.0.0.1:${TEST_REPORT_PORT}/"
printf "%-18s %s\n" "API docs" "http://127.0.0.1:${API_DOCS_PORT}/"

echo "\n== External Dependencies =="
printf "%-18s %s\n" "Redis" "$(check_redis)"
printf "%-18s %s\n" "MinIO" "$(check_minio)"
printf "%-18s %s\n" "Celery workers" "$(celery_workers)"
