"""Celery tasks for metadata extraction from mm-schema documents."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import requests
from jinja2 import Template

from .celery_app import meta_celery
from .config import get_settings
from .storage import download_object, upload_file

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """
你是文档元数据抽取助手。请仅输出 JSON，对键 summary(中文摘要), tags(字符串列表), keywords(字符串列表), questions(字符串列表) 给出内容，禁止输出解释或额外文本。
"""


def _get_api_key() -> str:
    api_key = settings.bailian.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("META_bailian__api_key is required")
    return api_key


def _normalize_endpoint() -> str:
    base = settings.bailian.api_base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _load_manifest(request: Dict[str, Any], workdir: Path) -> Path:
    dest = workdir / "mm-schema.json"
    if obj := request.get("manifest_object_key"):
        download_object(obj, dest)
        return dest
    if url := request.get("manifest_url") or request.get("input_url"):
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    raise ValueError("manifest_object_key or manifest_url is required")


def _render_prompt(chunk: Dict[str, Any], doc_meta: Dict[str, Any]) -> str:
    template = Template(settings.processing.prompt_template)
    keyframes = chunk.get("keyframes") or []
    text_content = ((chunk.get("content") or {}).get("text") or {}).get("full_text") or ""
    return template.render(
        summary_words=settings.processing.summary_words,
        title=(doc_meta.get("title") or doc_meta.get("file_name") or "未知文档"),
        start=(chunk.get("temporal") or {}).get("start_time"),
        end=(chunk.get("temporal") or {}).get("end_time"),
        text=text_content,
        keyframes=keyframes,
    )


def _parse_llm_content(raw: str) -> Dict[str, Any]:
    try:
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {
            "summary": raw.strip(),
            "tags": [],
            "keywords": [],
            "questions": [],
        }


def _normalize_text_fields(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure content.text has full_text and segments backfilled."""
    content = chunk.setdefault("content", {})
    text = content.setdefault("text", {})
    full_text = text.get("full_text") or ""
    segments = text.get("segments") or []

    # Fallback: use keyframe descriptions when no ASR text is present
    if not full_text and not segments:
        kf_desc = []
        for kf in chunk.get("keyframes") or []:
            desc = (kf or {}).get("description") or ""
            if desc:
                kf_desc.append(desc)
        if kf_desc:
            full_text = " ".join(kf_desc).strip()
            text["full_text"] = full_text

    if not full_text and segments:
        # Concatenate segment text to rebuild full_text
        full_text = "".join(seg.get("text") or "" for seg in segments).strip()
        if full_text:
            text["full_text"] = full_text

    if full_text and not segments:
        # Build a single segment covering the chunk time span
        temporal = chunk.get("temporal") or {}
        text["segments"] = [
            {
                "index": 0,
                "start_time": temporal.get("start_time"),
                "end_time": temporal.get("end_time"),
                "text": full_text,
            }
        ]

    return text


def _aggregate_doc_metadata(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Roll up chunk-level extraction into document-level metadata."""
    extras: List[Dict[str, Any]] = []
    for chunk in manifest.get("chunks") or []:
        meta = (chunk.get("metadata") or {}).get("extraction")
        if meta:
            extras.append(meta)

    def _dedup_list(key: str) -> List[str]:
        seen = []
        for item in extras:
            for val in item.get(key) or []:
                if val not in seen:
                    seen.append(val)
        return seen

    summaries = [e.get("summary") for e in extras if e.get("summary")]
    doc_meta = manifest.setdefault("document_metadata", {})
    doc_meta["extraction"] = {
        "summary": "\n".join(summaries) if summaries else None,
        "tags": _dedup_list("tags"),
        "keywords": _dedup_list("keywords"),
        "questions": _dedup_list("questions"),
        "chunks_with_extraction": len(extras),
    }
    return doc_meta


def _call_llm(prompt: str) -> Dict[str, Any]:
    api_key = _get_api_key()
    endpoint = _normalize_endpoint()
    payload = {
        "model": settings.bailian.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT.strip()},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(endpoint, json=payload, timeout=settings.bailian.request_timeout_sec, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        raise ValueError(f"LLM response missing choices: {data}")
    content = choices[0].get("message", {}).get("content") or ""
    return _parse_llm_content(content)


def _enrich_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    doc_meta = (manifest.get("document_metadata") or {}).get("source_info") or {}
    total = len(manifest.get("chunks") or [])
    max_chunks = settings.processing.max_chunks or total
    for idx, chunk in enumerate(manifest.get("chunks") or []):
        if idx >= max_chunks:
            logger.info("Skip chunk %s beyond max_chunks=%s", idx, max_chunks)
            break
        _normalize_text_fields(chunk)
        prompt = _render_prompt(chunk, doc_meta)
        try:
            extracted = _call_llm(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM extraction failed for chunk %s: %s", chunk.get("chunk_id") or idx, exc)
            continue
        chunk.setdefault("metadata", {})["extraction"] = extracted
    _aggregate_doc_metadata(manifest)
    manifest.setdefault("processing", {})["metadata_extraction"] = {
        "status": "success",
        "processed_chunks": min(total, max_chunks),
    }
    return manifest


@meta_celery.task(name="meta.process")
def process_manifest(request: Dict[str, Any]) -> Dict[str, Any]:
    task_id = request.get("task_id") or uuid4().hex
    workdir = Path(tempfile.mkdtemp(prefix="meta-"))
    try:
        manifest_path = _load_manifest(request, workdir)
        manifest_obj = json.loads(manifest_path.read_text(encoding="utf-8"))
        enriched = _enrich_manifest(manifest_obj)

        # derive output object key
        output_key = request.get("output_object_key")
        if not output_key:
            if obj := request.get("manifest_object_key"):
                path = Path(obj)
                output_key = str(path.with_name("mm-schema.meta.json"))
            else:
                output_key = f"meta/{task_id}/mm-schema.meta.json"

        out_path = workdir / "mm-schema.meta.json"
        out_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")
        stored = upload_file(out_path, output_key)
        return {"task_id": task_id, "output": stored}
    finally:
        try:
            # Cleanup temp directory
            for item in workdir.glob("*"):
                if item.is_file():
                    item.unlink(missing_ok=True)
            workdir.rmdir()
        except Exception:  # noqa: BLE001
            pass


@meta_celery.task(name="meta.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    async_result = process_manifest.apply_async(args=[request])
    return {"task_id": async_result.id}
