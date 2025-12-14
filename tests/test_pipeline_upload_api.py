"""Tests for pipeline upload endpoint using stub MinIO client."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pipeline_service.app import create_app


def test_upload_to_minio(monkeypatch, tmp_path):
    stored = {}

    class _Client:
        def __init__(self):
            self.created = False

        def bucket_exists(self, bucket):
            return False

        def make_bucket(self, bucket):
            self.created = True

        def fput_object(self, bucket, object_key, file_path, content_type=None):
            stored["bucket"] = bucket
            stored["object_key"] = object_key
            stored["content_type"] = content_type
            stored["content"] = Path(file_path).read_bytes()

    monkeypatch.setattr("pipeline_service.app.get_minio_client", lambda: _Client())

    app = create_app()
    client = TestClient(app)

    resp = client.post(
        "/api/v1/pipeline/upload",
        files={"file": ("demo.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert stored["bucket"] == data["bucket"]
    assert data["object_key"].startswith("uploads/")
    assert stored["content"] == b"hello"
