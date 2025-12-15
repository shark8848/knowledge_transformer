"""Celery app for the multimodal service."""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

mm_celery = Celery(
    settings.service_name,
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

mm_celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Allow synchronous result joins when orchestrating from other workers.
    task_join_will_block=True,
    task_default_queue=settings.celery.default_queue,
    task_time_limit=settings.celery.task_time_limit_sec,
    worker_prefetch_multiplier=settings.celery.prefetch_multiplier,
)

mm_celery.autodiscover_tasks(["multimodal_service"])
