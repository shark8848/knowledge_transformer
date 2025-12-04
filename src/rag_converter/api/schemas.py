"""Request and response models for the conversion API."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, HttpUrl


class ConversionFile(BaseModel):
    source_format: str = Field(..., description="Original file format, e.g., doc")
    target_format: str = Field(..., description="Desired output format, e.g., docx")
    input_url: HttpUrl | None = Field(None, description="Optional URL to fetch input")
    object_key: str | None = Field(None, description="Storage object key reference")
    size_mb: float = Field(..., ge=0.0, description="Reported file size in megabytes")


class ConversionRequest(BaseModel):
    task_name: str = Field(..., description="Human-readable task identifier")
    files: List[ConversionFile]
    priority: Literal["low", "normal", "high"] = "normal"
    callback_url: HttpUrl | None = Field(
        None, description="Optional webhook notified after conversion"
    )


class ConversionResponse(BaseModel):
    status: Literal["accepted", "failure"]
    task_id: str | None = None
    message: str | None = None
    error_code: str | None = None
    error_status: int | None = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    timestamp: datetime
    dependencies: dict[str, str] = Field(default_factory=dict)


class FormatDescriptor(BaseModel):
    source: str
    target: str
    plugin: Optional[str] = None


class FormatsResponse(BaseModel):
    formats: List[FormatDescriptor]
