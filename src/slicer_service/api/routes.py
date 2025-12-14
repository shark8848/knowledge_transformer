"""API routes for the standalone slicer/recommendation service."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from ..config import Settings, settings_dependency
from ..recommendation import _round_profile, extract_signals_from_samples, recommend_strategy
from ..security import authenticate_request
from ..errors import raise_error
from .schemas import (
    CustomDelimiterConfig,
    ProbeRequest,
    ProfileResponse,
    StrategyRecommendRequest,
    StrategyRecommendResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "/probe/profile",
    status_code=status.HTTP_200_OK,
    response_model=ProfileResponse,
    dependencies=[Depends(authenticate_request)],
)
async def probe_profile(payload: ProbeRequest, settings: Settings = Depends(settings_dependency)) -> ProfileResponse:
    try:
        profile = extract_signals_from_samples(payload.samples)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    clean_profile = _round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3)
    logger.info("probe_profile: profile=%s", clean_profile)
    return ProfileResponse(profile=clean_profile)


@router.post(
    "/probe/recommend_strategy",
    status_code=status.HTTP_200_OK,
    response_model=StrategyRecommendResponse,
    dependencies=[Depends(authenticate_request)],
)
async def recommend_slice_strategy(
    payload: StrategyRecommendRequest, settings: Settings = Depends(settings_dependency)
) -> StrategyRecommendResponse:
    custom_cfg = payload.custom.model_dump() if payload.custom else {}
    try:
        profile = extract_signals_from_samples(payload.samples)
        
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    clean_profile = _round_profile({k: v for k, v in profile.items() if k != "para_lengths"}, 3)
    logger.info("recommend_slice_strategy: profile=%s", clean_profile)

    recommendation = recommend_strategy(
        profile,
        samples=payload.samples,
        custom_cfg=custom_cfg,
        emit_candidates=payload.emit_candidates,
        source_format=payload.source_format,
    )
    return StrategyRecommendResponse(recommendation=recommendation)
