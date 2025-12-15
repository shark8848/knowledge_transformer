"""Simple smoke test client for the multimodal (Ali Bailian) service.

Usage:
    python scripts/test_multimodal_service.py --api http://127.0.0.1:8300 \
        --url https://raw.githubusercontent.com/pytorch/hub/master/images/dog.jpg

    python scripts/test_multimodal_service.py --api http://127.0.0.1:8300 \
        --file ./sample.jpg

Defaults:
    - API: http://127.0.0.1:8300
    - Media URL: sample dog image from PyTorch hub

Requires that the multimodal service is running and MM/BAILIAN env vars are set (API key).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any, Dict

import requests

DEFAULT_MEDIA = "https://upload.wikimedia.org/wikipedia/commons/3/3a/Cat03.jpg"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multimodal service smoke test")
    parser.add_argument("media", nargs="?", default=None, help="Optional positional media URL or file path")
    parser.add_argument("--api", default="http://127.0.0.1:8300", help="Multimodal API base url")
    parser.add_argument("--url", default=DEFAULT_MEDIA, help="Image/Video URL to analyze")
    parser.add_argument("--file", default=None, help="Optional local file path (uploads via service)")
    parser.add_argument("--prompt", default=None, help="Optional prompt override")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--kind", default="image", choices=["image", "video"], help="Media kind")
    parser.add_argument("--poll-seconds", type=float, default=1.5, help="Polling interval seconds")
    parser.add_argument("--timeout", type=float, default=60.0, help="Overall timeout seconds")
    return parser.parse_args()


def post_analyze(
    api: str,
    url: str | None,
    file_path: str | None,
    prompt: str | None,
    model: str | None,
    kind: str,
) -> str:
    payload: Dict[str, Any] = {
        "kind": kind,
        "prompt": prompt,
        "model": model,
    }
    if file_path:
        payload["object_key"] = file_path
    elif url:
        payload["input_url"] = url
    else:
        raise RuntimeError("Provide either --url or --file")
    resp = requests.post(f"{api}/api/v1/mm/analyze", json=payload, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError(f"Unexpected response: {data}")
    print(f"submitted task_id={task_id}")
    return task_id


def fetch_result(api: str, task_id: str, timeout: float, poll_seconds: float) -> Dict[str, Any]:
    deadline = time.time() + timeout
    url = f"{api}/api/v1/mm/result/{task_id}"
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
    # If positional media is provided, route it to url or file automatically.
    if args.media:
        if args.media.startswith("http://") or args.media.startswith("https://"):
            args.url = args.media
        else:
            args.file = args.media
    try:
        task_id = post_analyze(args.api, args.url, args.file, args.prompt, args.model, args.kind)
        result = fetch_result(args.api, task_id, args.timeout, args.poll_seconds)
    except Exception as exc:  # noqa: BLE001
        print(f"test failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
