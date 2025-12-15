"""Celery tasks for embedding and reranking using an OpenAI-compatible API."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import requests

from .celery_app import vector_celery
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_api_key() -> str:
    # Prefer runtime env for overrides/tests
    api_key = os.getenv("VECTOR_bailian__api_key") or settings.bailian.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("VECTOR_bailian__api_key is required")
    return api_key


def _normalize(endpoint_suffix: str) -> str:
    base = (os.getenv("VECTOR_bailian__api_base") or settings.bailian.api_base).rstrip("/")
    if base.endswith(endpoint_suffix):
        return base
    return f"{base}/{endpoint_suffix}"


def _call_embeddings(inputs: List[str], model: str | None = None) -> Dict[str, Any]:
    api_key = _get_api_key()
    endpoint = _normalize("embeddings")
    payload = {"model": model or settings.bailian.embed_model, "input": inputs}
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(endpoint, json=payload, timeout=settings.bailian.request_timeout_sec, headers=headers)
    resp.raise_for_status()
    return resp.json()


def _call_rerank(query: str, passages: List[str], top_k: int = 5, model: str | None = None) -> List[Dict[str, Any]]:
    api_key = _get_api_key()
    endpoint = _normalize("chat/completions")
    prompt = (
        "你是排序助手。给定查询和多个候选文本，请按相关度从高到低排序，输出 JSON 数组，每个元素包含: index(原序号), score(0-1之间), text。"
        "禁止输出其他说明。\n"
        f"查询: {query}\n候选: \n"
    )
    for idx, passage in enumerate(passages):
        prompt += f"[{idx}] {passage}\n"
    payload = {
        "model": model or settings.bailian.rerank_model,
        "messages": [
            {"role": "system", "content": "你是严格的排序器，只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(endpoint, json=payload, timeout=settings.bailian.request_timeout_sec, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    content = choices[0].get("message", {}).get("content") if choices else "[]"
    try:
        import json as _json

        parsed = _json.loads(content)
    except Exception:  # noqa: BLE001
        logger.warning("Failed to parse rerank JSON, returning empty list")
        return []
    # ensure top_k
    return parsed[:top_k]


@vector_celery.task(name="vector.embed")
def embed(request: Dict[str, Any]) -> Dict[str, Any]:
    inputs = request.get("input") or request.get("inputs")
    if not inputs:
        raise ValueError("input list is required")
    if isinstance(inputs, str):
        inputs = [inputs]
    model = request.get("model") or settings.bailian.embed_model
    result = _call_embeddings(inputs, model=model)
    return {"model": model, "data": result.get("data"), "usage": result.get("usage"), "raw": result}


@vector_celery.task(name="vector.rerank")
def rerank(request: Dict[str, Any]) -> Dict[str, Any]:
    query = request.get("query")
    passages = request.get("passages") or []
    if not query or not passages:
        raise ValueError("query and passages are required")
    top_k = int(request.get("top_k") or 5)
    model = request.get("model") or settings.bailian.rerank_model
    ranked = _call_rerank(query, passages, top_k=top_k, model=model)
    return {"model": model, "ranked": ranked}


@vector_celery.task(name="vector.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    action = request.get("action") or "embed"
    if action == "embed":
        async_result = embed.apply_async(args=[request])
    elif action == "rerank":
        async_result = rerank.apply_async(args=[request])
    else:
        raise ValueError("action must be embed or rerank")
    return {"task_id": async_result.id}
