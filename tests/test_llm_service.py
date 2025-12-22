import os

import pytest

from llm_service import tasks


def test_chat_invokes_openai_compatible_api(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, headers=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["headers"] = headers

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok"}},
                    ],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }

        return _Resp()

    monkeypatch.setenv("LLM_bailian__api_key", "dummy-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("LLM_bailian__api_base", "https://example.com/compatible-mode/v1")
    monkeypatch.setattr(tasks.requests, "post", fake_post)

    result = tasks.chat({"messages": [{"role": "user", "content": "hi"}], "model": "gpt-x", "temperature": 0.2})

    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "gpt-x"
    assert captured["json"]["messages"][0]["content"] == "hi"
    assert captured["json"]["temperature"] == 0.2
    assert captured["headers"]["Authorization"] == "Bearer dummy-key"
    assert result["provider"] == "bailian"
    assert result["choices"][0]["message"]["content"] == "ok"
    assert result["usage"]["prompt_tokens"] == 10


def test_chat_invokes_teamshub_api(monkeypatch):
    captured = {}

    def fake_post(url, json=None, timeout=None, headers=None, stream=None):  # noqa: A002
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        captured["headers"] = headers
        captured["stream"] = stream

        class _Resp:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "choices": [
                        {"message": {"role": "assistant", "content": "ok-teamshub"}},
                    ]
                }

        return _Resp()

    monkeypatch.setenv("LLM_teamshub__token", "dummy-token")
    monkeypatch.setenv("LLM_teamshub__api_base", "https://aicp.teamshub.com/custom")
    monkeypatch.setattr(tasks.requests, "post", fake_post)

    request = {
        "provider": "teamshub",
        "messages": [{"role": "user", "content": "hi"}],
        "model": "qwen3-32b",
        "stream": False,
    }

    result = tasks.chat(request)

    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "qwen3-32b"
    assert captured["json"]["messages"][0]["content"] == "hi"
    assert captured["json"]["stream"] is False
    assert captured["headers"]["token"] == "dummy-token"
    assert result["provider"] == "teamshub"
    assert result["choices"][0]["message"]["content"] == "ok-teamshub"


def test_chat_unknown_provider(monkeypatch):
    monkeypatch.setenv("LLM_bailian__api_key", "dummy-key")
    monkeypatch.setattr(tasks.requests, "post", lambda *_, **__: None)

    with pytest.raises(ValueError):
        tasks.chat({"provider": "unknown", "messages": [{"role": "user", "content": "hi"}]})
