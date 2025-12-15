"""Pydantic schemas for the Whisper ASR API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TranscriptionTask(str, Enum):
    transcribe = "transcribe"
    translate = "translate"


class AudioSource(BaseModel):
    format: Optional[str] = Field(default=None, description="File extension or mime")
    input_url: Optional[str] = None
    object_key: Optional[str] = None
    language: Optional[str] = Field(default=None, description="ISO-639 language hint")


class TranscriptionOptions(BaseModel):
    model_name: Optional[str] = Field(default=None, description="Whisper model size, e.g. base or medium")
    language: Optional[str] = None
    task: TranscriptionTask = TranscriptionTask.transcribe
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    beam_size: Optional[int] = Field(default=None, ge=1)
    initial_prompt: Optional[str] = None


class TranscribeRequest(BaseModel):
    source: AudioSource
    options: Optional[TranscriptionOptions] = None


class Segment(BaseModel):
    start: float
    end: float
    text: str


class TranscriptResult(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None
    segments: List[Segment] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranscribeResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[TranscriptResult] = None
