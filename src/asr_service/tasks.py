"""Celery tasks for Whisper-based ASR."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlparse

import requests
from celery import chain

from .celery_app import asr_celery
from .config import get_settings
from .errors import raise_error

logger = logging.getLogger(__name__)
settings = get_settings()


@lru_cache(maxsize=2)
def _load_model(model_name: str, device: str):
    try:
        import whisper
    except ImportError as exc:  # noqa: BLE001
        raise RuntimeError("Missing dependency 'openai-whisper'. Install it to run ASR tasks.") from exc
    logger.info("Loading Whisper model '%s' on %s", model_name, device)
    return whisper.load_model(model_name, device=device)


def _download_audio(source: Dict[str, Any]) -> str:
    url = source.get("input_url")
    if not url:
        raise_error("ERR_BAD_REQUEST", detail="input_url required for ASR")

    tmp_dir = Path(settings.processing.tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix or ".wav"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=tmp_dir) as handle:
        with requests.get(url, stream=True, timeout=settings.processing.download_timeout_sec) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    handle.write(chunk)
        return handle.name


def _merge_options(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = payload.get("source") or {}
    options = payload.get("options") or {}
    return {
        "model_name": options.get("model_name") or settings.processing.model_name,
        "task": options.get("task") or settings.processing.task,
        "language": options.get("language") or source.get("language") or settings.processing.language,
        "temperature": options.get("temperature", settings.processing.temperature),
        "beam_size": options.get("beam_size") or settings.processing.beam_size,
        "initial_prompt": options.get("initial_prompt") or settings.processing.initial_prompt,
    }


@asr_celery.task(name="asr.prepare")
def prepare_audio(request: Dict[str, Any]) -> Dict[str, Any]:
    source = request.get("source") or {}
    audio_path = _download_audio(source)
    return {"audio_path": audio_path, "source": source, "options": request.get("options") or {}}


@asr_celery.task(name="asr.transcribe")
def transcribe_audio(prepared: Dict[str, Any]) -> Dict[str, Any]:
    audio_path = prepared.get("audio_path")
    if not audio_path:
        raise_error("ERR_BAD_REQUEST", detail="audio_path missing for transcription")

    opts = _merge_options(prepared)
    model = _load_model(opts["model_name"], settings.processing.device)

    try:
        result = model.transcribe(
            audio_path,
            language=opts["language"],
            task=opts["task"],
            temperature=opts["temperature"],
            beam_size=opts["beam_size"],
            initial_prompt=opts["initial_prompt"],
        )
    finally:
        with contextlib.suppress(OSError):
            os.remove(audio_path)

    segments_raw: List[Dict[str, Any]] = result.get("segments") or []
    segments = [
        {
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": seg.get("text", ""),
        }
        for seg in segments_raw
    ]

    return {
        "text": result.get("text") or "",
        "language": result.get("language") or opts["language"],
        "duration": result.get("duration"),
        "segments": segments,
        "metadata": {"model_name": opts["model_name"], "task": opts["task"]},
    }


@asr_celery.task(name="asr.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    workflow = chain(
        prepare_audio.s(request),
        transcribe_audio.s(),
    )
    async_result = workflow.apply_async()
    return {"task_id": async_result.id}
