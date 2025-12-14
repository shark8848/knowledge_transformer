"""Celery app for the standalone slicer/recommendation service."""

from __future__ import annotations

import logging

from celery import Celery, signals

from .config import Settings, get_settings
from .recommendation import _round_profile, extract_signals_from_samples, recommend_strategy
from .monitoring import ensure_metrics_server

logger = logging.getLogger(__name__)

SETTINGS = get_settings()


def _create_celery(settings: Settings) -> Celery:
    app = Celery(settings.service_name)
    app.conf.update(
        broker_url=settings.celery.broker_url,
        result_backend=settings.celery.result_backend,
        task_default_queue=settings.celery.default_queue,
        task_time_limit=settings.celery.task_time_limit_sec,
        worker_prefetch_multiplier=settings.celery.prefetch_multiplier,
    )
    return app


celery_app = _create_celery(SETTINGS)


@signals.worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):  # type: ignore[override]
    if SETTINGS.monitoring.enable_metrics:
        ensure_metrics_server(SETTINGS.monitoring.prometheus_port)


@celery_app.task(name="probe.extract_signals")
def probe_extract_signals(payload):
    samples = payload.get("samples") or []
    profile = extract_signals_from_samples(samples)
    return _round_profile(profile, 3)


@celery_app.task(name="probe.recommend_strategy")
def probe_recommend_strategy(payload):
    samples = payload.get("samples") or []
    profile = payload.get("profile") or extract_signals_from_samples(samples)
    custom_cfg = payload.get("custom") or {}
    emit_candidates = bool(payload.get("emit_candidates", False))
    source_format = payload.get("source_format")
    return recommend_strategy(
        profile,
        samples=samples,
        custom_cfg=custom_cfg,
        emit_candidates=emit_candidates,
        source_format=source_format,
    )
