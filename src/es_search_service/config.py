"""Configuration for ES search service."""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class CelerySettings(BaseSettings):
    broker_url: str = Field(default="redis://localhost:6379/0", description="Celery broker URL")
    result_backend: str = Field(default="redis://localhost:6379/1", description="Celery result backend")
    default_queue: str = Field(default="es-search-tasks")
    task_time_limit_sec: int = Field(default=120)
    prefetch_multiplier: int = Field(default=1)


class ESSettings(BaseSettings):
    endpoint: str = Field(default="http://localhost:9200")
    username: Optional[str] = None
    password: Optional[str] = None
    verify_ssl: bool = Field(default=False)
    request_timeout_sec: int = Field(default=30)
    read_alias: str = Field(default="kb_chunks")
    default_index: str = Field(default="kb_chunks_v1")
    vector_field: str = Field(default="embedding")
    default_num_candidates: int = Field(default=200, ge=1, description="Default KNN num_candidates")
    text_fields: List[str] = Field(
        default_factory=lambda: [
            "title^2",
            "content^3",
            "summary",
            "keywords^1.5",
            "content_values",
        ],
    )


class ServiceSettings(BaseSettings):
    service_name: str = Field(default="es-search-service")
    api_version: str = Field(default="v1")
    base_url: str = Field(default="")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8086)
    grpc_port: int = Field(default=9106)
    celery: CelerySettings = Field(default_factory=CelerySettings)
    es: ESSettings = Field(default_factory=ESSettings)

    model_config = {
        "env_prefix": "ES_SEARCH_SERVICE_",
        "env_nested_delimiter": "__",
        "extra": "ignore",
    }


@lru_cache(maxsize=1)
def get_settings() -> ServiceSettings:
    return ServiceSettings()
