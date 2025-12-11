"""Unit tests for monitoring utilities and dependency checks."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from redis.exceptions import RedisError

from rag_converter.monitoring import (
    collect_dependency_status,
    ensure_metrics_server,
    record_task_accepted,
    record_task_completed,
    _check_celery_workers,
    _check_minio,
    _check_redis,
)


class _CounterStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self.count = 0

    def labels(self, **kwargs):
        self.calls.append(kwargs)
        return self

    def inc(self) -> None:
        self.count += 1


class _GaugeStub:
    def __init__(self) -> None:
        self.values: list[float] = []

    def set(self, value: float) -> None:
        self.values.append(value)


def test_ensure_metrics_server_runs_once(monkeypatch):
    starts: list[int] = []
    monkeypatch.setattr("rag_converter.monitoring._metrics_started", False)
    monkeypatch.setattr("rag_converter.monitoring.start_http_server", lambda port: starts.append(port))

    ensure_metrics_server(9999)
    ensure_metrics_server(9999)

    assert starts == [9999]


def test_record_task_metrics_increment(monkeypatch):
    accepted = _CounterStub()
    completed = _CounterStub()
    monkeypatch.setattr("rag_converter.monitoring.TASKS_ACCEPTED", accepted)
    monkeypatch.setattr("rag_converter.monitoring.TASKS_COMPLETED", completed)

    record_task_accepted("high")
    record_task_completed("success")

    assert accepted.calls == [{"priority": "high"}]
    assert accepted.count == 1
    assert completed.calls == [{"status": "success"}]
    assert completed.count == 1


def test_check_redis_success(monkeypatch, test_settings):
    gauge = _GaugeStub()
    monkeypatch.setattr("rag_converter.monitoring.QUEUE_DEPTH", gauge)

    class _Client:
        def ping(self):
            return True

        def llen(self, _queue):
            return 7

    monkeypatch.setattr(
        "rag_converter.monitoring.redis.Redis.from_url",
        lambda *args, **kwargs: _Client(),
    )

    result = _check_redis(test_settings)
    assert result == "ok"
    assert gauge.values[-1] == 7


def test_check_redis_failure(monkeypatch, test_settings):
    gauge = _GaugeStub()
    monkeypatch.setattr("rag_converter.monitoring.QUEUE_DEPTH", gauge)

    def _raise(*_args, **_kwargs):
        raise RedisError("boom")

    monkeypatch.setattr("rag_converter.monitoring.redis.Redis.from_url", _raise)

    result = _check_redis(test_settings)
    assert result == "error:RedisError"
    assert str(gauge.values[-1]) == "nan"


def test_check_minio_reports_bucket_status(monkeypatch, test_settings):
    class _Minio:
        def __init__(self, *_args, **_kwargs):
            pass

        def bucket_exists(self, bucket):
            return bucket == test_settings.minio.bucket

    monkeypatch.setattr("rag_converter.monitoring.Minio", _Minio)
    assert _check_minio(test_settings) == "ok"


def test_check_celery_workers(monkeypatch):
    gauge = _GaugeStub()
    monkeypatch.setattr("rag_converter.monitoring.CELERY_WORKERS", gauge)

    class _Control:
        def ping(self, timeout=1):
            return ["worker-1", "worker-2"]

    celery_app = SimpleNamespace(control=_Control())
    assert _check_celery_workers(celery_app) == "ok"
    assert gauge.values[-1] == 2


def test_collect_dependency_status_aggregates(monkeypatch, test_settings):
    monkeypatch.setattr("rag_converter.monitoring._check_redis", lambda settings: "redis-ok")
    monkeypatch.setattr("rag_converter.monitoring._check_minio", lambda settings: "minio-ok")
    monkeypatch.setattr(
        "rag_converter.monitoring._check_celery_workers",
        lambda celery: "celery-ok",
    )

    result = collect_dependency_status(test_settings, SimpleNamespace())
    assert result == {"redis": "redis-ok", "minio": "minio-ok", "celery": "celery-ok"}
