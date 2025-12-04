"""Monitoring utilities for dependency checks and Prometheus metrics."""

from __future__ import annotations

import logging
from typing import Dict
from urllib.parse import urlparse

from minio import Minio
from minio.error import S3Error
from prometheus_client import Counter, Gauge, start_http_server
import redis
from redis.exceptions import RedisError

from .config import Settings

logger = logging.getLogger(__name__)

TASKS_ACCEPTED = Counter(
    "conversion_tasks_accepted_total",
    "Total number of conversion tasks accepted",
    labelnames=("priority",),
)
TASKS_COMPLETED = Counter(
    "conversion_tasks_completed_total",
    "Total number of conversion tasks completed",
    labelnames=("status",),
)
QUEUE_DEPTH = Gauge(
    "conversion_queue_depth",
    "Number of pending tasks in the primary Celery queue",
)
CELERY_WORKERS = Gauge(
    "conversion_active_celery_workers",
    "Number of alive Celery workers responding to ping",
)

_metrics_started = False


def ensure_metrics_server(port: int) -> None:
    global _metrics_started
    if _metrics_started:
        return
    start_http_server(port)
    _metrics_started = True
    logger.info("Prometheus metrics server started", extra={"port": port})


def record_task_accepted(priority: str) -> None:
    TASKS_ACCEPTED.labels(priority=priority).inc()


def record_task_completed(status: str) -> None:
    TASKS_COMPLETED.labels(status=status).inc()


def _check_redis(settings: Settings) -> str:
    try:
        client = redis.Redis.from_url(
            settings.celery.broker_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        queue_depth = client.llen(settings.celery.default_queue)
        QUEUE_DEPTH.set(queue_depth)
        return "ok"
    except RedisError as exc:
        QUEUE_DEPTH.set(float("nan"))
        logger.warning("Redis health check failed", exc_info=exc)
        return f"error:{exc.__class__.__name__}"


def _check_minio(settings: Settings) -> str:
    parsed = urlparse(settings.minio.endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    try:
        client = Minio(
            netloc,
            access_key=settings.minio.access_key,
            secret_key=settings.minio.secret_key,
            secure=secure,
        )
        if settings.minio.bucket:
            exists = client.bucket_exists(settings.minio.bucket)
            return "ok" if exists else "missing-bucket"
        client.list_buckets()
        return "ok"
    except S3Error as exc:
        logger.warning("MinIO health check failed", exc_info=exc)
        return f"error:{exc.code}"
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("MinIO unexpected failure")
        return f"error:{exc.__class__.__name__}"


def _check_celery_workers(celery_app) -> str:
    try:
        replies = celery_app.control.ping(timeout=1)
        worker_count = len(replies) if replies else 0
        CELERY_WORKERS.set(worker_count)
        return "ok" if worker_count else "no-worker"
    except Exception as exc:  # pragma: no cover - defensive
        CELERY_WORKERS.set(0)
        logger.warning("Celery health check failed", exc_info=exc)
        return f"error:{exc.__class__.__name__}"


def collect_dependency_status(settings: Settings, celery_app) -> Dict[str, str]:
    """Run dependency probes and update Prometheus gauges."""

    return {
        "redis": _check_redis(settings),
        "minio": _check_minio(settings),
        "celery": _check_celery_workers(celery_app),
    }
