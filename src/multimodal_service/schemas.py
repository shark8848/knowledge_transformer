"""Pydantic schemas for the multimodal analysis API (Ali Bailian)."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class MediaKind(str, Enum):
    image = "image"
    video = "video"


class MediaSource(BaseModel):
    kind: MediaKind = MediaKind.image
    input_url: Optional[str] = Field(default=None, description="Publicly reachable URL")
    object_key: Optional[str] = Field(default=None, description="Object storage key if proxied")
    prompt: Optional[str] = Field(default=None, description="User prompt override")
    model: Optional[str] = Field(default=None, description="Model override, e.g. qwen-vl-plus")


class AnalysisResult(BaseModel):
    text: Optional[str] = None
    raw: Dict[str, Any] = Field(default_factory=dict)


class AnalysisResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[AnalysisResult] = None
