import os

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
    assert result["choices"][0]["message"]["content"] == "ok"
    assert result["usage"]["prompt_tokens"] == 10
