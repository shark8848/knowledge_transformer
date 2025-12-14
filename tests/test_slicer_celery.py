"""Celery-orchestrated tests for slicer probe/recommend tasks."""

from __future__ import annotations

import pytest

from slicer_service.celery_app import celery_app


@pytest.fixture(autouse=True)
def _force_eager_tasks():
    # Run Celery tasks inline to avoid external broker dependency in tests.
    celery_app.conf.task_always_eager = True
    celery_app.conf.result_backend = "cache+memory://"
    yield
    celery_app.conf.task_always_eager = False


def test_probe_extract_signals_task():
    samples = ["# Title\nParagraph text with list\n- a\n- b"]
    result = celery_app.tasks["probe.extract_signals"].apply(args=({"samples": samples},)).get()
    assert result["heading_ratio"] > 0
    assert result["list_ratio"] > 0
    assert result["code_ratio"] >= 0


def test_probe_recommend_strategy_task_custom_and_candidates():
    samples = ["a---b---c---d---e---f"]
    payload = {"samples": samples, "custom": {"enable": True, "delimiters": ["---"], "min_segments": 2}, "emit_candidates": True}
    result = celery_app.tasks["probe.recommend_strategy"].apply(args=(payload,)).get()
    assert result["strategy_id"] == "custom_delimiter_split"
    assert result["delimiter_hits"] >= 2
    assert result["candidates"]  # should include candidate scores when emit_candidates is True


def test_probe_recommend_strategy_task_auto_profile():
    samples = ["def foo():\n    pass\nclass Bar:\n    ..."]
    result = celery_app.tasks["probe.recommend_strategy"].apply(args=({"samples": samples},)).get()
    assert result["strategy_id"] in {"code_log_block", "heading_block_length_split", "sentence_split_sliding"}
    assert "params" in result
