"""Tests for FastAPI routes and request validation."""

from __future__ import annotations

from uuid import UUID
from pathlib import Path

import pytest
from celery.exceptions import CeleryError
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from rag_converter.api.routes import (
    REGISTRY,
    _validate_request,
    router,
)
from rag_converter.api.schemas import ConversionFile, ConversionRequest
from rag_converter.config import Settings, settings_dependency
from rag_converter.security import authenticate_request


@pytest.fixture()
def api_app(test_settings: Settings) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[settings_dependency] = lambda: test_settings
    app.dependency_overrides[authenticate_request] = lambda: None
    return app


@pytest.fixture()
def api_client(api_app: FastAPI) -> TestClient:
    return TestClient(api_app)


@pytest.fixture()
def mock_celery(monkeypatch):
    payloads: list[dict] = []

    class _Task:
        def delay(self, payload):
            payloads.append(payload)

    monkeypatch.setattr("rag_converter.api.routes.handle_conversion_task", _Task())
    return payloads


@pytest.fixture()
def fixed_uuid(monkeypatch):
    fake = UUID("12345678-1234-5678-1234-567812345678")
    monkeypatch.setattr("rag_converter.api.routes.uuid4", lambda: fake)
    return str(fake)


def _make_file(**overrides) -> ConversionFile:
    defaults = dict(
        source_format="doc",
        target_format="docx",
        size_mb=10,
        input_url="https://example.com/input.doc",
    )
    defaults.update(overrides)
    return ConversionFile(**defaults)


def _make_request(**overrides) -> ConversionRequest:
    defaults = dict(task_name="demo", files=[_make_file()], priority="normal")
    defaults.update(overrides)
    return ConversionRequest(**defaults)


def test_validate_request_accepts_valid_payload(test_settings):
    payload = _make_request()
    _validate_request(payload, test_settings)


def test_validate_request_rejects_empty_payload(test_settings):
    payload = _make_request(files=[])
    with pytest.raises(HTTPException) as exc:
        _validate_request(payload, test_settings)
    assert exc.value.detail["error_code"] == "ERR_FORMAT_UNSUPPORTED"


def test_validate_request_rejects_large_file(test_settings):
    payload = _make_request(files=[_make_file(size_mb=25)])
    with pytest.raises(HTTPException) as exc:
        _validate_request(payload, test_settings)
    assert exc.value.detail["error_code"] == "ERR_FILE_TOO_LARGE"


def test_validate_request_rejects_batch_limit(test_settings):
    files = [_make_file(size_mb=50), _make_file(size_mb=40, object_key="obj2")]
    payload = _make_request(files=files)
    with pytest.raises(HTTPException) as exc:
        _validate_request(payload, test_settings)
    assert exc.value.detail["error_code"] == "ERR_BATCH_LIMIT_EXCEEDED"


def test_validate_request_rejects_unsupported_format(test_settings):
    files = [
        _make_file(
            source_format="ppt",
            target_format="pptx",
            input_url=None,
            object_key="objects/ppt.ppt",
        )
    ]
    payload = _make_request(files=files)
    with pytest.raises(HTTPException) as exc:
        _validate_request(payload, test_settings)
    assert exc.value.detail["error_code"] == "ERR_FORMAT_UNSUPPORTED"
    assert "source=objects/ppt.ppt" in exc.value.detail["message"]


def test_validate_request_sync_rejects_multiple_files(test_settings):
    files = [_make_file(), _make_file(object_key="obj2.doc")]
    payload = _make_request(files=files, mode="sync")
    with pytest.raises(HTTPException) as exc:
        _validate_request(payload, test_settings)
    assert exc.value.detail["error_code"] == "ERR_BATCH_LIMIT_EXCEEDED"
    assert "sync mode only supports a single file" in exc.value.detail["message"]


def test_submit_conversion_queues_task(api_client, mock_celery, fixed_uuid):
    response = api_client.post(
        "/convert",
        json={
            "task_name": "demo",
            "files": [
                {
                    "source_format": "doc",
                    "target_format": "docx",
                    "size_mb": 10,
                    "input_url": "https://example.com/input.doc",
                }
            ],
        },
    )

    assert response.status_code == 202
    body = response.json()
    assert body["task_id"] == fixed_uuid
    assert mock_celery[0]["task_id"] == fixed_uuid
    assert mock_celery[0]["files"][0]["source_format"] == "doc"


def test_submit_conversion_passes_storage_override(api_client, mock_celery, fixed_uuid):
    payload = {
        "task_name": "demo",
        "storage": {
            "endpoint": "http://override:9000",
            "access_key": "ak",
            "secret_key": "sk",
            "bucket": "custom",
        },
        "files": [
            {
                "source_format": "doc",
                "target_format": "docx",
                "size_mb": 10,
                "input_url": "https://example.com/input.doc",
            }
        ],
    }

    response = api_client.post("/convert", json=payload)

    assert response.status_code == 202
    queued = mock_celery[0]["storage"]
    assert queued == payload["storage"]


def test_submit_conversion_sync_mode_runs_inline(api_client, monkeypatch):
    calls = {}

    def fake_materialize(file_meta, settings, use_cache):
        calls["materialized"] = file_meta
        path = Path("/tmp/input.doc")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    class _Plugin:
        def convert(self, conv_input):
            calls["conversion_input"] = conv_input

            class _Result:
                output_path = None
                object_key = "outputs/demo.docx"
                metadata = {"pages": 1}

            return _Result()

    monkeypatch.setattr("rag_converter.api.routes._materialize_input", fake_materialize)
    monkeypatch.setattr("rag_converter.api.routes.REGISTRY.get", lambda s, t: _Plugin())
    monkeypatch.setattr(
        "rag_converter.api.routes._upload_output",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not upload")),
    )
    monkeypatch.setattr("rag_converter.api.routes._upload_output_to_sitech", lambda path: None)
    monkeypatch.setattr("rag_converter.api.routes._upload_input_to_sitech", lambda path: None)

    response = api_client.post(
        "/convert",
        json={
            "task_name": "demo",
            "mode": "sync",
            "files": [
                {
                    "source_format": "doc",
                    "target_format": "docx",
                    "size_mb": 10,
                    "input_url": "https://example.com/input.doc",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["message"] == "Task completed synchronously"
    assert body["results"][0]["object_key"] == "outputs/demo.docx"
    assert calls["materialized"]["input_url"] == "https://example.com/input.doc"
    assert calls["conversion_input"].source_format == "doc"


def test_submit_conversion_sync_mode_uploads_sitech(api_client, monkeypatch, tmp_path):
    calls = {}
    input_file = tmp_path / "input.doc"
    input_file.write_text("payload", encoding="utf-8")

    def fake_materialize(file_meta, settings, use_cache):
        return input_file

    class _Plugin:
        def convert(self, conv_input):
            calls["conversion_input"] = conv_input

            class _Result:
                output_path = None
                object_key = "outputs/demo.docx"
                metadata = {"pages": 1}

            return _Result()

    monkeypatch.setattr("rag_converter.api.routes._materialize_input", fake_materialize)

    def _fake_sitech_upload(path):
        calls["sitech"] = path
        return "fid-sync"

    monkeypatch.setattr("rag_converter.api.routes._upload_input_to_sitech", _fake_sitech_upload)
    monkeypatch.setattr("rag_converter.api.routes._upload_output", lambda *args, **kwargs: None)
    monkeypatch.setattr("rag_converter.api.routes._upload_output_to_sitech", lambda path: None)
    monkeypatch.setattr("rag_converter.api.routes.REGISTRY.get", lambda s, t: _Plugin())

    response = api_client.post(
        "/convert",
        json={
            "task_name": "demo",
            "mode": "sync",
            "files": [
                {
                    "source_format": "doc",
                    "target_format": "docx",
                    "size_mb": 10,
                    "input_url": "https://example.com/input.doc",
                }
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["results"][0]["sitech_fm_fileid"] == "fid-sync"
    assert calls["sitech"] == input_file


def test_submit_conversion_handles_celery_failure(api_client, monkeypatch):
    class _FailingTask:
        def delay(self, payload):
            raise CeleryError("boom")

    monkeypatch.setattr("rag_converter.api.routes.handle_conversion_task", _FailingTask())
    response = api_client.post(
        "/convert",
        json={
            "task_name": "demo",
            "files": [
                {
                    "source_format": "doc",
                    "target_format": "docx",
                    "size_mb": 10,
                    "input_url": "https://example.com/input.doc",
                }
            ],
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"]["error_code"] == "ERR_TASK_FAILED"


def test_list_formats_uses_registry(api_client, monkeypatch):
    class _Plugin:
        source_format = "wav"
        target_format = "mp3"
        slug = "audio"

    monkeypatch.setattr(REGISTRY, "list", lambda: [_Plugin()])
    response = api_client.get("/formats")
    assert response.status_code == 200
    assert response.json()["formats"] == [
        {"source": "wav", "target": "mp3", "plugin": "audio"}
    ]


def test_list_formats_fallbacks_to_settings(api_client, monkeypatch, test_settings):
    monkeypatch.setattr(REGISTRY, "list", lambda: [])
    response = api_client.get("/formats")
    assert response.status_code == 200
    assert response.json()["formats"] == [
        {
            "source": test_settings.convert_formats[0].source,
            "target": test_settings.convert_formats[0].target,
            "plugin": test_settings.convert_formats[0].plugin,
        }
    ]


def test_health_check_returns_dependency_status(api_client, monkeypatch):
    monkeypatch.setattr(
        "rag_converter.api.routes.collect_dependency_status",
        lambda settings, celery_app: {"redis": "ok", "minio": "ok"},
    )
    response = api_client.get("/monitor/health")
    assert response.status_code == 200
    assert response.json()["dependencies"] == {"redis": "ok", "minio": "ok"}
