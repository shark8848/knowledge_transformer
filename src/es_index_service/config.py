"""Configuration for ES schema/index service."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class CelerySettings(BaseSettings):
    broker_url: str = Field(
        default="redis://localhost:6379/0",
        description="Celery broker URL",
    )
    result_backend: str = Field(
        default="redis://localhost:6379/1",
        description="Celery result backend",
    )
    default_queue: str = Field(default="es-schema-tasks")
    task_time_limit_sec: int = Field(default=300)
    prefetch_multiplier: int = Field(default=1)


class ESSettings(BaseSettings):
    endpoint: str = Field(default="http://localhost:9200")
    username: Optional[str] = None
    password: Optional[str] = None
    verify_ssl: bool = Field(default=False)
    request_timeout_sec: int = Field(default=30)
    base_index: str = Field(default="kb_chunks")
    default_index: str = Field(default="kb_chunks_v1")
    read_alias: str = Field(default="kb_chunks")
    write_alias: str = Field(default="kb_chunks_write")
    default_shards: int = Field(default=3)
    default_replicas: int = Field(default=1)
    refresh_interval: str = Field(default="10s")
    mapping_path: Path = Field(default=Path("config/kb_chunks_v1_mapping.json"))


class ServiceSettings(BaseSettings):
    service_name: str = Field(default="es-index-service")
    api_version: str = Field(default="v1")
    base_url: str = Field(default="")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8085)
    grpc_port: int = Field(default=9105)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    es: ESSettings = Field(default_factory=ESSettings)

    model_config = {
        "env_prefix": "ES_INDEX_SERVICE_",
        "env_nested_delimiter": "__",
        "extra": "ignore",
    }


def _apply_legacy_env_prefix() -> None:
    """Allow ES_SERVICE_* variables to continue working by mapping to the new prefix."""

    legacy_prefix = "ES_SERVICE_"
    new_prefix = "ES_INDEX_SERVICE_"
    for key, value in os.environ.items():
        if not key.startswith(legacy_prefix):
            continue
        suffix = key[len(legacy_prefix) :]
        mapped = f"{new_prefix}{suffix}"
        os.environ.setdefault(mapped, value)


@lru_cache(maxsize=1)
def get_settings() -> ServiceSettings:
    _apply_legacy_env_prefix()
    return ServiceSettings()
