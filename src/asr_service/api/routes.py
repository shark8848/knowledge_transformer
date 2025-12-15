"""API routes for the Whisper ASR service."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from celery.result import AsyncResult

from ..config import Settings, settings_dependency
from ..errors import raise_error
from ..schemas import TranscribeRequest, TranscribeResponse
from ..security import authenticate_request
from ..tasks import orchestrate
from ..celery_app import asr_celery

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/asr/transcribe",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TranscribeResponse,
    dependencies=[Depends(authenticate_request)],
)
async def transcribe(payload: TranscribeRequest, settings: Settings = Depends(settings_dependency)) -> TranscribeResponse:
    if not payload.source.object_key and not payload.source.input_url:
        raise_error("ERR_BAD_REQUEST", detail="object_key or input_url required")

    try:
        orchestration = orchestrate.delay(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.exception("orchestrate failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return TranscribeResponse(task_id=orchestration.id, status="accepted", result=None)


@router.get(
    "/asr/result/{task_id}",
    status_code=status.HTTP_200_OK,
    response_model=TranscribeResponse,
    dependencies=[Depends(authenticate_request)],
)
async def get_result(task_id: str) -> TranscribeResponse:
    async_result = AsyncResult(task_id, app=asr_celery)

    # Follow nested task_id returned by orchestrator to the final transcribe result.
    max_hops = 3
    hops = 0
    while hops < max_hops and async_result.successful():
        payload = async_result.result
        if isinstance(payload, dict) and "text" in payload:
            return TranscribeResponse(task_id=task_id, status="success", result=payload)  # type: ignore[arg-type]
        if isinstance(payload, dict) and "task_id" in payload:
            async_result = AsyncResult(str(payload["task_id"]), app=asr_celery)
            hops += 1
            continue
        break

    status_str = async_result.status.lower()
    if async_result.failed():
        detail = str(async_result.result)
        raise HTTPException(status_code=500, detail=detail)

    result_payload = async_result.result if async_result.successful() else None
    return TranscribeResponse(task_id=task_id, status=status_str, result=result_payload)  # type: ignore[arg-type]
