"""Centralized settings and configuration loading utilities."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FileLimitSettings(BaseModel):
    default_max_size_mb: int = Field(100, ge=1)
    per_format_max_size_mb: Dict[str, int] = Field(default_factory=dict)
    max_total_upload_size_mb: int = Field(500, ge=1)
    max_files_per_task: int = Field(10, ge=1)


class LoggingSettings(BaseModel):
    level: str = "INFO"
    log_dir: str = "./logs"
    rotation: str = "size"
    max_log_file_size_mb: int = 100
    backup_count: int = 7
    retention_days: int = 30


class MonitoringSettings(BaseModel):
    health_api: str = "/api/v1/monitor/health"
    traffic_api: str = "/api/v1/monitor/traffic"
    queue_api: str = "/api/v1/monitor/queue"
    dependencies_api: str = "/api/v1/monitor/dependencies"
    prometheus_port: int = 9091
    metrics_interval_sec: int = 15


class StorageSettings(BaseModel):
    endpoint: str = "http://minio:9000"
    access_key: str = "access_key"
    secret_key: str = "secret_key"
    bucket: str = "qadata"
    timeout: int = 30
    public_endpoint: str | None = None
    presign_expiry_sec: int | None = 0


class ConversionFormat(BaseModel):
    source: str
    target: str
    plugin: Optional[str] = None


class APIAuthSettings(BaseModel):
    required: bool = True
    app_secrets_path: str = "./secrets/appkeys.json"
    header_appid: str = "X-Appid"
    header_key: str = "X-Key"


class CeleryQueueSettings(BaseModel):
    broker_url: str = "redis://localhost:6379/0"
    result_backend: str = "redis://localhost:6379/1"
    default_queue: str = "conversion"
    task_time_limit_sec: int = 300
    prefetch_multiplier: int = 4


class RateLimitSettings(BaseModel):
    enabled: bool = False
    interval_sec: int = 60
    max_requests: int = 100


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RAG_", env_nested_delimiter="__", extra="allow")

    service_name: str = "rag-conversion-engine"
    environment: str = "dev"
    api_version: str = "v1"
    base_url: str = "/api/v1"

    file_limits: FileLimitSettings = FileLimitSettings()
    logging: LoggingSettings = LoggingSettings()
    monitoring: MonitoringSettings = MonitoringSettings()
    minio: StorageSettings = StorageSettings()
    convert_formats: list[ConversionFormat] = Field(default_factory=list)
    plugin_modules: list[str] = Field(default_factory=list)
    plugin_modules_file: str | None = "./config/plugins.yaml"
    plugin_deps_file: str | None = "./config/plugins-deps.yaml"
    api_auth: APIAuthSettings = APIAuthSettings()
    celery: CeleryQueueSettings = CeleryQueueSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()

    @staticmethod
    def load_yaml_config_file(file_path: str | Path | None) -> Dict[str, Any]:
        if not file_path:
            return {}
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        import yaml  # lazy import for optional dependency

        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("Configuration YAML must produce a mapping")
        return data

    @classmethod
    def from_source(cls, *, config_file: str | None = None, **overrides: Any) -> "Settings":
        base_data = cls.load_yaml_config_file(config_file)
        base_data.update(overrides)
        return cls(**base_data)


@lru_cache
def get_settings() -> Settings:
    cfg_file = os.getenv("RAG_CONFIG_FILE")
    if cfg_file:
        return Settings.from_source(config_file=cfg_file)

    default_path = Path.cwd() / "config" / "settings.yaml"
    if default_path.exists():
        return Settings.from_source(config_file=str(default_path))

    return Settings()


def reload_settings() -> None:
    get_settings.cache_clear()


def settings_dependency() -> Settings:
    return get_settings()
