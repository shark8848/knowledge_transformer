"""Celery application wired with conversion plugins."""

from __future__ import annotations

import base64
import errno
import logging
import os
import shutil
from binascii import Error as BinasciiError
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import uuid4

from celery import Celery, signals
from minio import Minio

from .config import Settings, get_settings
from .monitoring import ensure_metrics_server, record_task_completed
from .plugins import REGISTRY, load_plugins_from_settings
from .plugins.base import ConversionInput

logger = logging.getLogger(__name__)


def _create_celery(settings: Settings) -> Celery:
    app = Celery(settings.service_name)
    app.conf.update(
        broker_url=settings.celery.broker_url,
        result_backend=settings.celery.result_backend,
        task_default_queue=settings.celery.default_queue,
        task_time_limit=settings.celery.task_time_limit_sec,
        worker_prefetch_multiplier=settings.celery.prefetch_multiplier,
    )
    return app


SETTINGS = get_settings()
load_plugins_from_settings(SETTINGS)
celery_app = _create_celery(SETTINGS)
_worker_metrics_started = False
WORK_DIR = Path(os.getenv("RAG_WORK_DIR", "/tmp/rag_converter"))
WORK_DIR.mkdir(parents=True, exist_ok=True)
_TEST_ARTIFACTS_DIR_ENV = os.getenv("RAG_TEST_ARTIFACTS_DIR")
TEST_ARTIFACTS_DIR = Path(_TEST_ARTIFACTS_DIR_ENV).expanduser() if _TEST_ARTIFACTS_DIR_ENV else None
_MINIO_CLIENT: Optional[Minio] = None


def _apply_storage_override(settings: Settings, override: Optional[Dict[str, Any]]) -> Settings:
    if not override:
        return settings

    merged_minio = settings.minio.model_copy(
        update={k: v for k, v in override.items() if v is not None}
    )
    return settings.model_copy(update={"minio": merged_minio})


def _build_minio_client(settings: Settings) -> Minio:
    parsed = urlparse(settings.minio.endpoint)
    secure = parsed.scheme == "https"
    netloc = parsed.netloc or parsed.path
    return Minio(
        netloc,
        access_key=settings.minio.access_key,
        secret_key=settings.minio.secret_key,
        secure=secure,
    )


def _get_minio_client(settings: Settings, *, use_cache: bool = True) -> Minio:
    global _MINIO_CLIENT
    if use_cache and _MINIO_CLIENT is not None:
        return _MINIO_CLIENT

    client = _build_minio_client(settings)
    if use_cache:
        _MINIO_CLIENT = client
    return client


def _workspace_file(filename: str) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR / f"{uuid4().hex}_{filename}"


def _source_locator(file_meta: Dict[str, Any]) -> str:
    """Mirror API-side locator for clearer worker errors without re-validating."""

    return (
        file_meta.get("input_url")
        or file_meta.get("object_key")
        or file_meta.get("filename")
        or f"inline.{file_meta.get('source_format', 'bin')}"
    )


def _materialize_input(file_meta: Dict[str, Any], settings: Settings, use_cache: bool = True) -> Path:
    if file_meta.get("base64_data"):
        raw_b64: str = file_meta["base64_data"]
        try:
            decoded = base64.b64decode(raw_b64, validate=True)
        except (BinasciiError, ValueError) as exc:
            raise ValueError("Invalid base64_data payload") from exc

        filename = file_meta.get("filename")
        if not filename:
            src_fmt = (file_meta.get("source_format") or "").split("/")[-1]
            extension = src_fmt or "bin"
            filename = f"inline.{extension}"

        dest = _workspace_file(filename)
        with dest.open("wb") as handle:
            handle.write(decoded)
        return dest

    if file_meta.get("local_path"):
        path = Path(file_meta["local_path"])
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: {path}")
        return path

    if object_key := file_meta.get("object_key"):
        filename = Path(object_key).name or f"input_{uuid4().hex}"
        dest = _workspace_file(filename)
        client = _get_minio_client(settings, use_cache=use_cache)
        client.fget_object(settings.minio.bucket, object_key, str(dest))
        return dest

    if input_url := file_meta.get("input_url"):
        parsed = urlparse(input_url)
        filename = Path(parsed.path).name or "input.bin"
        dest = _workspace_file(filename)
        with urlopen(input_url, timeout=30) as response, dest.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        return dest

    raise ValueError("No input source provided (object_key or input_url required)")


def _upload_output(
    path: Path | None, settings: Settings, task_id: str | None, use_cache: bool = True
) -> Optional[str]:
    if not path or not Path(path).exists():
        return None
    object_key = f"converted/{task_id or uuid4().hex}/{Path(path).name}"
    client = _get_minio_client(settings, use_cache=use_cache)
    client.fput_object(settings.minio.bucket, object_key, str(path))
    return object_key


def _store_test_artifact(path: Path | None, task_id: str | None) -> None:
    """Persist conversion output into a shared tests directory when configured."""

    if not path:
        return

    target_path = Path(path)
    if not target_path.exists():
        return

    global TEST_ARTIFACTS_DIR
    artifact_dir = TEST_ARTIFACTS_DIR
    if not artifact_dir:
        env_dir = os.getenv("RAG_TEST_ARTIFACTS_DIR")
        if not env_dir:
            return
        artifact_dir = Path(env_dir).expanduser()
        TEST_ARTIFACTS_DIR = artifact_dir

    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
        dest_name = f"{task_id}_{target_path.name}" if task_id else target_path.name
        shutil.copy2(target_path, artifact_dir / dest_name)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.debug("Unable to persist test artifact", exc_info=exc)


def _ensure_worker_metrics_started() -> None:
    """Start worker-side metrics exactly once per process."""

    global _worker_metrics_started
    if _worker_metrics_started:
        return

    try:
        ensure_metrics_server(SETTINGS.monitoring.prometheus_port + 1)
    except OSError as exc:  # pragma: no cover - defensive on prefork workers
        if exc.errno != errno.EADDRINUSE:
            raise
        logger.debug("Worker metrics server already running", exc_info=exc)
    _worker_metrics_started = True


@signals.worker_ready.connect
def _on_worker_ready(sender=None, **kwargs):  # type: ignore[override]
    _ensure_worker_metrics_started()


@celery_app.task(name="conversion.handle_batch")
def handle_conversion_task(payload: Dict[str, Any]) -> Dict[str, Any]:
    _ensure_worker_metrics_started()

    storage_override = payload.get("storage")
    task_settings = _apply_storage_override(SETTINGS, storage_override)
    use_cache = not bool(storage_override)

    task_id = payload.get("task_id")
    files: List[Dict[str, Any]] = payload.get("files", [])
    results: List[Dict[str, Any]] = []

    for file_meta in files:
        source = file_meta.get("source_format")
        target = file_meta.get("target_format")
        try:
            plugin = REGISTRY.get(source, target)
        except KeyError as exc:
            logger.exception("Unsupported format: %s -> %s", source, target)
            record_task_completed("failed")
            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "failed",
                    "reason": f"Unsupported format {source}->{target} (source={_source_locator(file_meta)})",
                }
            )
            continue

        try:
            input_path = _materialize_input(file_meta, task_settings, use_cache=use_cache)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to prepare input for %s -> %s", source, target)
            record_task_completed("failed")
            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "failed",
                    "reason": f"Input preparation failed (source={_source_locator(file_meta)}): {exc}",
                }
            )
            continue

        conversion_input = ConversionInput(
            source_format=source,
            target_format=target,
            input_path=input_path,
            input_url=file_meta.get("input_url"),
            object_key=file_meta.get("object_key"),
            metadata={
                "requested_by": payload.get("requested_by"),
                "page_limit": file_meta.get("page_limit"),
                "duration_seconds": file_meta.get("duration_seconds"),
            },
        )
        try:
            result = plugin.convert(conversion_input)
            output_path = Path(result.output_path) if result.output_path else None
            output_object = result.object_key
            if not output_object:
                try:
                    output_object = _upload_output(
                        output_path, task_settings, task_id, use_cache=use_cache
                    )
                except Exception as upload_exc:  # pragma: no cover - defensive logging
                    logger.exception("Failed to upload output for %s -> %s", source, target)

            _store_test_artifact(output_path, task_id)

            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "success",
                    "output_path": str(output_path) if output_path else None,
                    "object_key": output_object,
                    "metadata": result.metadata,
                }
            )
            record_task_completed("success")
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Conversion failed for %s -> %s", source, target)
            record_task_completed("failed")
            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "failed",
                    "reason": str(exc),
                }
            )

    return {
        "task_id": task_id,
        "results": results,
    }
