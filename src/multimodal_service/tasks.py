"""Celery tasks for Ali Bailian multimodal analysis."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import dashscope
import requests
from dashscope.aigc.multimodal_conversation import MultiModalConversation
from dashscope.utils.oss_utils import upload_file
from celery import chain
from fastapi import HTTPException
from jinja2 import Template

from .celery_app import mm_celery
from .config import get_settings
from .errors import raise_error

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT_TEMPLATE = Template(
    """
你是一名多模态理解与OCR助手。请严格按以下步骤输出简洁要点：
1) OCR：提取画面中所有可见文字，保持原始顺序与大小写，如有多处请按视觉顺序列出。
2) 场景拆分：清晰区分【人物/行为】与【环境/界面/物体】两类信息；若无人物请说明无人物。
3) 关键信息：提炼核心对象、操作、界面元素，避免编造未出现的内容。
4) 附加提示（如有）：{{ user_hint or "无" }}。仅在不与以上要求冲突时参考，优先遵循系统要求。
输出使用简短中文要点。
    """
)


def _get_api_key() -> str:
    key = settings.bailian.api_key or os.getenv("DASHSCOPE_API_KEY")
    if not key:
        raise_error("ERR_BAD_REQUEST", detail="MM_bailian__api_key is required")
    return key


def _render_prompt(user_prompt: str | None) -> str:
    # System template enforces OCR +人物/场景分离；user hint is optional and lower priority.
    return SYSTEM_PROMPT_TEMPLATE.render(user_hint=(user_prompt or "").strip())


def _init_dashscope(api_key: str) -> None:
    dashscope.api_key = api_key
    base = settings.bailian.api_base.rstrip("/") if settings.bailian.api_base else None
    if base and "compatible-mode" not in base:
        os.environ.setdefault("DASHSCOPE_HTTP_BASE_URL", base)
        if base.startswith("https://"):
            os.environ.setdefault("DASHSCOPE_WEBSOCKET_BASE_URL", base.replace("https://", "wss://"))


def _resolve_media_url(source: Dict[str, Any], api_key: str, model: str) -> str:
    if source.get("input_url"):
        return str(source["input_url"])

    local_path = source.get("object_key")
    if local_path:
        path = Path(local_path)
        if not path.exists():
            raise_error("ERR_BAD_REQUEST", detail=f"object_key/local_path not found: {local_path}")
        # Upload to DashScope OSS to avoid external download timeouts.
        upload_url = upload_file(model, f"file://{path}", api_key)
        return upload_url

    raise_error("ERR_BAD_REQUEST", detail="input_url or object_key required")


def _build_sdk_messages(media_url: str, prompt: str, kind: str, model: str) -> Dict[str, Any]:
    media_item: Dict[str, Any] = {"image": media_url} if kind == "image" else {"video": media_url}
    text_item = {"text": prompt}
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [media_item, text_item],
            }
        ],
    }


def _build_http_payload(media_url: str, prompt: str, kind: str, model: str) -> Dict[str, Any]:
    media_item = {"type": "image_url", "image_url": {"url": media_url}}
    if kind == "video":
        media_item = {"type": "image_url", "image_url": {"url": media_url, "image_format": "video"}}
    text_item = {"type": "text", "text": prompt}
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [media_item, text_item],
            }
        ],
    }


def _call_bailian_sdk(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    _init_dashscope(api_key)
    response = MultiModalConversation.call(
        model=payload.get("model"),
        messages=payload.get("messages"),
        timeout=settings.bailian.request_timeout_sec,
    )
    # DashScopeResponse exposes common fields directly; capture what we can first.
    result: Dict[str, Any] = {}
    for key in ("output", "usage", "code", "message", "request_id", "status_code", "data"):
        try:
            val = getattr(response, key)
        except Exception:  # noqa: BLE001
            val = None
        if val is not None:
            result[key] = val
    if result:
        return result

    try:
        to_dict = getattr(response, "to_dict", None)
        if callable(to_dict):
            return to_dict()  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        pass

    try:
        return response.__dict__  # type: ignore[no-any-return]
    except Exception:  # noqa: BLE001
        pass

    try:
        return dict(response)  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected DashScope response type: %s", type(response))
        raise_error("ERR_UPSTREAM", detail=str(exc))


def _call_bailian_http(payload: Dict[str, Any], api_key: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    api_url = settings.bailian.api_base.rstrip("/")
    if "/services/" not in api_url:
        api_url = f"{api_url}/chat/completions"
    resp = requests.post(
        api_url,
        json=payload,
        headers=headers,
        timeout=settings.bailian.request_timeout_sec,
    )
    try:
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        detail = f"{exc}: {resp.text}"
        logger.exception("Bailian call failed: %s", detail)
        raise_error("ERR_UPSTREAM", detail=detail)
    return resp.json()


def _is_download_timeout(exc: Exception) -> bool:
    text = str(exc)
    return "Download the media resource timed out" in text or "InvalidParameter.DataInspection" in text


def _is_download_timeout_result(result: Dict[str, Any]) -> bool:
    code = str(result.get("code") or "").lower()
    message = str(result.get("message") or "").lower()
    return "invalidparameter.datainspection" in code or "download the media resource timed out" in message


def _is_invalid_media_exc(exc: Exception) -> bool:
    text = str(exc).lower()
    return "invalidparameter" in text or "does not appear to be valid" in text


def _is_invalid_media_result(result: Dict[str, Any]) -> bool:
    code = str(result.get("code") or "").lower()
    message = str(result.get("message") or "").lower()
    return "invalidparameter" in code or "does not appear to be valid" in message or "invalid media" in message


def _upload_and_call(media_url: str, prompt: str, kind: str, model: str, api_key: str) -> Dict[str, Any]:
    # Download media locally then upload to DashScope OSS to bypass remote fetch issues.
    resp = requests.get(media_url, timeout=20)
    resp.raise_for_status()

    parsed = urlparse(media_url)
    suffix = Path(parsed.path).suffix or ".bin"
    tmp_path = Path(tempfile.mkstemp(suffix=suffix)[1])
    try:
        tmp_path.write_bytes(resp.content)
        oss_url = upload_file(model, f"file://{tmp_path}", api_key)
        payload = _build_sdk_messages(oss_url, prompt, kind, model)
        return _call_bailian_sdk(payload, api_key)
    finally:
        tmp_path.unlink(missing_ok=True)


def _extract_text(result: Dict[str, Any]) -> str | None:
    output = result.get("output") or {}
    choices = output.get("choices") or []
    for choice in choices:
        message = choice.get("message") or {}
        content = message.get("content") or []
        for item in content:
            if isinstance(item, dict) and item.get("text"):
                return item.get("text")
    return None


@mm_celery.task(name="mm.call")
def call_bailian(request: Dict[str, Any]) -> Dict[str, Any]:
    source = request.get("source") or {}
    prompt = _render_prompt(source.get("prompt") or settings.bailian.user_prompt)
    kind = source.get("kind") or "image"
    model = source.get("model") or settings.bailian.model

    api_key = _get_api_key()
    media_url = _resolve_media_url(source, api_key, model)
    sdk_payload = _build_sdk_messages(media_url, prompt, kind, model)
    http_payload = _build_http_payload(media_url, prompt, kind, model)

    try:
        result = _call_bailian_sdk(sdk_payload, api_key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bailian SDK call failed, falling back to HTTP: %s", exc)
        try:
            result = _call_bailian_http(http_payload, api_key)
        except HTTPException as http_exc:  # type: ignore[misc]
            if source.get("input_url") and (_is_download_timeout(http_exc) or _is_invalid_media_exc(http_exc)):
                logger.warning("Remote fetch failed, re-uploading media then retrying via SDK")
                result = _upload_and_call(source["input_url"], prompt, kind, model, api_key)
            else:
                raise

    if source.get("input_url") and isinstance(result, dict) and (
        _is_download_timeout_result(result) or _is_invalid_media_result(result)
    ):
        logger.warning("Upstream rejected media URL, re-uploading then retrying via SDK")
        result = _upload_and_call(source["input_url"], prompt, kind, model, api_key)

    text = _extract_text(result) if isinstance(result, dict) else None
    return {"text": text, "raw": result}


@mm_celery.task(name="mm.orchestrate")
def orchestrate(request: Dict[str, Any]) -> Dict[str, Any]:
    workflow = chain(call_bailian.s(request))
    async_result = workflow.apply_async()
    return {"task_id": async_result.id}
