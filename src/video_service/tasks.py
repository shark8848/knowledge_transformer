"""Video processing Celery tasks that produce mm-schema outputs and upload to MinIO."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple
from uuid import uuid4

import requests
from celery.result import AsyncResult

from asr_service.celery_app import asr_celery
from multimodal_service.celery_app import mm_celery

from .celery_app import video_celery
from .config import get_settings
from .storage import download_object, ensure_bucket, upload_file
logger = logging.getLogger(__name__)
settings = get_settings()


def _require_bin(binary: str) -> None:
    if shutil.which(binary) is None:
        raise RuntimeError(f"Required binary not found: {binary}")


def _run(cmd: List[str]) -> None:
    logger.debug("Running command: %s", " ".join(cmd))
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def _post_json(url: str, payload: Dict[str, Any], timeout: int = 120) -> Dict[str, Any]:
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _fixed_segments(duration: float, win: float) -> List[Tuple[float, float]]:
    if duration <= 0 or win <= 0:
        return []
    segments: List[Tuple[float, float]] = []
    cursor = 0.0
    while cursor < duration:
        end = min(duration, cursor + win)
        segments.append((cursor, end))
        if end == duration:
            break
        cursor = end
    return segments


def _scene_segments(video_path: Path, threshold: float, min_duration: float, total_duration: float) -> List[Tuple[float, float]]:
    """Detect scene boundaries via ffprobe scene score and return merged segments."""

    _require_bin("ffprobe")
    filter_expr = f"movie={video_path},select=gt(scene\\,{threshold})"
    cmd = [
        "ffprobe",
        "-hide_banner",
        "-show_frames",
        "-of",
        "json",
        "-f",
        "lavfi",
        filter_expr,
    ]
    try:
        proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        data = json.loads(proc.stdout or "{}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scene detection failed, fallback to fixed segments: %s", exc)
        return []

    frames = data.get("frames") or []
    cuts: List[float] = []
    for frame in frames:
        ts = frame.get("pkt_pts_time")
        try:
            if ts is not None:
                cuts.append(float(ts))
        except Exception:  # noqa: BLE001
            continue

    cuts = sorted({c for c in cuts if 0.0 < c < total_duration})
    if not cuts:
        return []

    boundaries = [0.0] + cuts + [total_duration]
    segments: List[Tuple[float, float]] = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        if end > start:
            segments.append((start, end))

    # merge segments shorter than min_duration with the previous one
    merged: List[Tuple[float, float]] = []
    for seg in segments:
        if not merged:
            merged.append(seg)
            continue
        prev_start, prev_end = merged[-1]
        if (seg[1] - seg[0]) < min_duration:
            merged[-1] = (prev_start, seg[1])
        else:
            merged.append(seg)

    # ensure last segment reaches total_duration
    if merged:
        last_start, last_end = merged[-1]
        if last_end < total_duration:
            merged[-1] = (last_start, total_duration)

    return merged


def _probe_duration(path: Path) -> float:
    _require_bin("ffprobe")
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=nk=1:nw=1",
        str(path),
    ]
    proc = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        return float(proc.stdout.strip())
    except Exception:  # noqa: BLE001
        return 0.0


def _materialize_media(request: Dict[str, Any], workdir: Path) -> Path:
    ensure_bucket()
    if object_key := request.get("object_key"):
        dest = workdir / Path(object_key).name
        return download_object(object_key, dest)
    if input_url := request.get("input_url"):
        dest = workdir / (Path(input_url).name or "input.mp4")
        resp = requests.get(input_url, timeout=60)
        resp.raise_for_status()
        dest.write_bytes(resp.content)
        return dest
    raise ValueError("input_url or object_key required")


def _extract_audio(video_path: Path, workdir: Path) -> Path:
    _require_bin("ffmpeg")
    out_path = workdir / "audio_full.m4a"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-acodec",
        "aac",
        str(out_path),
    ]
    _run(cmd)
    return out_path


def _call_asr_task(audio_url: str) -> Dict[str, Any]:
    try:
        async_res = asr_celery.send_task(
            "asr.orchestrate",
            args=[{"source": {"input_url": audio_url}}],
            queue=settings.celery.asr_queue,
        )
        result = async_res.get(timeout=300, disable_sync_subtasks=False)
        if isinstance(result, dict) and "task_id" in result and len(result) == 1:
            inner = AsyncResult(result["task_id"], app=asr_celery)
            result = inner.get(timeout=300)
        return result if isinstance(result, dict) else {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("ASR task failed: %s", exc)
        return {}


def _caption_frame(frame_url: str, prompt: str) -> str:
    try:
        async_res = mm_celery.send_task(
            "mm.call",
            args=[{"source": {"input_url": frame_url, "kind": "image", "prompt": prompt}}],
            queue=settings.celery.vision_queue,
        )
        result = async_res.get(timeout=180, disable_sync_subtasks=False)
        if isinstance(result, dict):
            return (result.get("text") or "")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Frame caption failed: %s", exc)
    return ""


def _caption_frames_async(frames: List[Dict[str, Any]], prompt: str, timeout: int = 180) -> Dict[float, str]:
    """Fire off caption tasks for all frames and then collect results in parallel."""

    pending: Dict[float, Tuple[Any, Dict[str, Any]]] = {}
    for f in frames:
        url = f.get("url")
        ts = f.get("timestamp")
        if not url or ts is None:
            continue
        try:
            async_res = mm_celery.send_task(
                "mm.call",
                args=[{"source": {"input_url": url, "kind": "image", "prompt": prompt}}],
                queue=settings.celery.vision_queue,
            )
            pending[float(ts)] = (async_res, f)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Frame caption dispatch failed (ts=%s): %s", ts, exc)

    captions: Dict[float, str] = {}
    for ts in sorted(pending):
        async_res, f = pending[ts]
        try:
            result = async_res.get(timeout=timeout, disable_sync_subtasks=False)
            if isinstance(result, dict):
                desc = result.get("text") or ""
                if desc:
                    f["description"] = desc
                    captions[ts] = desc
        except Exception as exc:  # noqa: BLE001
            logger.warning("Frame caption collect failed (ts=%s): %s", ts, exc)
    return captions


def _slice_video(video_path: Path, segments: List[Tuple[float, float]], base_prefix: str, workdir: Path) -> List[Dict[str, Any]]:
    _require_bin("ffmpeg")
    results: List[Dict[str, Any]] = []
    for idx, (start, end) in enumerate(segments):
        duration = max(0.0, end - start)
        out_path = workdir / f"video_seg_{idx:04d}.mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start}",
            "-i",
            str(video_path),
            "-t",
            f"{duration}",
            "-c",
            "copy",
            str(out_path),
        ]
        _run(cmd)
        obj_key = f"{base_prefix}/video/slices/seg_{idx:04d}.mp4"
        upload = upload_file(out_path, obj_key)
        results.append({"start": start, "end": end, "duration": duration, **upload})
    return results


def _slice_audio(audio_path: Path, segments: List[Tuple[float, float]], base_prefix: str, workdir: Path) -> List[Dict[str, Any]]:
    _require_bin("ffmpeg")
    results: List[Dict[str, Any]] = []
    for idx, (start, end) in enumerate(segments):
        duration = max(0.0, end - start)
        out_path = workdir / f"audio_seg_{idx:04d}.m4a"
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start}",
            "-i",
            str(audio_path),
            "-t",
            f"{duration}",
            "-c",
            "copy",
            str(out_path),
        ]
        _run(cmd)
        obj_key = f"{base_prefix}/audio/slices/seg_{idx:04d}.m4a"
        upload = upload_file(out_path, obj_key)
        results.append({"start": start, "end": end, "duration": duration, **upload})
    return results


def _extract_frames(video_path: Path, fps: float, base_prefix: str, workdir: Path) -> List[Dict[str, Any]]:
    if fps <= 0:
        return []
    _require_bin("ffmpeg")
    frame_dir = workdir / "frames"
    frame_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"fps={fps}",
        str(frame_dir / "frame_%06d.jpg"),
    ]
    _run(cmd)

    frames: List[Dict[str, Any]] = []
    for idx, path in enumerate(sorted(frame_dir.glob("frame_*.jpg"))):
        timestamp = idx / fps if fps > 0 else 0.0
        obj_key = f"{base_prefix}/frames/frame_{idx:06d}.jpg"
        upload = upload_file(path, obj_key)
        frames.append({"timestamp": timestamp, **upload})
    return frames


def _build_manifest(
    task_id: str,
    request: Dict[str, Any],
    duration: float,
    segments: List[Tuple[float, float]],
    original_video: Dict[str, Any],
    full_audio: Dict[str, Any] | None,
    video_slices: List[Dict[str, Any]],
    audio_slices: List[Dict[str, Any]],
    frames: List[Dict[str, Any]],
    asr_results: List[Dict[str, Any]],
    frame_captions: Dict[float, str],
    processing_time: float | None,
) -> Dict[str, Any]:
    kb_id = request.get("kb_id") or "default"
    doc_id = request.get("document_id") or task_id
    title = request.get("title") or Path(original_video["object_key"]).name

    chunks: List[Dict[str, Any]] = []
    for idx, (start, end) in enumerate(segments):
        duration_seg = max(0.0, end - start)
        video_obj = video_slices[idx]
        audio_obj = audio_slices[idx] if idx < len(audio_slices) else None
        frame_items = [f for f in frames if start <= f.get("timestamp", 0) < end]
        asr = asr_results[idx] if idx < len(asr_results) else {}
        text_seg = asr.get("text") or ""
        text_segments = [
            {
                "index": i + 1,
                "start_time": seg.get("start"),
                "end_time": seg.get("end"),
                "text": seg.get("text"),
            }
            for i, seg in enumerate(asr.get("segments") or [])
        ]
        keyframe_items = []
        for f_item in frame_items:
            ts = f_item.get("timestamp")
            desc = frame_captions.get(ts)
            keyframe_items.append(
                {
                    "timestamp": ts,
                    "thumbnail_url": f_item.get("url"),
                    "description": desc or "",
                }
            )
        chunk = {
            "chunk_id": f"{task_id}_seg_{idx:04d}",
            "media_type": "video",
            "temporal": {
                "start_time": start,
                "end_time": end,
                "duration": duration_seg,
                "chunk_index": idx + 1,
            },
            "content": {
                "text": {
                    "full_text": text_seg,
                    "segments": text_segments,
                    "language": asr.get("language") or request.get("language") or "unknown",
                },
                "audio": {
                    "url": audio_obj["url"] if audio_obj else None,
                    "format": "m4a",
                    "duration": duration_seg,
                },
                "video": {
                    "url": video_obj["url"],
                    "format": "mp4",
                    "duration": duration_seg,
                },
            },
            "keyframes": keyframe_items,
            "processing": {
                "status": "success",
                "processing_time": processing_time,
                "pipeline_version": "video-service-1",
            },
        }
        chunks.append(chunk)

    manifest: Dict[str, Any] = {
        "document_id": doc_id,
        "kb_id": kb_id,
        "kb_type": request.get("kb_type") or "enterprise",
        "document_metadata": {
            "title": title,
            "format": Path(original_video["object_key"]).suffix.lstrip("."),
            "duration": duration,
            "total_chunks": len(chunks),
            "source_info": {
                "file_name": title,
                "storage_url": original_video.get("url"),
                "bundle_url": None,
            },
        },
        "vector_status": "pending",
        "status": request.get("status") or "active",
        "chunks": chunks,
    }

    # Optional enrichments
    if frames:
        manifest.setdefault("document_summary", {})["key_points"] = [
            f"frame@{round(f['timestamp'], 2)}" for f in frames[: min(5, len(frames))]
        ]
    if full_audio:
        manifest.setdefault("document_metadata", {}).setdefault("audio", {})["url"] = full_audio.get("url")

    return manifest


def _evenly_pick(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """Pick items evenly up to limit to cover the range without biasing the head."""

    if limit <= 0 or len(items) <= limit:
        return items
    step = max(1, round(len(items) / limit))
    picked: List[Dict[str, Any]] = []
    for idx in range(0, len(items), step):
        picked.append(items[idx])
        if len(picked) >= limit:
            break
    return picked


@video_celery.task(name="video.process")
def process_video(request: Dict[str, Any]) -> Dict[str, Any]:
    """Download video, slice, extract frames/audio, upload all artifacts, and emit mm-schema JSON."""

    task_id = request.get("task_id") or uuid4().hex
    started_at = time.perf_counter()
    workdir = Path(tempfile.mkdtemp(prefix="video-mm-"))
    try:
        video_path = _materialize_media(request, workdir)
        duration = _probe_duration(video_path)
        if duration <= 0:
            duration = float(settings.processing.fixed_segment_seconds * 3)

        segment_seconds = float(request.get("segment_seconds") or settings.processing.fixed_segment_seconds)
        fps = float(request.get("frame_sample_fps") or settings.processing.frame_sample_fps)

        segments: List[Tuple[float, float]] = []
        if request.get("scene_cut"):
            threshold = float(request.get("scene_threshold") or settings.processing.scene_change_threshold)
            min_duration = float(request.get("scene_min_duration_sec") or settings.processing.scene_min_duration_sec)
            segments = _scene_segments(video_path, threshold, min_duration, duration)
            if not segments:
                logger.warning("Scene cut found no segments; fallback to fixed %.2fs", segment_seconds)
        if not segments:
            segments = _fixed_segments(duration, segment_seconds)
        if not segments:
            segments = [(0.0, duration)]

        base_prefix = f"mm/video/{task_id}"

        original_obj = upload_file(video_path, f"{base_prefix}/video/original{video_path.suffix}")

        audio_path = _extract_audio(video_path, workdir)
        full_audio_obj = upload_file(audio_path, f"{base_prefix}/audio/full.m4a") if audio_path.exists() else None

        video_slices = _slice_video(video_path, segments, base_prefix, workdir)
        audio_slices = _slice_audio(audio_path, segments, base_prefix, workdir)
        frame_objs = _extract_frames(video_path, fps, base_prefix, workdir)

        # ASR per audio slice
        asr_results: List[Dict[str, Any]] = []
        for audio_obj in audio_slices:
            if audio_obj and audio_obj.get("url"):
                asr_results.append(_call_asr_task(audio_obj["url"]))
            else:
                asr_results.append({})

        # Caption frames via multimodal (per-chunk selection to cover timeline)
        cap_override = request.get("frame_caption_max")
        frame_prompt = request.get("frame_prompt") or "请用一句话描述画面主体与场景"
        # Choose frames to caption per chunk, spread evenly to avoid only early frames.
        frames_for_caption: List[Dict[str, Any]] = []
        for start, end in segments:
            frames_in_chunk = [f for f in frame_objs if start <= f.get("timestamp", 0.0) < end]
            if cap_override is None:
                cap_per_chunk = len(frames_in_chunk)  # default: caption all keyframes in the chunk
            else:
                cap_per_chunk = int(cap_override)
                if cap_per_chunk <= 0:
                    cap_per_chunk = len(frames_in_chunk)
            frames_for_caption.extend(_evenly_pick(frames_in_chunk, cap_per_chunk))

        # Deduplicate by timestamp to avoid duplicate caption calls when limits overlap.
        unique_frames: Dict[float, Dict[str, Any]] = {}
        for f in frames_for_caption:
            ts = f.get("timestamp")
            if ts is not None and ts not in unique_frames:
                unique_frames[ts] = f

        frame_captions: Dict[float, str] = _caption_frames_async(list(unique_frames.values()), frame_prompt)

        total_processing_time = round(time.perf_counter() - started_at, 3)

        manifest = _build_manifest(
            task_id,
            request,
            duration,
            segments,
            original_obj,
            full_audio_obj,
            video_slices,
            audio_slices,
            frame_objs,
            asr_results,
            frame_captions,
            total_processing_time,
        )
        manifest_path = workdir / "mm-schema.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_obj = upload_file(manifest_path, f"{base_prefix}/json/mm-schema.json")

        return {
            "task_id": task_id,
            "bucket": manifest_obj["bucket"],
            "manifest_key": manifest_obj["object_key"],
            "manifest_url": manifest_obj["url"],
            "prefix": base_prefix,
            "doc": manifest,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


@video_celery.task(name="video.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    async_result = process_video.apply_async(args=[request])
    return {"task_id": async_result.id}
