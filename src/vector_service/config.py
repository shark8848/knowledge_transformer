"""Configuration for the vector service (embeddings and rerank)."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class CeleryQueueSettings(BaseModel):
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_queue: str = "vector"
    task_time_limit_sec: int = 600
    prefetch_multiplier: int = 2


class BailianSettings(BaseModel):
    api_key: Optional[str] = None
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embed_model: str = "text-embedding-v1"
    rerank_model: str = "qwen-plus"
    request_timeout_sec: int = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="VECTOR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    service_name: str = "vector-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    celery: CeleryQueueSettings = CeleryQueueSettings()
    bailian: BailianSettings = BailianSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
