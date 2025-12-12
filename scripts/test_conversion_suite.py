#!/usr/bin/env python3
"""End-to-end conversion smoke suite covering core formats (docx/html→pdf, svg→png, wav→mp3, gif→mp4).

Usage:
    API_URL=http://127.0.0.1:8000/api/v1/convert \
    API_APPID=xxx API_KEY=yyy \
    python scripts/test_conversion_suite.py

Env vars:
- API_URL: conversion endpoint (default http://127.0.0.1:8000/api/v1/convert)
- API_APPID / API_KEY: auth headers
- DOCX_PATH: optional path to a .docx file for docx->pdf case
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1/convert")
APP_ID = os.getenv("API_APPID", "12872b4f6d05")
API_KEY = os.getenv("API_KEY", "CDqH3KrwthT8GtX9TEQppLMOrB96N178zR-MzGgdEEk")


def _post(payload: Dict[str, Any], name: str) -> bool:
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "X-Appid": APP_ID,
        "X-Key": API_KEY,
    }
    req = Request(API_URL, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(f"[PASS] {name}: HTTP {resp.status} -> {body}")
            return True
    except HTTPError as exc:
        print(f"[FAIL] {name}: HTTP {exc.code} {exc.reason}")
        try:
            print(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            pass
        return False
    except URLError as exc:
        print(f"[FAIL] {name}: Request failed: {exc}")
        return False


def build_html_payload() -> Dict[str, Any]:
    html = (
        "<html><body><h1>Knowledge Transformer</h1>"
        "<p>Base64 HTML → PDF smoke</p>"
        "<p>scripts/test_conversion_suite.py</p>"
        "</body></html>"
    )
    raw = html.encode("utf-8")
    b64 = base64.b64encode(raw).decode("ascii")
    size_mb = round(len(raw) / (1024 * 1024), 4)
    return {
        "task_name": "html-to-pdf-suite",
        "priority": "normal",
        "files": [
            {
                "base64_data": b64,
                "source_format": "html",
                "target_format": "pdf",
                "filename": "sample.html",
                "size_mb": size_mb,
            }
        ],
    }


def build_docx_payload() -> Dict[str, Any] | None:
    docx_path = Path(os.getenv("DOCX_PATH", "knowledge_transformer详细设计文档.docx")).expanduser()
    if not docx_path.exists():
        print(f"[SKIP] docx-to-pdf: DOCX file missing at {docx_path}")
        return None
    raw = docx_path.read_bytes()
    b64 = base64.b64encode(raw).decode("ascii")
    size_mb = round(len(raw) / (1024 * 1024), 4)
    return {
        "task_name": "docx-to-pdf-suite",
        "priority": "normal",
        "files": [
            {
                "base64_data": b64,
                "source_format": "docx",
                "target_format": "pdf",
                "filename": docx_path.name,
                "size_mb": size_mb,
            }
        ],
    }


def build_svg_payload() -> Dict[str, Any]:
    svg = """<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64'><rect width='64' height='64' fill='teal'/><text x='8' y='36' font-size='16' fill='white'>KT</text></svg>"""
    raw = svg.encode("utf-8")
    b64 = base64.b64encode(raw).decode("ascii")
    size_mb = round(len(raw) / (1024 * 1024), 4)
    return {
        "task_name": "svg-to-png-suite",
        "priority": "normal",
        "files": [
            {
                "base64_data": b64,
                "source_format": "svg",
                "target_format": "png",
                "filename": "logo.svg",
                "size_mb": size_mb,
            }
        ],
    }


def build_wav_payload() -> Dict[str, Any]:
    import io
    import wave
    import struct

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        frames = b"".join(struct.pack("<h", 0) for _ in range(8000 // 10))  # 0.1s silence
        wav.writeframes(frames)
    raw = buffer.getvalue()
    b64 = base64.b64encode(raw).decode("ascii")
    size_mb = round(len(raw) / (1024 * 1024), 4)
    return {
        "task_name": "wav-to-mp3-suite",
        "priority": "normal",
        "files": [
            {
                "base64_data": b64,
                "source_format": "wav",
                "target_format": "mp3",
                "filename": "silence.wav",
                "size_mb": size_mb,
            }
        ],
    }


def build_gif_payload() -> Dict[str, Any]:
    # 1x1 transparent GIF
    gif_b64 = "R0lGODlhAQABAPAAAAAAAAAAACH5BAEAAAAALAAAAAABAAEAAAICRAEAOw=="
    raw = base64.b64decode(gif_b64)
    size_mb = round(len(raw) / (1024 * 1024), 4)
    return {
        "task_name": "gif-to-mp4-suite",
        "priority": "normal",
        "files": [
            {
                "base64_data": gif_b64,
                "source_format": "gif",
                "target_format": "mp4",
                "filename": "tiny.gif",
                "size_mb": size_mb,
            }
        ],
    }


def main() -> int:
    scenarios: List[tuple[str, Dict[str, Any]]] = []

    html_payload = build_html_payload()
    scenarios.append(("html(base64)->pdf", html_payload))

    docx_payload = build_docx_payload()
    if docx_payload:
        scenarios.append(("docx(base64)->pdf", docx_payload))

    scenarios.append(("svg(base64)->png", build_svg_payload()))
    scenarios.append(("wav(base64)->mp3", build_wav_payload()))
    scenarios.append(("gif(base64)->mp4", build_gif_payload()))

    if not scenarios:
        print("No scenarios to run.")
        return 1

    successes = 0
    for name, payload in scenarios:
        if _post(payload, name):
            successes += 1

    total = len(scenarios)
    print(f"Summary: {successes}/{total} scenarios succeeded")
    return 0 if successes == total else 1


if __name__ == "__main__":
    sys.exit(main())
