"""API route definitions for the conversion service."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from typing import Any

from fastapi import APIRouter, Depends, status
from celery.exceptions import CeleryError
from fastapi.responses import JSONResponse

from ..config import Settings, settings_dependency
from ..errors import raise_error
from ..security import authenticate_request
from ..celery_app import (
    _apply_storage_override,
    _materialize_input,
    _upload_output,
    _build_download_url,
    celery_app,
    handle_conversion_task,
)
from ..plugins import REGISTRY
from ..plugins.base import ConversionInput
from ..monitoring import collect_dependency_status, record_task_accepted
from .schemas import (
    ConversionRequest,
    ConversionResponse,
    ConversionResultPayload,
    FormatDescriptor,
    FormatsResponse,
    HealthResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _per_format_limit(settings: Settings, fmt: str) -> int:
    limits = settings.file_limits
    return limits.per_format_max_size_mb.get(fmt, limits.default_max_size_mb)


def _source_locator(file: Any) -> str:
    return file.input_url or file.object_key or file.filename or f"inline.{file.source_format}"


def _default_target_for_source(source: str, settings: Settings) -> str | None:
    src = source.lower()
    for plugin in REGISTRY.list():
        if plugin.source_format.lower() == src:
            return plugin.target_format
    for fmt in settings.convert_formats:
        if fmt.source.lower() == src:
            return fmt.target
    return None


def _apply_default_targets(payload: ConversionRequest, settings: Settings) -> None:
    """Populate missing target_format using the first registered/configured mapping."""

    for file in payload.files:
        if file.target_format:
            continue
        inferred = _default_target_for_source(file.source_format, settings)
        if not inferred:
            locator = _source_locator(file)
            raise_error(
                "ERR_FORMAT_UNSUPPORTED",
                detail=f"No default target configured for {file.source_format} (source={locator})",
            )
        file.target_format = inferred


def _validate_request(payload: ConversionRequest, settings: Settings) -> None:
    limits = settings.file_limits
    files = payload.files
    mode = payload.mode.lower() if payload.mode else "async"

    _apply_default_targets(payload, settings)

    if not files:
        raise_error("ERR_FORMAT_UNSUPPORTED")

    if mode == "sync" and len(files) > 1:
        raise_error("ERR_BATCH_LIMIT_EXCEEDED", detail="sync mode only supports a single file")

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

    doc_formats = {"doc", "docx", "ppt", "pptx", "html"}
    av_formats = {
        "wav",
        "flac",
        "ogg",
        "aac",
        "avi",
        "mov",
        "mkv",
        "webm",
        "mpeg",
        "gif",
        "flv",
        "ts",
        "m4v",
        "3gp",
    }
    for file in files:
        fmt = file.source_format.lower()
        per_limit = _per_format_limit(settings, fmt)
        if file.size_mb > per_limit:
            raise_error("ERR_FILE_TOO_LARGE")
        if (fmt, file.target_format.lower()) not in supported:
            locator = _source_locator(file)
            raise_error(
                "ERR_FORMAT_UNSUPPORTED",
                detail=f"Unsupported format {fmt}->{file.target_format.lower()} (source={locator})",
            )

        if file.page_limit is not None and file.duration_seconds is not None:
            raise_error("ERR_FORMAT_UNSUPPORTED")

        if file.page_limit is not None:
            if fmt not in doc_formats:
                locator = _source_locator(file)
                raise_error(
                    "ERR_FORMAT_UNSUPPORTED",
                    detail=f"page_limit only allowed for doc formats (source={locator})",
                )

        if file.duration_seconds is not None:
            if fmt not in av_formats:
                locator = _source_locator(file)
                raise_error(
                    "ERR_FORMAT_UNSUPPORTED",
                    detail=f"duration_seconds only allowed for audio/video formats (source={locator})",
                )


def _run_sync_conversion(payload: ConversionRequest, settings: Settings) -> ConversionResponse:
    file_meta = payload.files[0].model_dump(mode="json")
    storage_override = payload.storage.model_dump(exclude_none=True) if payload.storage else None
    task_settings = _apply_storage_override(settings, storage_override)
    use_cache = not bool(storage_override)
    task_id = str(uuid4())

    source = file_meta.get("source_format")
    target = file_meta.get("target_format")
    try:
        plugin = REGISTRY.get(source, target)
    except KeyError:
        locator = _source_locator(payload.files[0])
        raise_error(
            "ERR_FORMAT_UNSUPPORTED",
            detail=f"Unsupported format {source}->{target} (source={locator})",
        )

    try:
        input_path = _materialize_input(file_meta, task_settings, use_cache=use_cache)
    except Exception as exc:  # pragma: no cover - defensive
        raise_error("ERR_TASK_FAILED", detail=str(exc))

    conversion_input = ConversionInput(
        source_format=source,
        target_format=target,
        input_path=input_path,
        input_url=file_meta.get("input_url"),
        object_key=file_meta.get("object_key"),
        metadata={
            "requested_by": None,
            "page_limit": file_meta.get("page_limit"),
            "duration_seconds": file_meta.get("duration_seconds"),
        },
    )
    try:
        result = plugin.convert(conversion_input)
    except Exception as exc:  # pragma: no cover - defensive
        raise_error("ERR_TASK_FAILED", detail=str(exc))

    output_path = Path(result.output_path) if result.output_path else None
    output_object = result.object_key
    if not output_object:
        try:
            output_object = _upload_output(output_path, task_settings, task_id, use_cache=use_cache)
        except Exception as exc:  # pragma: no cover - defensive
            raise_error("ERR_TASK_FAILED", detail=f"Upload failed: {exc}")

    download_url = _build_download_url(output_object, task_settings, use_cache=use_cache)

    conv_result = ConversionResultPayload(
        source=source,
        target=target,
        status="success",
        output_path=str(output_path) if output_path else None,
        object_key=output_object,
        download_url=download_url,
        metadata=result.metadata,
    )

    return ConversionResponse(
        status="success",
        task_id=task_id,
        message="Task completed synchronously",
        results=[conv_result],
    )


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

    if payload.mode == "sync":
        response = _run_sync_conversion(payload, settings)
        return JSONResponse(status_code=status.HTTP_200_OK, content=response.model_dump())

    task_id = str(uuid4())
    message = "Task accepted and scheduled for conversion"
    task_payload = {
        "task_id": task_id,
        "files": [file.model_dump(mode="json") for file in payload.files],
        "priority": payload.priority,
        "callback_url": str(payload.callback_url) if payload.callback_url else None,
        "storage": payload.storage.model_dump(exclude_none=True) if payload.storage else None,
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
