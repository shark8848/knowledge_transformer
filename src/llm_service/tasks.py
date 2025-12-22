"""Celery tasks for a generic chat-completion LLM service."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import requests

from .celery_app import llm_celery
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_bailian_api_key() -> str:
    # Prefer runtime env to allow tests/overrides after import
    api_key = os.getenv("LLM_bailian__api_key") or settings.bailian.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError("LLM_bailian__api_key is required")
    return api_key


def _normalize_bailian_endpoint() -> str:
    base = (os.getenv("LLM_bailian__api_base") or settings.bailian.api_base).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _call_bailian(messages: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    api_key = _get_bailian_api_key()
    endpoint = _normalize_bailian_endpoint()
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


def _get_teamshub_token() -> str:
    token = os.getenv("LLM_teamshub__token") or settings.teamshub.token
    if not token:
        raise ValueError("LLM_teamshub__token is required")
    return token


def _normalize_teamshub_endpoint() -> str:
    base = (os.getenv("LLM_teamshub__api_base") or settings.teamshub.api_base).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def _collect_stream(resp: requests.Response) -> Dict[str, Any]:
    """Consume a streaming response and stitch content into a single message."""

    content_parts: List[str] = []
    usage: Optional[Dict[str, Any]] = None
    finish_reason: Optional[str] = None
    raw_events: List[Any] = []

    for line in resp.iter_lines():
        if not line:
            continue
        try:
            text = line.decode("utf-8").strip()
        except Exception:  # noqa: BLE001
            continue
        if not text:
            continue
        if text.startswith("data:"):
            text = text[len("data:") :].strip()
        if not text or text == "[DONE]":
            finish_reason = finish_reason or "stop"
            continue
        try:
            data = json.loads(text)
        except Exception:  # noqa: BLE001
            logger.debug("Skip non-JSON stream chunk: %s", text)
            continue
        raw_events.append(data)
        choices = data.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            if "content" in delta:
                content_parts.append(delta["content"])
            finish_reason = choices[0].get("finish_reason") or finish_reason
        if data.get("usage"):
            usage = data["usage"]

    message = {"role": "assistant", "content": "".join(content_parts)}
    return {
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason or "stop",
                "message": message,
            }
        ],
        "usage": usage,
        "raw": raw_events,
    }


def _call_teamshub(messages: List[Dict[str, Any]], **kwargs: Any) -> Dict[str, Any]:
    token = _get_teamshub_token()
    endpoint = _normalize_teamshub_endpoint()
    stream = kwargs.get("stream")
    if stream is None:
        stream = settings.teamshub.stream
    enable_thinking = kwargs.get("enable_thinking")
    if enable_thinking is None:
        enable_thinking = settings.teamshub.enable_thinking

    payload: Dict[str, Any] = {
        "model": kwargs.get("model") or settings.teamshub.model,
        "messages": messages,
        "stream": stream,
        "enable_thinking": enable_thinking,
    }
    for field in ("temperature", "top_p", "max_tokens"):
        if kwargs.get(field) is not None:
            payload[field] = kwargs[field]

    headers = {"token": token}
    resp = requests.post(
        endpoint,
        json=payload,
        timeout=settings.teamshub.request_timeout_sec,
        headers=headers,
        stream=stream,
    )
    resp.raise_for_status()
    if stream:
        return _collect_stream(resp)
    return resp.json()


def _call_llm(messages: List[Dict[str, Any]], provider: str, **kwargs: Any) -> Dict[str, Any]:
    provider = (provider or settings.default_provider).lower()
    if provider == "teamshub":
        return _call_teamshub(messages, **kwargs)
    if provider in ("bailian", "dashscope"):
        return _call_bailian(messages, **kwargs)
    raise ValueError(f"unsupported provider: {provider}")


def _default_model(provider: str) -> str:
    provider = (provider or settings.default_provider).lower()
    if provider == "teamshub":
        return settings.teamshub.model
    if provider in ("bailian", "dashscope"):
        return settings.bailian.model
    raise ValueError(f"unsupported provider: {provider}")


@llm_celery.task(name="llm.chat")
def chat(request: Dict[str, Any]) -> Dict[str, Any]:
    messages = request.get("messages") or []
    if not messages:
        raise ValueError("messages is required")
    provider = request.get("provider") or request.get("channel") or settings.default_provider
    model = request.get("model") or _default_model(provider)
    params = {
        k: request.get(k)
        for k in (
            "temperature",
            "top_p",
            "max_tokens",
            "response_format",
            "stream",
            "enable_thinking",
        )
        if request.get(k) is not None
    }
    result = _call_llm(messages, provider=provider, model=model, **params)
    return {
        "provider": provider,
        "model": model,
        "choices": result.get("choices"),
        "usage": result.get("usage"),
        "raw": result,
    }


@llm_celery.task(name="llm.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    async_result = chat.apply_async(args=[request])
    return {"task_id": async_result.id}
