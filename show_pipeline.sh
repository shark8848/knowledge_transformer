#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
RUN_DIR="$ROOT_DIR/.run"
PIPELINE_PORT="${PIPELINE_PORT:-9100}"
PIPELINE_FLOWER_PORT="${PIPELINE_FLOWER_PORT:-5557}"
CONFIG_FILE="${PIPELINE_CONFIG_FILE:-$ROOT_DIR/config/settings.yaml}"
PYTHONPATH="$ROOT_DIR/src"
export PYTHONPATH

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[pipeline-show] Missing executable: $1" >&2
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
from pipeline_service.config import get_settings

cfg = get_settings()
url = urlparse(cfg.redis_broker)
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
from pipeline_service.config import get_settings

cfg = get_settings()
parsed = urlparse(str(cfg.minio_endpoint))
client = Minio(
    (parsed.netloc or parsed.path),
    access_key=cfg.minio_access_key,
    secret_key=cfg.minio_secret_key,
    secure=(parsed.scheme == 'https'),
)
try:
    bucket = cfg.minio_bucket
    if bucket:
        client.bucket_exists(bucket)
    else:
        client.list_buckets()
    print("healthy")
except Exception as exc:  # pragma: no cover
    print(f"unhealthy ({exc.__class__.__name__})")
PY
}

echo "== Pipeline Process Status =="
printf "%-20s %s\n" "Pipeline Celery" "$(is_running "$RUN_DIR/pipeline-celery.pid")"
printf "%-20s %s\n" "Pipeline API" "$(is_running "$RUN_DIR/pipeline-api.pid")"
printf "%-20s %s\n" "Pipeline API /health" "$(check_http "http://127.0.0.1:${PIPELINE_PORT}/docs")"
printf "%-20s %s\n" "Pipeline Flower" "$(is_running "$RUN_DIR/pipeline-flower.pid")"
printf "%-20s %s\n" "Pipeline Flower UI" "http://127.0.0.1:${PIPELINE_FLOWER_PORT}/pipeline-flower"
printf "%-20s %s\n" "Redis" "$(check_redis)"
printf "%-20s %s\n" "MinIO" "$(check_minio)"
