"""Configuration for the independent video slicing service."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIAuthSettings(BaseModel):
    required: bool = False
    header_appid: str = "X-Appid"
    header_key: str = "X-Key"
    appid: Optional[str] = None
    key: Optional[str] = None


class CeleryQueueSettings(BaseModel):
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_queue: str = "video"
    task_time_limit_sec: int = 600
    prefetch_multiplier: int = 2
    asr_queue: str = "video_asr"
    vision_queue: str = "video_vision"


class ProcessingSettings(BaseModel):
    frame_sample_fps: float = 0.5
    fixed_segment_seconds: int = 30
    scene_change_threshold: float = 0.35
    scene_min_duration_sec: float = 5.0
    asr_url: str = "http://asr-service/transcribe"
    vision_url: str = "http://vision-service/analyze"
    frame_caption_max: int = 8


class MinioSettings(BaseModel):
    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "qadata"
    secure: bool = False
    region: Optional[str] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VIDEO_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    service_name: str = "video-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    processing: ProcessingSettings = ProcessingSettings()
    minio: MinioSettings = MinioSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
