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
from urllib.parse import urlparse, parse_qs
from urllib.request import urlopen
from uuid import uuid4

from celery import Celery, signals
from minio import Minio
from pipeline_service.sitech_fm_client import FileUploadResult, get_sitech_fm_client

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
_SITECH_CLIENT = None


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


def _get_sitech_client():
    global _SITECH_CLIENT
    if _SITECH_CLIENT is None:
        _SITECH_CLIENT = get_sitech_fm_client()
    return _SITECH_CLIENT


def _workspace_file(filename: str) -> Path:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    return WORK_DIR / f"{uuid4().hex}_{filename}"


def _unwrap_download(path: Path) -> Path:
    """If a download produces a directory, pick the single file inside or fail with context."""

    if not path.is_dir():
        return path

    files = [p for p in path.rglob("*") if p.is_file()]
    if len(files) == 1:
        return files[0]

    entries = list(path.iterdir()) if path.exists() else []
    names = ", ".join(e.name for e in entries[:5])
    more = "" if len(entries) <= 5 else f" (+{len(entries)-5} more)"
    raise ValueError(f"Downloaded path is a directory: {path}; entries={names}{more}")


def _source_locator(file_meta: Dict[str, Any]) -> str:
    """Mirror API-side locator for clearer worker errors without re-validating."""

    return (
        file_meta.get("input_url")
        or file_meta.get("object_key")
        or file_meta.get("filename")
        or f"inline.{file_meta.get('source_format', 'bin')}"
    )


def _materialize_input(file_meta: Dict[str, Any], settings: Settings, use_cache: bool = True) -> Path:
    attach_id = file_meta.get("sitech_attach_id") or file_meta.get("sitech_fm_fileid")
    if attach_id:
        filename = file_meta.get("filename") or f"{attach_id}"
        dest = _workspace_file(filename)
        client = _get_sitech_client()
        client.download(attach_id, dest)
        return _unwrap_download(dest)

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
        return _unwrap_download(dest)

    if input_url := file_meta.get("input_url"):
        parsed = urlparse(input_url)

        # 如果是 SI-TECH 下载链接，优先走 sitech client（支持认证/默认参数）
        try:
            client = _get_sitech_client()
            cfg = getattr(client, "_config", None)
            if cfg:
                is_same_host = str(parsed.netloc).lower() == str(urlparse(cfg.base_url).netloc).lower()
                is_same_path = parsed.path.rstrip("/") == str(cfg.download_path).rstrip("/")
                q = parse_qs(parsed.query)
                attach_param = cfg.attach_id_param
                attach_val = q.get(attach_param, [None])[0]
                if is_same_host and is_same_path and attach_val:
                    filename = file_meta.get("filename") or Path(parsed.path).name or attach_val
                    dest = _workspace_file(filename)
                    client.download(attach_val, dest)
                    return _unwrap_download(dest)
        except Exception:
            # 回退走原始 URL 下载
            pass

        filename = Path(parsed.path).name or "input.bin"
        dest = _workspace_file(filename)
        with urlopen(input_url, timeout=30) as response, dest.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        return _unwrap_download(dest)

    raise ValueError("No input source provided (object_key or input_url required)")


def _upload_output(
    path: Path | None, settings: Settings, task_id: str | None, use_cache: bool = True
) -> Optional[str]:
    if not path or not Path(path).exists():
        return None
    if Path(path).is_dir():
        raise ValueError(f"Output path is a directory: {path}")
    object_key = f"converted/{task_id or uuid4().hex}/{Path(path).name}"
    client = _get_minio_client(settings, use_cache=use_cache)
    client.fput_object(settings.minio.bucket, object_key, str(path))
    return object_key


def _upload_input_to_sitech(path: Path) -> Optional[str]:
    """Upload original input to SI-TECH file manager; return fileid or None on failure."""

    if not path.exists():
        logger.warning("Sitech upload skipped; file not found: %s", path)
        return None

    try:
        client = _get_sitech_client()
        result: FileUploadResult = client.upload(path)
        return result.fileid
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Sitech upload failed for %s: %s", path, exc)
        return None


def _upload_output_to_sitech(path: Path | None) -> Optional[str]:
    """Upload converted output to SI-TECH; return fileid or None on failure."""

    if not path or not path.exists():
        return None
    if path.is_dir():
        return None

    try:
        client = _get_sitech_client()
        result: FileUploadResult = client.upload(path)
        return result.fileid
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning("Sitech output upload failed for %s: %s", path, exc)
        return None


def _build_download_url(object_key: str | None, settings: Settings, *, use_cache: bool = True) -> str | None:
    """Return a direct or presigned download URL for the converted artifact.

    - If presign_expiry_sec > 0, attempt presigned URL with that expiry.
    - Otherwise, build a stable URL using public_endpoint (if set) or endpoint/bucket/object_key.
    """

    if not object_key:
        return None

    base_endpoint = settings.minio.public_endpoint or settings.minio.endpoint
    base_endpoint = str(base_endpoint).rstrip("/")

    expiry = settings.minio.presign_expiry_sec
    if expiry and expiry > 0:
        try:
            client = _get_minio_client(settings, use_cache=use_cache)
            return client.presigned_get_object(settings.minio.bucket, object_key, expires=expiry)
        except Exception:
            # Fallback to static URL if presign fails
            pass

    return f"{base_endpoint}/{settings.minio.bucket}/{object_key}"


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


def _guess_filename(file_meta: Dict[str, Any], input_path: Path | None = None) -> Optional[str]:
    """Best-effort filename for result payloads.

    Priority: explicit filename -> input_path -> object_key basename -> input_url path basename -> None.
    """

    if file_meta.get("filename"):
        return file_meta.get("filename")

    if input_path:
        return Path(input_path).name

    object_key = file_meta.get("object_key")
    if object_key:
        name = Path(object_key).name
        if name:
            return name

    input_url = file_meta.get("input_url")
    if input_url:
        try:
            name = Path(urlparse(input_url).path).name
            if name:
                return name
        except Exception:
            pass

    return None


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

    logger.debug("Starting conversion task %s with %d files", task_id, len(files))   
    logger.debug("Conversion task payload: %s", payload)

    for file_meta in files:
        # 对于空的转换请求，直接跳过 source，但允许 target 为空透传到下游（将得到不支持格式的失败结果）
        def _is_missing(value: Any) -> bool:
            if value is None:
                return True
            if isinstance(value, str):
                normalized = value.strip().lower()
                return normalized == "" or normalized in {"null", "none"}
            return False

        source = file_meta.get("source_format")
        target = file_meta.get("target_format")

        def _norm_fmt(value: Any) -> Any:
            if isinstance(value, str):
                return value.strip().lower()
            return value

        source_norm = _norm_fmt(source)
        target_norm = _norm_fmt(target)
        missing_target = _is_missing(target)

        # 对于空目标格式，视为与 source 相同，走透传上传
        if missing_target:
            target_norm = source_norm

        target_for_lookup = "" if missing_target else target

        if _is_missing(source):
            logger.error("Missing source format for file %s", _source_locator(file_meta))
            record_task_completed("failed")
            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "ignored",
                    "reason": "no source_format provided",
                    "filename": file_meta.get("filename"),
                    "file_meta": file_meta,
                }
            )
            continue

        # Passthrough: same source/target (including empty target treated as source), just upload original as output
        if target_norm and source_norm == target_norm:
            try:
                input_path = _materialize_input(file_meta, task_settings, use_cache=use_cache)
                result_filename = _guess_filename(file_meta, input_path)
                if input_path.is_dir():
                    raise ValueError(f"Input path is a directory: {input_path}")
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Failed to prepare input for passthrough %s -> %s", source, target)
                record_task_completed("failed")
                results.append(
                    {
                        "source": source,
                        "target": target,
                        "status": "failed",
                        "reason": f"Input preparation failed (source={_source_locator(file_meta)}): {exc}",
                        "filename": _guess_filename(file_meta),
                    }
                )
                continue

            output_path = input_path
            output_object = _upload_output(output_path, task_settings, task_id, use_cache=use_cache)
            sitech_input_fileid = file_meta.get("sitech_attach_id") or file_meta.get("sitech_fm_fileid")
            if not sitech_input_fileid:
                sitech_input_fileid = _upload_input_to_sitech(input_path)

            sitech_output_fileid = _upload_output_to_sitech(output_path)
            download_url = _build_download_url(output_object, task_settings, use_cache=use_cache)

            _store_test_artifact(output_path, task_id)

            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "success",
                    "output_path": str(output_path) if output_path else None,
                    "object_key": output_object,
                    "download_url": download_url,
                    "sitech_fm_fileid": sitech_input_fileid,
                    "sitech_fm_output_fileid": sitech_output_fileid,
                    "metadata": {"passthrough": True},
                    "filename": result_filename,
                }
            )
            record_task_completed("success")
            continue

        try:
            plugin = REGISTRY.get(source, target_for_lookup)
        except KeyError as exc:
            # 只有显式目标且非透传时才报不支持；空目标已被透传处理
            if not missing_target and target_norm != source_norm:
                logger.exception("Unsupported format: %s -> %s", source, target)
                record_task_completed("failed")
                results.append(
                    {
                        "source": source,
                        "target": target,
                        "status": "failed",
                        "reason": f"Unsupported format {source}->{target} (source={_source_locator(file_meta)})",
                        "filename": _guess_filename(file_meta),
                    }
                )
                continue
            plugin = None

        try:
            input_path = _materialize_input(file_meta, task_settings, use_cache=use_cache)
            result_filename = _guess_filename(file_meta, input_path)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Failed to prepare input for %s -> %s", source, target)
            record_task_completed("failed")
            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "failed",
                    "reason": f"Input preparation failed (source={_source_locator(file_meta)}): {exc}",
                    "filename": _guess_filename(file_meta),
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

            sitech_input_fileid = file_meta.get("sitech_attach_id") or file_meta.get("sitech_fm_fileid")
            if not sitech_input_fileid:
                sitech_input_fileid = _upload_input_to_sitech(input_path)

            sitech_output_fileid = _upload_output_to_sitech(output_path)
            download_url = _build_download_url(output_object, task_settings, use_cache=use_cache)

            _store_test_artifact(output_path, task_id)

            results.append(
                {
                    "source": source,
                    "target": target,
                    "status": "success",
                    "output_path": str(output_path) if output_path else None,
                    "object_key": output_object,
                    "download_url": download_url,
                    "sitech_fm_fileid": sitech_input_fileid,
                    "sitech_fm_output_fileid": sitech_output_fileid,
                    "metadata": result.metadata,
                    "filename": result_filename,
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
                    "filename": _guess_filename(file_meta),
                }
            )

    return {
        "task_id": task_id,
        "results": results,
    }
