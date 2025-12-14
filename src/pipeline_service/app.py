"""FastAPI entry exposing pipeline orchestration as an API."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel, Field

from .celery_app import pipeline_celery
from .config import get_settings
from .minio_client import get_minio_client
from .utils import normalize_source_format, prefer_markdown_target


class FilePayload(BaseModel):
    source_format: str
    target_format: Optional[str] = Field(default="pdf")
    input_url: Optional[str] = None
    object_key: Optional[str] = None
    base64_data: Optional[str] = None
    filename: Optional[str] = None
    size_mb: Optional[float] = None
    page_limit: Optional[int] = None
    duration_seconds: Optional[int] = None


class PipelineRequest(BaseModel):
    files: List[FilePayload]
    priority: str = "normal"
    callback_url: Optional[str] = None
    storage: Optional[Dict[str, Any]] = None
    async_mode: bool = False


class PipelineResponse(BaseModel):
    task_id: str
    status: str = "accepted"
    result: Optional[Dict[str, Any]] = None


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.api_title, version=settings.api_version)

    @app.post("/api/v1/pipeline/upload")
    async def upload_to_minio(file: UploadFile = File(...)):
        if not file.filename:
            raise HTTPException(status_code=400, detail="filename is required")

        client = get_minio_client()
        bucket = settings.minio_bucket
        try:
            if not client.bucket_exists(bucket):
                client.make_bucket(bucket)
        except Exception as exc:  # noqa: BLE001
            if "already exists" not in str(exc):
                raise HTTPException(status_code=500, detail=f"bucket check failed: {exc}")

        safe_name = Path(file.filename).name or "upload.bin"
        object_key = f"uploads/{uuid4().hex}_{safe_name}"

        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            client.fput_object(
                bucket,
                object_key,
                str(tmp_path),
                content_type=file.content_type or "application/octet-stream",
            )
        except Exception as exc:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail=f"upload failed: {exc}")
        finally:
            tmp_path.unlink(missing_ok=True)

        return {"bucket": bucket, "object_key": object_key}

    @app.post("/api/v1/pipeline/recommend", response_model=PipelineResponse)
    def recommend(req: PipelineRequest):
        if not req.files:
            raise HTTPException(status_code=400, detail="files is required")

        payload = req.model_dump()
        # enforce pdf/page_limit defaults
        for f in payload["files"]:
            f["source_format"] = normalize_source_format(f.get("source_format"))
            f["target_format"] = prefer_markdown_target(f["source_format"], f.get("target_format"))
            f.setdefault("page_limit", settings.sample_pages)

        all_pdf_passthrough = all(
            (f.get("source_format") or "").lower() in {"pdf", "application/pdf"}
            and (f.get("target_format") or "pdf").lower() == "pdf"
            and f.get("object_key")
            for f in payload["files"]
        )

        if all_pdf_passthrough:
            stub_result = {
                "task_id": None,
                "results": [
                    {
                        "source": f.get("source_format"),
                        "target": f.get("target_format"),
                        "status": "success",
                        "object_key": f.get("object_key"),
                        "output_path": None,
                        "metadata": {"note": "passthrough pdf"},
                    }
                    for f in payload["files"]
                ],
            }
            async_result = pipeline_celery.signature(
                "pipeline.extract_and_probe", args=[stub_result], queue=settings.pipeline_queue
            ).apply_async()
        else:
            workflow = pipeline_celery.signature(
                "conversion.handle_batch", args=[payload], immutable=True, queue=settings.conversion_queue
            ) | pipeline_celery.signature("pipeline.extract_and_probe", queue=settings.pipeline_queue)
            async_result = workflow.apply_async()

        if req.async_mode:
            return PipelineResponse(task_id=async_result.id)

        try:
            result = async_result.get(timeout=settings.conversion_timeout_sec + settings.probe_timeout_sec)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        return PipelineResponse(task_id=async_result.id, status="success", result=result)

    return app


app = create_app()
