"""Celery tasks that orchestrate conversion and slicing recommendations."""

from __future__ import annotations

import logging
import random
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from celery import chain
from pypdf import PdfReader, PdfWriter

from .celery_app import pipeline_celery
from .config import get_settings
from .minio_client import get_minio_client
from .utils import is_markdown_target, normalize_source_format, normalize_target_format, prefer_markdown_target

settings = get_settings()
logger = logging.getLogger(__name__)


def _round_value(val: Any, places: int = 3) -> Any:
    if not isinstance(val, (int, float)):
        return val
    return float(f"{float(val):.{places}f}")


def _round_profile(profile: Dict[str, Any], places: int = 3) -> Dict[str, Any]:
    return {k: _round_value(v, places) for k, v in profile.items()}


def _round_scores(scores: Dict[str, Any] | None, places: int = 3) -> Dict[str, Any] | None:
    if scores is None:
        return None
    return {k: _round_value(v, places) for k, v in scores.items()}


def _first_success(results: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    for item in results:
        if item.get("status") == "success" and (item.get("object_key") or item.get("output_path")):
            return item
    return None


def _download_to_temp(object_key: str) -> Path:
    client = get_minio_client()
    tmp = Path(tempfile.mkstemp(suffix=Path(object_key).suffix)[1])
    client.fget_object(settings.minio_bucket, object_key, str(tmp))
    return tmp


def _extract_pdf_text(pdf_path: Path, max_pages_hint: int) -> tuple[List[str], List[int]]:
    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)

    if total_pages <= 0:
        return [], []

    # 按页数比例抽样：确保至少1页，比例抽样后上限10页；若 max_pages_hint 更小则使用提示值作为下限限制。
    ratio_count = int(max(1, round(total_pages * settings.sample_page_ratio)))
    limit = min(10, max(ratio_count, min(max_pages_hint, total_pages)))

    if limit >= total_pages:
        selected = list(range(total_pages))
    else:
        # 从中间出发随机左右扩散，保证覆盖文档不同区域。
        mid = total_pages // 2
        selected_set = {mid}
        left_cursor = mid
        right_cursor = mid
        max_step = max(1, min(3, total_pages))
        while len(selected_set) < limit and (left_cursor > 0 or right_cursor < total_pages - 1):
            choices = []
            if left_cursor > 0:
                choices.append("left")
            if right_cursor < total_pages - 1:
                choices.append("right")
            if not choices:
                break
            direction = random.choice(choices)
            step = random.randint(1, max_step)
            if direction == "left" and left_cursor > 0:
                left_cursor = max(0, left_cursor - step)
                selected_set.add(left_cursor)
            elif direction == "right" and right_cursor < total_pages - 1:
                right_cursor = min(total_pages - 1, right_cursor + step)
                selected_set.add(right_cursor)
        selected = sorted(selected_set)

    texts: List[str] = []
    for idx in selected:
        texts.append(reader.pages[idx].extract_text() or "")

    if settings.sample_char_limit and settings.sample_char_limit > 0:
        total_chars = sum(len(t) for t in texts)
        if total_chars > settings.sample_char_limit:
            capped_texts: List[str] = []
            remaining = settings.sample_char_limit
            for t in texts:
                if remaining <= 0:
                    break
                capped_piece = t[:remaining]
                capped_texts.append(capped_piece)
                remaining -= len(capped_piece)
            texts = capped_texts

    logger.info(
        "probe.page_sampling total=%s limit=%s pages=%s",
        total_pages,
        limit,
        selected,
    )

    # 备用：若后续需按字符抽样，可在此处截断总字符数；当前按页返回全部文本。
    return texts, selected


def _extract_markdown(md_path: Path) -> tuple[List[str], List[int]]:
    content = md_path.read_text(encoding="utf-8", errors="ignore")
    if not content:
        return [""], [0]

    trimmed = content
    if settings.sample_char_limit and settings.sample_char_limit > 0 and len(trimmed) > settings.sample_char_limit:
        trimmed = trimmed[: settings.sample_char_limit]

    paragraphs = [para.strip() for para in trimmed.split("\n\n") if para.strip()]
    if not paragraphs:
        paragraphs = [trimmed.strip()]

    max_segments = max(1, min(settings.sample_pages, len(paragraphs)))
    selected_indices = list(range(max_segments))
    samples = paragraphs[:max_segments]

    logger.info(
        "probe.markdown_sampling segments=%s len=%s",
        selected_indices,
        sum(len(s) for s in samples),
    )

    return samples, selected_indices


@pipeline_celery.task(name="pipeline.extract_and_probe")
def extract_and_probe(conversion_result: Dict[str, Any]) -> Dict[str, Any]:
    """Take conversion result -> pull first pages text -> run probe tasks."""

    results = conversion_result.get("results") or []
    picked = _first_success(results)
    artifact_path: Path | None = None
    source_format = None
    target_format = None
    samples: List[str] = []
    selected_pages: List[int] = []

    if picked:
        if picked.get("output_path"):
            candidate = Path(str(picked["output_path"]))
            if candidate.exists():
                artifact_path = candidate
        if not artifact_path:
            if not picked.get("object_key"):
                raise RuntimeError("Missing object_key for converted artifact")
            artifact_path = _download_to_temp(picked["object_key"])

        source_format = normalize_source_format(picked.get("source")) if picked.get("source") else None
        target_format = normalize_target_format(picked.get("target") or artifact_path.suffix.lstrip("."))
        if is_markdown_target(target_format) or artifact_path.suffix.lower() == ".md":
            samples, selected_pages = _extract_markdown(artifact_path)
        else:
            samples, selected_pages = _extract_pdf_text(artifact_path, settings.sample_pages)
    else:
        if pipeline_celery.conf.task_always_eager:
            # In eager/test mode, fabricate a minimal PDF so downstream probe tasks can run without external storage.
            tmp_pdf = Path(tempfile.mkstemp(suffix=".pdf")[1])
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            with tmp_pdf.open("wb") as f:
                writer.write(f)
            artifact_path = tmp_pdf
            target_format = "pdf"
            samples, selected_pages = _extract_pdf_text(artifact_path, settings.sample_pages)
        else:
            raise RuntimeError("No successful conversion result with object_key/output_path")
    combined_text = "\n".join(samples)
    logger.info(
        "probe.extract_and_probe.samples_ready pages=%s len=%s",
        selected_pages,
        len(combined_text),
        extra={
            "sample_pages": settings.sample_pages,
            "artifact_path": str(artifact_path),
            "target_format": target_format,
            "sample_length": len(combined_text),
            "sample_preview": combined_text[:500],
            "selected_pages": selected_pages,
        },
    )

    # Dispatch probe tasks to the dedicated slicer worker queue; in eager mode, run inline to avoid Celery send_task ignoring task_always_eager.
    def _probe(task_name: str, args: tuple[Any, ...]) -> Any:
        if pipeline_celery.conf.task_always_eager:
            return pipeline_celery.tasks[task_name].apply(args=args).get()
        async_result = pipeline_celery.send_task(task_name, args=args, queue=settings.probe_queue)
        return async_result.get(timeout=settings.probe_timeout_sec, disable_sync_subtasks=False)

    profile_result = _probe("probe.extract_signals", ({"samples": samples},))
    profile_result = _round_profile(profile_result, 3)

    recommend_result = _probe(
        "probe.recommend_strategy",
        ({
            "profile": profile_result,
            "samples": samples,
            "emit_candidates": True,
            "source_format": source_format,
        },),
    )

    # Ensure downstream consumers always see at most 3 decimal places.
    if isinstance(recommend_result, dict):
        if "profile" in recommend_result and isinstance(recommend_result["profile"], dict):
            recommend_result["profile"] = _round_profile(recommend_result["profile"], 3)
        if "candidates" in recommend_result:
            recommend_result["candidates"] = _round_scores(recommend_result.get("candidates"), 3)

    recommendation = recommend_result

    logger.info(
        "probe.recommendation strategy=%s candidates=%s",
        recommendation.get("strategy_id") if isinstance(recommendation, dict) else None,
        recommendation.get("candidates") if isinstance(recommendation, dict) else None,
        extra={
            "strategy_id": recommendation.get("strategy_id") if isinstance(recommendation, dict) else None,
            "candidates": recommendation.get("candidates") if isinstance(recommendation, dict) else None,
        },
    )

    return {
        "conversion": conversion_result,
        "profile": profile_result,
        "recommendation": recommendation,
    }


@pipeline_celery.task(name="pipeline.run_document_pipeline")
def run_document_pipeline(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run full pipeline: conversion.handle_batch -> extract_and_probe."""

    conv_payload = dict(payload)
    for f in conv_payload.get("files", []):
        f["source_format"] = normalize_source_format(f.get("source_format"))
        f["target_format"] = prefer_markdown_target(f["source_format"], f.get("target_format"))
        f.setdefault("page_limit", settings.sample_pages)

    all_pdf_passthrough = all(
        (f.get("source_format") or "").lower() in {"pdf"}
        and (f.get("target_format") or "pdf").lower() == "pdf"
        and f.get("object_key")
        for f in conv_payload.get("files", [])
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
                for f in conv_payload.get("files", [])
            ],
        }
        async_result = pipeline_celery.signature(
            "pipeline.extract_and_probe", args=[stub_result], queue=settings.pipeline_queue
        ).apply_async()
        return async_result.get(timeout=settings.probe_timeout_sec)

    if pipeline_celery.conf.task_always_eager:
        conv_result = pipeline_celery.tasks["conversion.handle_batch"].apply(args=(conv_payload,)).get()
        return pipeline_celery.tasks["pipeline.extract_and_probe"].apply(args=(conv_result,)).get()

    workflow = chain(
        pipeline_celery.signature(
            "conversion.handle_batch", args=[conv_payload], immutable=True, queue=settings.conversion_queue
        ),
        pipeline_celery.signature("pipeline.extract_and_probe", queue=settings.pipeline_queue),
    )
    async_result = workflow.apply_async()
    return async_result.get(timeout=settings.conversion_timeout_sec + settings.probe_timeout_sec)
