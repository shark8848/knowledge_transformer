"""Celery app for the video slicing service."""

from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

video_celery = Celery(
    settings.service_name,
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
)

video_celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Allow this worker to synchronously wait on downstream ASR/MM results.
    task_join_will_block=True,
    task_default_queue=settings.celery.default_queue,
    task_routes={
        "video.*": {"queue": settings.celery.default_queue},
        "video.asr.*": {"queue": settings.celery.asr_queue},
        "video.vision.*": {"queue": settings.celery.vision_queue},
    },
)

video_celery.autodiscover_tasks(["video_service"])
