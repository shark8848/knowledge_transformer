"""Celery app for pipeline orchestration (conversion -> slicing)."""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

pipeline_celery = Celery(
    "pipeline_service",
    broker=settings.redis_broker,
    backend=settings.redis_backend,
)

pipeline_celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.pipeline_queue,
    task_routes={
        "pipeline.*": {"queue": settings.pipeline_queue},
        "conversion.handle_batch": {"queue": settings.conversion_queue},
        "probe.*": {"queue": settings.probe_queue},
    },
)

# Ensure local task modules are registered so the worker can execute pipeline.* tasks.
pipeline_celery.autodiscover_tasks(["pipeline_service"])
