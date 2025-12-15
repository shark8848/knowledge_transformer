"""API routes for the Bailian multimodal service."""

from __future__ import annotations

import logging

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status

from ..celery_app import mm_celery
from ..config import Settings, settings_dependency
from ..errors import raise_error
from ..schemas import AnalysisResponse, MediaSource
from ..security import authenticate_request
from ..tasks import orchestrate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/mm/analyze",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AnalysisResponse,
    dependencies=[Depends(authenticate_request)],
)
async def analyze(payload: MediaSource, settings: Settings = Depends(settings_dependency)) -> AnalysisResponse:
    if not payload.input_url and not payload.object_key:
        raise_error("ERR_BAD_REQUEST", detail="input_url or object_key required")

    try:
        orchestration = orchestrate.delay({"source": payload.model_dump()})
    except Exception as exc:  # noqa: BLE001
        logger.exception("orchestrate failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return AnalysisResponse(task_id=orchestration.id, status="accepted", result=None)


@router.get(
    "/mm/result/{task_id}",
    status_code=status.HTTP_200_OK,
    response_model=AnalysisResponse,
    dependencies=[Depends(authenticate_request)],
)
async def get_result(task_id: str) -> AnalysisResponse:
    async_result = AsyncResult(task_id, app=mm_celery)

    # Follow nested orchestrator task if needed.
    max_hops = 2
    hops = 0
    while hops < max_hops and async_result.successful():
        payload = async_result.result
        if isinstance(payload, dict) and ("text" in payload or "raw" in payload):
            return AnalysisResponse(task_id=task_id, status="success", result=payload)  # type: ignore[arg-type]
        if isinstance(payload, dict) and "task_id" in payload:
            async_result = AsyncResult(str(payload["task_id"]), app=mm_celery)
            hops += 1
            continue
        break

    status_str = (async_result.status or "").lower()
    if async_result.failed():
        detail = str(async_result.result)
        raise HTTPException(status_code=500, detail=detail)

    result_payload = async_result.result if async_result.successful() else None
    return AnalysisResponse(task_id=task_id, status=status_str, result=result_payload)  # type: ignore[arg-type]
