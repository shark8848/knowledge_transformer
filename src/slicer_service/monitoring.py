"""Minimal Prometheus metrics server utilities for slicer service."""

from __future__ import annotations

import logging
from typing import Dict

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest, start_http_server

logger = logging.getLogger(__name__)
_metrics_started: Dict[int, bool] = {}


def ensure_metrics_server(port: int) -> None:
    if _metrics_started.get(port):
        return
    try:
        start_http_server(port)
        _metrics_started[port] = True
        logger.info("Started Prometheus metrics server on port %s", port)
    except OSError as exc:  # pragma: no cover - port in use
        logger.warning("Metrics server already running or port busy: %s", exc)


def render_metrics() -> tuple[bytes, str]:
    output = generate_latest(REGISTRY)
    return output, CONTENT_TYPE_LATEST
