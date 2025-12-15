"""Simple smoke test client for the ASR service.

Usage:
    python scripts/test_asr_service.py --api http://127.0.0.1:8200 --url <audio_url>

Defaults:
    - API: http://127.0.0.1:8200
    - Audio URL: small public WAV sample
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict

import requests

DEFAULT_AUDIO = "https://huggingface.co/datasets/Narsil/asr_dummy/resolve/main/1.flac"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ASR service smoke test")
    parser.add_argument("--api", default="http://127.0.0.1:8200", help="ASR API base url")
    parser.add_argument("--url", default=DEFAULT_AUDIO, help="Audio file URL to transcribe")
    parser.add_argument("--model", default=None, help="Optional model name override")
    parser.add_argument("--language", default=None, help="Language hint, e.g. en")
    parser.add_argument("--poll-seconds", type=float, default=1.5, help="Polling interval seconds")
    parser.add_argument("--timeout", type=float, default=60.0, help="Overall timeout seconds")
    return parser.parse_args()


def post_transcribe(api: str, url: str, model: str | None, language: str | None) -> str:
    payload: Dict[str, Any] = {
        "source": {"input_url": url, "language": language},
        "options": {"model_name": model} if model else None,
    }
    resp = requests.post(f"{api}/api/v1/asr/transcribe", json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Unexpected response: {data}")
    print(f"submitted task_id={task_id}")
    return task_id


def fetch_result(api: str, task_id: str, timeout: float, poll_seconds: float) -> Dict[str, Any]:
    deadline = time.time() + timeout
    url = f"{api}/api/v1/asr/result/{task_id}"
    while True:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        status_val = (data.get("status") or "").lower()
        if status_val in {"success", "succeeded", "finished", "ready"} or data.get("result"):
            return data
        if status_val in {"failure", "failed"}:
            raise RuntimeError(f"Task failed: {data}")
        if time.time() >= deadline:
            return data
        print(f"polling {task_id} status={status_val or 'pending'} ...")
        time.sleep(poll_seconds)


def main() -> int:
    args = parse_args()
    try:
        task_id = post_transcribe(args.api, args.url, args.model, args.language)
        result = fetch_result(args.api, task_id, args.timeout, args.poll_seconds)
    except Exception as exc:  # noqa: BLE001
        print(f"test failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
