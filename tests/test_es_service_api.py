from __future__ import annotations

import json
from typing import Optional

import pytest
from fastapi.testclient import TestClient

import es_service.api.routes as routes
import es_service.app as app_module
from es_service.app import create_app
from es_service.config import CelerySettings, ESSettings, ServiceSettings


class DummyResult:
    def __init__(self, task_id: str = "task-1"):
        self.id = task_id
        self.state = "PENDING"
        self.result = None


def make_settings(tmp_path):
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(
        json.dumps(
            {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                    "refresh_interval": "5s",
                },
                "mappings": {"properties": {"field": {"type": "keyword"}}},
            }
        ),
        encoding="utf-8",
    )
    return ServiceSettings(
        service_name="es-service",
        api_version="v1-test",
        base_url="",
        host="0.0.0.0",
        port=9000,
        grpc_port=9100,
        celery=CelerySettings(),
        es=ESSettings(mapping_path=mapping_path, default_index="kb_test"),
    )


def build_client(monkeypatch, settings: Optional[ServiceSettings] = None) -> TestClient:
    if settings:
        monkeypatch.setattr(app_module, "get_settings", lambda: settings)
        monkeypatch.setattr(routes, "get_settings", lambda: settings)
    return TestClient(create_app())


def test_health_endpoint_works():
    client = TestClient(create_app())
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "es-service"
    assert data["version"]


def test_render_schema_applies_overrides(tmp_path, monkeypatch):
    settings = make_settings(tmp_path)
    client = build_client(monkeypatch, settings)

    resp = client.post(
        "/schemas/render",
        json={"overrides": {"number_of_shards": 5, "refresh_interval": "1s"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["mapping_applied"] is True
    rendered = body["mapping"]
    assert rendered["settings"]["number_of_shards"] == 5
    assert rendered["settings"]["refresh_interval"] == "1s"
    # unchanged values remain
    assert rendered["settings"]["number_of_replicas"] == 1


def test_create_index_submits_task(monkeypatch):
    captured = {}

    def fake_delay(index_name, overrides):
        captured["args"] = (index_name, overrides)
        return DummyResult("task-create")

    monkeypatch.setattr(routes.create_index_task, "delay", fake_delay)
    client = TestClient(create_app())

    resp = client.post(
        "/indices/create",
        json={"index_name": "kb_custom", "overrides": {"number_of_shards": 2}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["task_id"] == "task-create"
    assert captured["args"] == ("kb_custom", {"number_of_shards": 2})


def test_bulk_and_alias_submissions(monkeypatch):
    captured = {"bulk": None, "alias": None}

    def fake_bulk(index_name, docs, refresh):
        captured["bulk"] = (index_name, docs, refresh)
        return DummyResult("task-bulk")

    def fake_alias(new_index, read_alias, write_alias, old_index):
        captured["alias"] = (new_index, read_alias, write_alias, old_index)
        return DummyResult("task-alias")

    monkeypatch.setattr(routes.bulk_ingest_task, "delay", fake_bulk)
    monkeypatch.setattr(routes.alias_switch_task, "delay", fake_alias)
    client = TestClient(create_app())

    bulk_resp = client.post(
        "/ingest/bulk",
        json={"index_name": "kb_custom", "docs": [{"id": 1}], "refresh": "wait_for"},
    )
    alias_resp = client.post(
        "/indices/alias/switch",
        json={"new_index": "kb_v2", "old_index": "kb_v1", "read_alias": "kb", "write_alias": "kb_w"},
    )

    assert bulk_resp.status_code == 200
    assert alias_resp.status_code == 200
    assert bulk_resp.json()["task_id"] == "task-bulk"
    assert alias_resp.json()["task_id"] == "task-alias"
    assert captured["bulk"] == ("kb_custom", [{"id": 1}], "wait_for")
    assert captured["alias"] == ("kb_v2", "kb", "kb_w", "kb_v1")


def test_task_status_uses_async_result(monkeypatch):
    class FakeAsyncResult:
        def __init__(self, task_id):
            self.id = task_id
            self.state = "SUCCESS"
            self.result = {"ok": True}

    monkeypatch.setattr("celery.result.AsyncResult", FakeAsyncResult)
    client = TestClient(create_app())

    resp = client.get("/tasks/abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "abc123"
    assert data["state"] == "SUCCESS"
    assert data["result"] == {"ok": True}
