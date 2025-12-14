"""Configuration for pipeline service orchestration."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PIPELINE_", env_nested_delimiter="__", extra="allow")

    redis_broker: str = Field("redis://localhost:6379/0", description="Shared Redis broker with other services")
    redis_backend: str = Field("redis://localhost:6379/2", description="Result backend for pipeline orchestration")

    pipeline_queue: str = Field("pipeline", description="Queue for pipeline orchestration tasks")
    conversion_queue: str = Field("conversion", description="Queue for converter tasks")
    probe_queue: str = Field("probe", description="Queue for probe/recommendation tasks")

    minio_endpoint: AnyUrl | str = Field("http://localhost:9000", description="MinIO/S3 endpoint")
    minio_access_key: str = Field("minioadmin", description="MinIO access key")
    minio_secret_key: str = Field("minioadmin", description="MinIO secret key")
    minio_bucket: str = Field("qadata", description="Bucket storing converted artifacts")

    sample_pages: int = Field(5, description="Legacy fixed page count for probing (fallback)")
    sample_page_ratio: float = Field(0.2, description="比例抽页，基于文档页数，最大不超过10页")
    sample_char_limit: int = Field(5000, description="仅按字符抽取时的上限长度")
    probe_timeout_sec: int = Field(60, description="Timeout for probe tasks")
    conversion_timeout_sec: int = Field(180, description="Timeout for conversion task result")

    api_title: str = "Pipeline Service"
    api_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
