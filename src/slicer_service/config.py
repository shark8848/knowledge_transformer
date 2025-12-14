"""Configuration for the independent slicing/recommendation service."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic import BaseModel, Field
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
    default_queue: str = "probe"
    task_time_limit_sec: int = 120
    prefetch_multiplier: int = 4


class MonitoringSettings(BaseModel):
    prometheus_port: int = 9093
    enable_metrics: bool = True


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SLICE_", env_nested_delimiter="__", extra="allow")

    service_name: str = "slicer-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    monitoring: MonitoringSettings = MonitoringSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
