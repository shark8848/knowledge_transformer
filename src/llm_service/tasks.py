"""Celery tasks for a generic chat-completion LLM service."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import requests

from .celery_app import llm_celery
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_api_key() -> str:
    # Prefer runtime env to allow tests/overrides after import
    api_key = os.getenv("LLM_bailian__api_key") or settings.bailian.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("LLM_bailian__api_key is required")
    return api_key


def _normalize_endpoint() -> str:
    base = (os.getenv("LLM_bailian__api_base") or settings.bailian.api_base).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _call_llm(messages: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    api_key = _get_api_key()
    endpoint = _normalize_endpoint()
    payload = {
        "model": kwargs.get("model") or settings.bailian.model,
        "messages": messages,
    }
    for field in ("temperature", "top_p", "max_tokens", "response_format"):
        if kwargs.get(field) is not None:
            payload[field] = kwargs[field]
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.post(endpoint, json=payload, timeout=settings.bailian.request_timeout_sec, headers=headers)
    resp.raise_for_status()
    return resp.json()


@llm_celery.task(name="llm.chat")
def chat(request: Dict[str, Any]) -> Dict[str, Any]:
    messages = request.get("messages") or []
    if not messages:
        raise ValueError("messages is required")
    model = request.get("model") or settings.bailian.model
    params = {k: request.get(k) for k in ("temperature", "top_p", "max_tokens", "response_format") if request.get(k) is not None}
    result = _call_llm(messages, model=model, **params)
    return {
        "model": model,
        "choices": result.get("choices"),
        "usage": result.get("usage"),
        "raw": result,
    }


@llm_celery.task(name="llm.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    async_result = chat.apply_async(args=[request])
    return {"task_id": async_result.id}
