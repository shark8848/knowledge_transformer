"""Configuration for the Ali Bailian multimodal service."""

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
    default_queue: str = "mm"
    task_time_limit_sec: int = 300
    prefetch_multiplier: int = 2


class BailianSettings(BaseModel):
    # Allow both MM_* envs (via BaseSettings) and legacy BAILIAN_* envs (via default_factory fallbacks).
    api_base: str = Field(
        default_factory=lambda: os.getenv(
            "MM_bailian__api_base",
            os.getenv("BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        )
    )
    api_key: Optional[str] = Field(
        default_factory=lambda: os.getenv("MM_bailian__api_key", os.getenv("BAILIAN_API_KEY")),
        description="Ali Bailian API key",
    )
    model: str = Field(
        default_factory=lambda: os.getenv(
            "MM_bailian__model",
            os.getenv("BAILIAN_MULTIMODAL_MODEL", os.getenv("BAILIAN_LLM_MODEL", "qwen-vl-plus")),
        )
    )
    embedding_model: Optional[str] = Field(
        default_factory=lambda: os.getenv("BAILIAN_EMBEDDING_MODEL"),
        description="Optional embedding model name",
    )
    llm_model: Optional[str] = Field(
        default_factory=lambda: os.getenv("BAILIAN_LLM_MODEL"),
        description="Optional LLM model name (compat only)",
    )
    request_timeout_sec: int = 60
    max_retries: int = 1
    user_prompt: str = "请分析这段图片或视频内容并给出概要描述、关键实体和场景。"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MM_", env_nested_delimiter="__", extra="allow")

    service_name: str = "multimodal-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    bailian: BailianSettings = BailianSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
