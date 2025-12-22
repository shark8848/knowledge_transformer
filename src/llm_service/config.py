"""Configuration for the generic LLM service."""

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
    default_queue: str = "llm"
    task_time_limit_sec: int = 600
    prefetch_multiplier: int = 2


class BailianSettings(BaseModel):
    api_key: Optional[str] = None
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    request_timeout_sec: int = 60


class TeamshubSettings(BaseModel):
    token: Optional[str] = None
    api_base: str = (
        "https://aicp.teamshub.com/ai-paas/ai-open/sitech/aiopen/stream/aliyun-Qwen3-32B-developing-ws/v1/chat/completions"
    )
    model: str = "qwen3-32b"
    stream: bool = True
    enable_thinking: bool = False
    request_timeout_sec: int = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LLM_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    service_name: str = "llm-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    default_provider: str = "bailian"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    bailian: BailianSettings = BailianSettings()
    teamshub: TeamshubSettings = TeamshubSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
