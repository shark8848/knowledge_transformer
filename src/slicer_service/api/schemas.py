"""Pydantic schemas for the slicer service APIs."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ProbeRequest(BaseModel):
    samples: List[str] = Field(..., description="Text probe samples")


class CustomDelimiterConfig(BaseModel):
    enable: bool = False
    delimiters: List[str] = Field(default_factory=list)
    min_segments: int = 5
    min_segment_len: int = 30
    max_segment_len: int = 800
    overlap_ratio: float | None = None


class ProfileFeatures(BaseModel):
    heading_ratio: float = 0.0
    list_ratio: float = 0.0
    table_ratio: float = 0.0
    code_ratio: float = 0.0
    p90_para_len: int = 0
    p50_para_len: int = 0
    digit_symbol_ratio: float | None = None
    samples: List[str] = Field(default_factory=list)


class ProfileResponse(BaseModel):
    profile: ProfileFeatures


class StrategyRecommendation(BaseModel):
    strategy_id: str
    mode: str
    mode_id: int | None = None
    mode_desc: str | None = None
    params: Dict[str, Any]
    candidates: Dict[str, float] | None = None
    delimiter_hits: int = 0
    profile: ProfileFeatures
    notes: str | None = None
    segments: Any | None = None


class StrategyRecommendRequest(BaseModel):
    samples: List[str] = Field(..., description="Text probe samples for recommendation")
    custom: CustomDelimiterConfig | None = None
    emit_candidates: bool = False
    source_format: str | None = Field(default=None, description="Optional normalized source format or extension")


class StrategyRecommendResponse(BaseModel):
    recommendation: StrategyRecommendation
