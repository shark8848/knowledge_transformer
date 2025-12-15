"""API routes for the video slicing service."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, settings_dependency
from ..errors import raise_error
from ..schemas import SliceRequest, SliceResponse
from ..security import authenticate_request
from ..tasks import orchestrate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/video/slice",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SliceResponse,
    dependencies=[Depends(authenticate_request)],
)
async def slice_video(payload: SliceRequest, settings: Settings = Depends(settings_dependency)) -> SliceResponse:
    if not payload.media.object_key and not payload.media.input_url:
        raise_error("ERR_BAD_REQUEST", detail="object_key or input_url required")

    try:
        orchestration = orchestrate.delay(payload.model_dump())
    except Exception as exc:  # noqa: BLE001
        logger.exception("orchestrate failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return SliceResponse(task_id=orchestration.id, status="accepted", result=None)
