"""Pydantic schemas for video slicing API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SliceMode(str, Enum):
    scene = "scene"
    fixed = "fixed"


class MediaSource(BaseModel):
    source_format: str = Field(description="File extension or mime")
    input_url: Optional[str] = None
    object_key: Optional[str] = None
    duration_seconds: Optional[float] = None


class SliceRequest(BaseModel):
    media: MediaSource
    mode: SliceMode = SliceMode.scene
    fixed_duration_seconds: Optional[int] = Field(default=None, ge=1)
    max_segments: Optional[int] = Field(default=200, ge=1)
    emit_candidates: bool = False


class TimeSpan(BaseModel):
    start: float
    end: float


class TrackFragment(BaseModel):
    kind: str
    uri: Optional[str] = None
    text: Optional[str] = None
    timespan: TimeSpan
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SliceResult(BaseModel):
    strategy: str
    segments: List[TimeSpan]
    tracks: List[TrackFragment]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SliceResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[SliceResult] = None
