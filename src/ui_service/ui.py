"""Gradio UI for pipeline upload & recommendation (standalone ui_service)."""
from __future__ import annotations

import os
import time
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
ES_SEARCH_API_URL = os.getenv("UI_ES_SEARCH_API_URL", "http://127.0.0.1:8086")
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


def _parse_json_field(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return requests.compat.json.loads(raw)
    except Exception:
        return None


def _parse_csv(raw: str):
    raw = (raw or "").strip()
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def _await_task(task_id: str, *, timeout: float = 15.0, interval: float = 0.5) -> dict:
    """Poll the search task until completion, raising on failure/timeout."""
    deadline = time.time() + timeout
    url = f"{ES_SEARCH_API_URL}/tasks/{task_id}"
    while True:
        resp = requests.get(url, timeout=10)
        try:
            data = resp.json()
        except Exception:
            raise RuntimeError(f"task status fetch failed: {resp.status_code} {resp.text}") from None

        state = data.get("state")
        if state == "SUCCESS":
            return data
        if state in {"FAILURE", "REVOKED"}:
            raise RuntimeError(f"search task failed: {data}")
        if time.time() > deadline:
            raise RuntimeError(f"search task timed out (state={state})")
        time.sleep(interval)


def _call_search(endpoint: str, payload: dict) -> dict:
    url = f"{ES_SEARCH_API_URL}{endpoint}"
    resp = requests.post(url, json=payload, timeout=60)
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"search submit failed: {resp.status_code} {resp.text}") from None
    if resp.status_code != 200:
        raise RuntimeError(f"search submit failed: {resp.status_code} {data}")

    task_id = data.get("task_id")
    if not task_id:
        raise RuntimeError(f"search submit missing task_id: {data}")
    return _await_task(task_id)


def _extract_hits(result: dict) -> list[dict]:
    hits = (((result or {}).get("result") or {}).get("body") or {}).get("hits", {}).get("hits", [])
    simplified = []
    for item in hits:
        src = item.get("_source", {})
        simplified.append(
            {
                "id": item.get("_id"),
                "index": item.get("_index"),
                "score": item.get("_score"),
                "title": src.get("title"),
                "content": (src.get("content") or "")[:200],
            }
        )
    return simplified


def run_fulltext_search(query: str, index_name: str, fields: str, filters: str, permission_filters: str, size: int, from_: int, highlight: str, source: str):
    payload = {
        "query": query,
        "index_name": index_name or None,
        "fields": _parse_csv(fields),
        "filters": _parse_json_field(filters),
        "permission_filters": _parse_json_field(permission_filters),
        "size": size,
        "from": from_,
        "highlight_fields": _parse_csv(highlight),
        "_source": _parse_csv(source),
    }
    data = _call_search("/search/text", payload)
    return data, _extract_hits(data)


def run_hybrid_search(query: str, query_vector: str, index_name: str, fields: str, filters: str, permission_filters: str, size: int, from_: int, vector_ratio: float, source: str):
    # 保证权重总和为 1：向量权重=vector_ratio，文本权重=1 - vector_ratio
    vector = _parse_json_field(query_vector) or []
    vr = max(0.0, min(1.0, vector_ratio or 0.5))
    payload = {
        "query": query,
        "query_vector": vector,
        "index_name": index_name or None,
        "fields": _parse_csv(fields),
        "filters": _parse_json_field(filters),
        "permission_filters": _parse_json_field(permission_filters),
        "size": size,
        "from": from_,
        "text_weight": 1.0 - vr,
        "vector_weight": vr,
        "_source": _parse_csv(source),
    }
    data = _call_search("/search/hybrid", payload)
    return data, _extract_hits(data)


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
    with gr.Blocks(title="Knowledge Transformer UI") as demo:
        gr.Markdown("## Knowledge Transformer 工具集")
        with gr.Tab("Pipeline 推荐"):
            gr.Markdown("上传文档 -> 存储到 MinIO -> 调用 Pipeline 推荐策略")
            file_in = gr.File(label="上传文档")
            summary = gr.Textbox(label="策略摘要")
            full = gr.JSON(label="完整结果")
            gr.Button("执行").click(run_pipeline, inputs=[file_in], outputs=[summary, full])

        with gr.Tab("全文检索"):
            with gr.Row():
                query = gr.Textbox(label="查询", placeholder="报销制度")
                index_name = gr.Textbox(label="索引/别名", value="kb_chunks_v1")
                size = gr.Slider(label="返回条数", minimum=1, maximum=50, value=10, step=1)
                from_ = gr.Slider(label="起始", minimum=0, maximum=500, value=0, step=1)
            fields = gr.Textbox(label="fields (逗号分隔)", value="content^3,title^2,summary")
            highlight = gr.Textbox(label="highlight_fields", value="content,title")
            source = gr.Textbox(label="_source (逗号分隔)", placeholder="chunk_id,title,content,tenant_id")
            filters = gr.Textbox(label="filters JSON", placeholder='[{"term": {"tenant_id": "ep_001"}}]')
            permission_filters = gr.Textbox(label="permission_filters JSON", placeholder='[{"term": {"tenant_id": "ep_001"}}]')
            btn_ft = gr.Button("搜索")
            ft_raw = gr.JSON(label="任务/原始返回")
            ft_hits = gr.Dataframe(headers=["id", "index", "score", "title", "content"], label="命中概览", datatype=["str", "str", "number", "str", "str"])
            btn_ft.click(
                run_fulltext_search,
                inputs=[query, index_name, fields, filters, permission_filters, size, from_, highlight, source],
                outputs=[ft_raw, ft_hits],
            )

        with gr.Tab("混合检索"):
            with gr.Row():
                h_query = gr.Textbox(label="查询", placeholder="员工差旅报销")
                h_index = gr.Textbox(label="索引/别名", value="kb_chunks_v1")
                h_size = gr.Slider(label="返回条数", minimum=1, maximum=50, value=10, step=1)
                h_from = gr.Slider(label="起始", minimum=0, maximum=500, value=0, step=1)
            h_fields = gr.Textbox(label="fields (逗号分隔)", value="content^3,title^2,summary")
            h_vector = gr.Textbox(label="query_vector (JSON 数组)", placeholder="[0.01,0.02,...]")
            h_ratio = gr.Slider(label="权重比 (向量0-1，文本=1-向量)", minimum=0.0, maximum=1.0, value=0.5, step=0.05)
            h_filters = gr.Textbox(label="filters JSON", placeholder='[{"term": {"tenant_id": "ep_001"}}]')
            h_permission = gr.Textbox(label="permission_filters JSON", placeholder='[{"term": {"tenant_id": "ep_001"}}]')
            h_source = gr.Textbox(label="_source (逗号分隔)", placeholder="chunk_id,title,content,tenant_id")
            btn_h = gr.Button("搜索")
            h_raw = gr.JSON(label="任务/原始返回")
            h_hits = gr.Dataframe(headers=["id", "index", "score", "title", "content"], label="命中概览", datatype=["str", "str", "number", "str", "str"])
            btn_h.click(
                run_hybrid_search,
                inputs=[h_query, h_vector, h_index, h_fields, h_filters, h_permission, h_size, h_from, h_ratio, h_source],
                outputs=[h_raw, h_hits],
            )

    demo.launch()


if __name__ == "__main__":
    launch_ui()
