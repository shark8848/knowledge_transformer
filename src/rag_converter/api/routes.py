"""API route definitions for the conversion service."""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, status
from celery.exceptions import CeleryError

from ..config import Settings, settings_dependency
from ..errors import raise_error
from ..security import authenticate_request
from ..celery_app import celery_app, handle_conversion_task
from ..plugins import REGISTRY
from ..monitoring import collect_dependency_status, record_task_accepted
from .schemas import (
    ConversionRequest,
    ConversionResponse,
    FormatDescriptor,
    FormatsResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _per_format_limit(settings: Settings, fmt: str) -> int:
    limits = settings.file_limits
    return limits.per_format_max_size_mb.get(fmt, limits.default_max_size_mb)


def _validate_request(payload: ConversionRequest, settings: Settings) -> None:
    limits = settings.file_limits
    files = payload.files

    if not files:
        raise_error("ERR_FORMAT_UNSUPPORTED")

    if len(files) > limits.max_files_per_task:
        raise_error("ERR_BATCH_LIMIT_EXCEEDED")

    total_size = sum(file.size_mb for file in files)
    if total_size > limits.max_total_upload_size_mb:
        raise_error("ERR_BATCH_LIMIT_EXCEEDED")

    registry_pairs = {
        (plugin.source_format.lower(), plugin.target_format.lower())
        for plugin in REGISTRY.list()
    }
    configured_pairs = {
        (f.source.lower(), f.target.lower())
        for f in settings.convert_formats
    }
    supported = registry_pairs or configured_pairs
    for file in files:
        fmt = file.source_format.lower()
        per_limit = _per_format_limit(settings, fmt)
        if file.size_mb > per_limit:
            raise_error("ERR_FILE_TOO_LARGE")
        if (fmt, file.target_format.lower()) not in supported:
            raise_error("ERR_FORMAT_UNSUPPORTED")


@router.post(
    "/convert",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ConversionResponse,
    dependencies=[Depends(authenticate_request)],
)
async def submit_conversion(
    payload: ConversionRequest,
    settings: Settings = Depends(settings_dependency),
) -> ConversionResponse:
    _validate_request(payload, settings)

    task_id = str(uuid4())
    message = "Task accepted and scheduled for conversion"
    task_payload = {
        "task_id": task_id,
        "files": [file.model_dump() for file in payload.files],
        "priority": payload.priority,
        "callback_url": payload.callback_url,
    }

    try:
        handle_conversion_task.delay(task_payload)
    except CeleryError:
        logger.exception("Failed to enqueue task %s", task_id)
        raise_error("ERR_TASK_FAILED")

    record_task_accepted(payload.priority)

    return ConversionResponse(status="accepted", task_id=task_id, message=message)


@router.get("/formats", response_model=FormatsResponse)
async def list_formats(settings: Settings = Depends(settings_dependency)) -> FormatsResponse:
    formats = [
        FormatDescriptor(source=plugin.source_format, target=plugin.target_format, plugin=plugin.slug)
        for plugin in REGISTRY.list()
    ]
    if not formats and settings.convert_formats:
        formats = [
            FormatDescriptor(source=f.source, target=f.target, plugin=f.plugin)
            for f in settings.convert_formats
        ]
    return FormatsResponse(formats=formats)


@router.get("/monitor/health", response_model=HealthResponse)
async def health_check(settings: Settings = Depends(settings_dependency)) -> HealthResponse:
    deps = collect_dependency_status(settings, celery_app)
    return HealthResponse(status="ok", timestamp=datetime.utcnow(), dependencies=deps)
