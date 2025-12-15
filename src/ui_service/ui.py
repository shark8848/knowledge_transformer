"""Gradio UI for pipeline upload & recommendation (standalone ui_service)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Tuple

import gradio as gr
import requests

# Prefer UI-specific env, fallback to legacy pipeline env for compatibility
PIPELINE_API_URL = (
    os.getenv("UI_PIPELINE_API_URL")
    or os.getenv("PIPELINE_API_URL")
    or "http://127.0.0.1:9100"
)
DEFAULT_PAGE_LIMIT = int(
    os.getenv("UI_PIPELINE_SAMPLE_PAGES")
    or os.getenv("PIPELINE_SAMPLE_PAGES")
    or "500"
)

def _infer_format(file_path: Path) -> str:
    suffix = file_path.suffix.lower().lstrip(".")
    return suffix or "pdf"


def _call_upload(file_path: Path) -> str:
    with file_path.open("rb") as handle:
        resp = requests.post(
            f"{PIPELINE_API_URL}/api/v1/pipeline/upload",
            files={"file": (file_path.name, handle, "application/octet-stream")},
            timeout=120,
        )
    if resp.status_code != 200:
        raise RuntimeError(f"upload failed: {resp.status_code} {resp.text}")
    data = resp.json()
    return data["object_key"]


def _call_recommend(object_key: str, source_format: str) -> dict:
    payload = {
        "files": [
            {
                "source_format": source_format,
                "target_format": "pdf",
                "object_key": object_key,
                "page_limit": DEFAULT_PAGE_LIMIT,
            }
        ],
        "priority": "normal",
        "async_mode": False,
    }
    resp = requests.post(
        f"{PIPELINE_API_URL}/api/v1/pipeline/recommend", json=payload, timeout=240
    )
    if resp.status_code != 200:
        raise RuntimeError(f"pipeline failed: {resp.status_code} {resp.text}")
    return resp.json().get("result") or {}


def run_pipeline(file) -> Tuple[str, dict]:
    if not file:
        return "请先上传文件", {}
    file_path = Path(file.name if hasattr(file, "name") else file)
    source_format = _infer_format(file_path)
    object_key = _call_upload(file_path)
    result = _call_recommend(object_key, source_format)

    rec = result.get("recommendation", {})
    strategy = rec.get("strategy_id", "unknown")
    summary = f"推荐策略: {strategy}\n对象: {object_key}"
    return summary, result


def launch_ui():
    demo = gr.Interface(
        fn=run_pipeline,
        inputs=[gr.File(label="上传文档")],
        outputs=[
            gr.Textbox(label="策略摘要"),
            gr.JSON(label="完整结果"),
        ],
        title="Pipeline 文档切片推荐",
        description="上传文档 -> 存储到 MinIO -> 调用 Pipeline 推荐策略",
    )
    demo.launch()


if __name__ == "__main__":
    launch_ui()
