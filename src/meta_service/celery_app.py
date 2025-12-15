"""Celery app for the metadata extraction service."""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

meta_celery = Celery(
    settings.service_name,
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

meta_celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.celery.default_queue,
    task_routes={"meta.*": {"queue": settings.celery.default_queue}},
)

meta_celery.autodiscover_tasks(["meta_service"])
