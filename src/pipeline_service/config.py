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

    file_manager_base_url: AnyUrl | str = Field(
        "http://10.88.162.151:8989", description="File management server base URL"
    )
    file_manager_download_path: str = Field(
        "/km/fm/downloadOriginal", description="Download endpoint path on the file server"
    )
    file_manager_upload_path: str = Field(
        "/km/fm/fileUpload", description="Upload endpoint path on the file server"
    )
    file_manager_attach_id_param: str = Field(
        "attachid", description="Query parameter name carrying the attachment identifier"
    )
    file_manager_file_field: str = Field(
        "uploadFile", description="Multipart field name used for uploads (SI-TECH default is uploadFile)"
    )
    file_manager_default_form_fields: dict[str, str | int] = Field(
        default_factory=lambda: {"source": "2", "attachType": "0"},
        description="Default form fields sent with uploads to SI-TECH server (attachType/attactType configurable)",
    )
    file_manager_timeout_sec: int = Field(120, description="HTTP timeout for file server operations")
    file_manager_verify_tls: bool = Field(True, description="Verify TLS certificates for file server calls")
    file_manager_auth_header: str = Field(
        "Authorization", description="Header name for token-based authentication when provided"
    )
    file_manager_token_prefix: str = Field(
        "Bearer ", description="Prefix prepended to the auth token (leave blank to disable)"
    )
    file_manager_auth_token: Optional[str] = Field(None, description="Optional auth token for the file server")
    file_manager_extra_headers: dict[str, str] = Field(
        default_factory=dict, description="Additional headers to send to the file server"
    )

    sample_pages: int = Field(5, description="Legacy fixed page count for probing (fallback)")
    sample_page_ratio: float = Field(0.2, description="比例抽页，基于文档页数，最大不超过10页")
    sample_char_limit: int = Field(5000, description="仅按字符抽取时的上限长度")
    probe_timeout_sec: int = Field(60, description="Timeout for probe tasks")
    conversion_timeout_sec: int = Field(180, description="Timeout for conversion task result")

    log_dir: str = Field("./logs", description="Directory for pipeline log files")
    log_level: str = Field("INFO", description="Root log level")
    log_backup_count: int = Field(7, description="Number of rotated log files to keep")

    api_title: str = "Pipeline Service"
    api_version: str = "v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
