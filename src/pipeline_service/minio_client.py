"""MinIO client helper for pipeline service."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

from minio import Minio

from .config import get_settings


@lru_cache
def get_minio_client() -> Minio:
    settings = get_settings()
    endpoint = str(settings.minio_endpoint)
    parsed = urlparse(endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(netloc, access_key=settings.minio_access_key, secret_key=settings.minio_secret_key, secure=secure)
