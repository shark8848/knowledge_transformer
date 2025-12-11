#!/usr/bin/env python3
"""Simple API smoke test: send base64 HTML and request PDF conversion."""

from __future__ import annotations

import base64
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000/api/v1/convert")
APP_ID = os.getenv("API_APPID", "12872b4f6d05")
API_KEY = os.getenv("API_KEY", "CDqH3KrwthT8GtX9TEQppLMOrB96N178zR-MzGgdEEk")

HTML_BODY = """
<html>
  <head><title>PDF Smoke</title></head>
  <body>
    <h1>Knowledge Transformer</h1>
    <p>富文本内联转 PDF 测试</p>
    <p>Task generated from test_pdf_conversion.py</p>
  </body>
</html>
""".strip()


def build_payload() -> dict:
    raw_bytes = HTML_BODY.encode("utf-8")
    b64 = base64.b64encode(raw_bytes).decode("ascii")
    size_mb = round(len(raw_bytes) / (1024 * 1024), 4)

    return {
        "task_name": "html-to-pdf-smoke",
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


def main() -> int:
    payload = build_payload()
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
            print(f"HTTP {resp.status}")
            print(body)
            return 0
    except HTTPError as exc:
        print(f"HTTP error {exc.code}: {exc.reason}")
        try:
            print(exc.read().decode("utf-8", errors="replace"))
        except Exception:
            pass
        return 1
    except URLError as exc:
        print(f"Request failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
