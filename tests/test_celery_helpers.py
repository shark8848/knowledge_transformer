"""Tests for Celery helpers and batch task execution."""

from __future__ import annotations

import base64
from pathlib import Path

import rag_converter.celery_app as worker
from rag_converter.plugins.base import ConversionResult


def test_workspace_file_uses_temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "WORK_DIR", tmp_path)
    generated = worker._workspace_file("example.txt")
    assert generated.parent == tmp_path
    assert generated.name.endswith("_example.txt")


def test_materialize_input_from_local_path(tmp_path, test_settings):
    local_file = tmp_path / "input.bin"
    local_file.write_text("payload", encoding="utf-8")
    result = worker._materialize_input({"local_path": str(local_file)}, test_settings)
    assert result == local_file


def test_materialize_input_downloads_from_object_store(tmp_path, test_settings, monkeypatch):
    downloads: list[tuple[str, str, str]] = []

    class _Client:
        def fget_object(self, bucket, object_key, dest):
            downloads.append((bucket, object_key, dest))
            Path(dest).write_text("data", encoding="utf-8")

    monkeypatch.setattr(worker, "WORK_DIR", tmp_path)
    monkeypatch.setattr(worker, "_get_minio_client", lambda settings: _Client())

    result = worker._materialize_input({"object_key": "foo/bar/baz.txt"}, test_settings)
    assert downloads and downloads[0][1] == "foo/bar/baz.txt"
    assert result.exists()


def test_materialize_input_decodes_base64(tmp_path, test_settings, monkeypatch):
    monkeypatch.setattr(worker, "WORK_DIR", tmp_path)
    content = b"rich text payload"
    b64 = base64.b64encode(content).decode("ascii")

    file_meta = {
        "base64_data": b64,
        "source_format": "text/plain",
        "filename": "note.txt",
    }

    result = worker._materialize_input(file_meta, test_settings)
    assert result.exists()
    assert result.name.endswith("note.txt")
    assert result.read_bytes() == content


def test_upload_output_sends_to_minio(tmp_path, test_settings, monkeypatch):
    uploads: list[tuple[str, str, str]] = []

    class _Client:
        def fput_object(self, bucket, object_key, path):
            uploads.append((bucket, object_key, path))

    monkeypatch.setattr(worker, "_get_minio_client", lambda settings: _Client())
    output_path = tmp_path / "result.txt"
    output_path.write_text("done", encoding="utf-8")

    object_key = worker._upload_output(output_path, test_settings, "task-123")
    assert object_key.startswith("converted/task-123/")
    assert uploads and uploads[0][1] == object_key


def test_handle_conversion_task_success(monkeypatch, tmp_path, test_settings):
    statuses: list[str] = []
    monkeypatch.setattr(worker, "record_task_completed", lambda status: statuses.append(status))
    monkeypatch.setattr(worker, "ensure_metrics_server", lambda port: None)
    monkeypatch.setattr(worker, "_worker_metrics_started", False)
    monkeypatch.setattr(worker, "SETTINGS", test_settings)

    input_file = tmp_path / "input.doc"
    input_file.write_text("data", encoding="utf-8")
    monkeypatch.setattr(worker, "_materialize_input", lambda file_meta, settings, use_cache=True: input_file)

    class _Plugin:
        def convert(self, conv_input):
            assert conv_input.source_format == "doc"
            return ConversionResult(
                output_path=str(tmp_path / "output.docx"),
                object_key="converted/docx",
                metadata={"size": 12},
            )

    class _Registry:
        def __init__(self) -> None:
            self.requested: list[tuple[str, str]] = []

        def get(self, source, target):
            self.requested.append((source, target))
            return _Plugin()

    registry = _Registry()
    monkeypatch.setattr(worker, "REGISTRY", registry)

    payload = {
        "task_id": "task-1",
        "files": [
            {
                "source_format": "doc",
                "target_format": "docx",
                "input_url": "https://example.com/file.doc",
                "size_mb": 1,
            }
        ],
    }

    result = worker.handle_conversion_task.run(payload)
    assert result["task_id"] == "task-1"
    assert result["results"][0]["status"] == "success"
    assert statuses == ["success"]
    assert registry.requested == [("doc", "docx")]


def test_handle_conversion_task_persists_artifacts(monkeypatch, tmp_path, test_settings):
    artifact_dir = tmp_path / "artifacts"
    statuses: list[str] = []

    monkeypatch.setattr(worker, "record_task_completed", lambda status: statuses.append(status))
    monkeypatch.setattr(worker, "ensure_metrics_server", lambda port: None)
    monkeypatch.setattr(worker, "_worker_metrics_started", False)
    monkeypatch.setattr(worker, "SETTINGS", test_settings)
    monkeypatch.setattr(worker, "TEST_ARTIFACTS_DIR", artifact_dir)
    monkeypatch.setattr(worker, "_upload_output", lambda path, settings, task_id: None)

    input_file = tmp_path / "input.doc"
    input_file.write_text("data", encoding="utf-8")
    output_file = tmp_path / "output.docx"
    output_file.write_text("result", encoding="utf-8")
    monkeypatch.setattr(worker, "_materialize_input", lambda file_meta, settings, use_cache=True: input_file)

    class _Plugin:
        def convert(self, conv_input):
            return ConversionResult(output_path=str(output_file))

    class _Registry:
        def get(self, source, target):
            return _Plugin()

    monkeypatch.setattr(worker, "REGISTRY", _Registry())

    payload = {
        "task_id": "task-artifact",
        "files": [
            {
                "source_format": "doc",
                "target_format": "docx",
                "input_url": "https://example.com/doc",
                "size_mb": 1,
            }
        ],
    }

    worker.handle_conversion_task.run(payload)
    copied = artifact_dir / f"task-artifact_{output_file.name}"
    assert copied.exists()
    assert statuses == ["success"]


def test_handle_conversion_task_records_failures(monkeypatch, tmp_path, test_settings):
    statuses: list[str] = []
    monkeypatch.setattr(worker, "record_task_completed", lambda status: statuses.append(status))
    monkeypatch.setattr(worker, "ensure_metrics_server", lambda port: None)
    monkeypatch.setattr(worker, "_worker_metrics_started", False)
    monkeypatch.setattr(worker, "SETTINGS", test_settings)

    class _Plugin:
        def convert(self, conv_input):
            raise RuntimeError("boom")

    class _Registry:
        def get(self, source, target):
            if source == "doc":
                return _Plugin()
            raise KeyError("unsupported")

    monkeypatch.setattr(worker, "REGISTRY", _Registry())
    monkeypatch.setattr(worker, "_materialize_input", lambda file_meta, settings, use_cache=True: tmp_path / "in.doc")

    payload = {
        "task_id": "task-2",
        "files": [
            {"source_format": "doc", "target_format": "docx", "object_key": "doc/1", "size_mb": 1},
            {"source_format": "ppt", "target_format": "pptx", "size_mb": 1},
        ],
    }

    result = worker.handle_conversion_task.run(payload)
    assert result["task_id"] == "task-2"
    statuses.sort()
    assert statuses == ["failed", "failed"]
    assert result["results"][0]["status"] == "failed"
    assert result["results"][1]["status"] == "failed"
    assert "unsupported" in result["results"][1]["reason"]


def test_handle_conversion_task_respects_storage_override(monkeypatch, tmp_path, test_settings):
    calls = []

    class _Client:
        def __init__(self, name: str) -> None:
            self.name = name

        def fget_object(self, bucket, object_key, dest):
            calls.append(("get", self.name, bucket, object_key))
            Path(dest).write_text("input", encoding="utf-8")

        def fput_object(self, bucket, object_key, path):
            calls.append(("put", self.name, bucket, object_key))

    def _fake_get_client(settings, use_cache=True):
        calls.append(
            (
                "client",
                settings.minio.endpoint,
                settings.minio.access_key,
                settings.minio.bucket,
                use_cache,
            )
        )
        return _Client(settings.minio.endpoint)

    class _Plugin:
        def convert(self, conv_input):
            output_file = tmp_path / "out.pdf"
            output_file.write_text("out", encoding="utf-8")
            return ConversionResult(output_path=str(output_file), object_key=None, metadata={})

    class _Registry:
        def get(self, source, target):
            return _Plugin()

    monkeypatch.setattr(worker, "WORK_DIR", tmp_path)
    monkeypatch.setattr(worker, "_get_minio_client", _fake_get_client)
    monkeypatch.setattr(worker, "REGISTRY", _Registry())
    monkeypatch.setattr(worker, "record_task_completed", lambda status: None)
    monkeypatch.setattr(worker, "ensure_metrics_server", lambda port: None)
    monkeypatch.setattr(worker, "_worker_metrics_started", False)
    monkeypatch.setattr(worker, "SETTINGS", test_settings)

    payload = {
        "task_id": "task-storage",
        "storage": {
            "endpoint": "http://custom:9100",
            "access_key": "ak",
            "secret_key": "sk",
            "bucket": "custom-bkt",
        },
        "files": [
            {
                "source_format": "html",
                "target_format": "pdf",
                "object_key": "foo/in.html",
                "size_mb": 1,
            }
        ],
    }

    worker.handle_conversion_task.run(payload)

    assert any(entry[0] == "client" and entry[1] == "http://custom:9100" and entry[2] == "ak" and entry[3] == "custom-bkt" and entry[4] is False for entry in calls)
    assert ("get", "http://custom:9100", "custom-bkt", "foo/in.html") in calls
    assert any(entry[0] == "put" and entry[2] == "custom-bkt" for entry in calls)
