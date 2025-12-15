"""MinIO helpers for the video service."""

from __future__ import annotations

import threading
from datetime import timedelta
from pathlib import Path
from typing import Dict
from urllib.parse import urlparse

from minio import Minio

from .config import get_settings

_settings = get_settings()
_client_lock = threading.Lock()
_client: Minio | None = None


def _build_client() -> Minio:
    parsed = urlparse(_settings.minio.endpoint)
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=_settings.minio.access_key,
        secret_key=_settings.minio.secret_key,
        secure=_settings.minio.secure if _settings.minio.secure is not None else parsed.scheme == "https",
        region=_settings.minio.region,
    )


def get_minio_client() -> Minio:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = _build_client()
        return _client


def ensure_bucket(client: Minio | None = None) -> str:
    client = client or get_minio_client()
    bucket = _settings.minio.bucket
    exists = client.bucket_exists(bucket)
    if not exists:
        client.make_bucket(bucket)
    return bucket

def presign_url(object_key: str, expires: int = 3600, client: Minio | None = None) -> str:
    client = client or get_minio_client()
    bucket = ensure_bucket(client)
    ttl = timedelta(seconds=expires)
    return client.presigned_get_object(bucket, object_key, expires=ttl)


def upload_file(path: Path, object_key: str, client: Minio | None = None) -> Dict[str, str]:
    client = client or get_minio_client()
    bucket = ensure_bucket(client)
    client.fput_object(bucket, object_key, str(path))
    url = presign_url(object_key, client=client)
    return {"bucket": bucket, "object_key": object_key, "url": url}


def download_object(object_key: str, dest: Path, client: Minio | None = None) -> Path:
    client = client or get_minio_client()
    bucket = ensure_bucket(client)
    client.fget_object(bucket, object_key, str(dest))
    return dest
