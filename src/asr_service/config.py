"""Configuration for the independent ASR service powered by Whisper."""

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
    default_queue: str = "asr"
    task_time_limit_sec: int = 900
    prefetch_multiplier: int = 2


class ProcessingSettings(BaseModel):
    model_name: str = "base"
    device: str = "cpu"
    task: str = "transcribe"
    language: Optional[str] = None
    temperature: float = 0.0
    beam_size: Optional[int] = None
    download_timeout_sec: int = 30
    tmp_dir: str = "/tmp/asr_service"
    initial_prompt: Optional[str] = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ASR_", env_nested_delimiter="__", extra="allow")

    service_name: str = "asr-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    processing: ProcessingSettings = ProcessingSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
