"""Eager-mode tests for pipeline orchestration without real services."""

from __future__ import annotations

from pathlib import Path

import pytest
from pypdf import PdfWriter

from pipeline_service.celery_app import pipeline_celery
from pipeline_service.tasks import extract_and_probe, run_document_pipeline


@pytest.fixture(autouse=True)
def _eager_mode():
    pipeline_celery.conf.task_always_eager = True
    pipeline_celery.conf.result_backend = "cache+memory://"
    yield
    pipeline_celery.conf.task_always_eager = False


@pytest.fixture()
def fake_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "sample.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    # add simple text annotation as proxy text
    writer.add_outline_item("Title", writer.pages[0])
    with pdf.open("wb") as f:
        writer.write(f)
    return pdf


@pytest.fixture(autouse=True)
def _register_stub_tasks(fake_pdf: Path):
    # stub conversion task
    @pipeline_celery.task(name="conversion.handle_batch")
    def _fake_conversion(payload):  # type: ignore
        return {
            "task_id": "conv-1",
            "results": [
                {
                    "source": "doc",
                    "target": "pdf",
                    "status": "success",
                    "output_path": str(fake_pdf),
                    "object_key": None,
                }
            ],
        }

    @pipeline_celery.task(name="probe.extract_signals")
    def _fake_extract(payload):  # type: ignore
        return {"heading_ratio": 0.1, "list_ratio": 0.0, "code_ratio": 0.0, "samples": payload.get("samples")}

    @pipeline_celery.task(name="probe.recommend_strategy")
    def _fake_recommend(payload):  # type: ignore
        return {"strategy_id": "sentence_split_sliding", "delimiter_hits": 0, "params": {}}

    yield


def test_extract_and_probe_uses_conversion_result():
    conv_result = pipeline_celery.tasks["conversion.handle_batch"].apply(args=({"files": []},)).get()
    result = extract_and_probe.apply(args=(conv_result,)).get()
    assert result["recommendation"]["strategy_id"] == "sentence_split_sliding"
    assert result["profile"]["heading_ratio"] >= 0


def test_run_document_pipeline_chain():
    payload = {"files": [{"source_format": "doc", "target_format": "pdf", "object_key": "ignored"}]}
    result = run_document_pipeline.apply(args=(payload,)).get()
    assert result["recommendation"]["strategy_id"] == "sentence_split_sliding"
    assert "conversion" in result
