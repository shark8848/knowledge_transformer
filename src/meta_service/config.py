"""Configuration for the metadata extraction service."""

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
    default_queue: str = "meta"
    task_time_limit_sec: int = 600
    prefetch_multiplier: int = 2


class BailianSettings(BaseModel):
    api_key: Optional[str] = None
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-plus"
    request_timeout_sec: int = 60


class MinioSettings(BaseModel):
    endpoint: str = "http://localhost:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "qadata"
    secure: bool = False
    region: Optional[str] = None


class ProcessingSettings(BaseModel):
    max_chunks: int = 30
    summary_words: int = 120
    prompt_template: str = (
        "你是文档元数据抽取助手。请仅输出 JSON，包含键: summary(中文摘要), tags(字符串列表), "
        "keywords(字符串列表), questions(字符串列表)。摘要控制在 {{ summary_words }} 字以内。\n"
        "输入上下文：\n"
        "- 文档标题：{{ title }}\n"
        "- Chunk 时间范围：{{ start }}s - {{ end }}s\n"
        "- 文本内容：\n{{ text }}\n"
        "- 关键帧描述：\n{% for kf in keyframes %}- t={{ kf.timestamp }}s: {{ kf.description }}\n{% endfor %}"
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="META_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    service_name: str = "meta-service"
    api_version: str = "v1"
    base_url: str = "/api/v1"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    bailian: BailianSettings = BailianSettings()
    minio: MinioSettings = MinioSettings()
    processing: ProcessingSettings = ProcessingSettings()


@lru_cache
def get_settings() -> Settings:
    return Settings()


def settings_dependency() -> Settings:
    return get_settings()
