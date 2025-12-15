import os

from vector_service import tasks


def test_embed_calls_bailian_embeddings(monkeypatch):
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
                    "data": [
                        {"index": 0, "embedding": [0.1, 0.2]},
                        {"index": 1, "embedding": [0.3, 0.4]},
                    ],
                    "usage": {"prompt_tokens": 2},
                }

        return _Resp()

    monkeypatch.setenv("VECTOR_bailian__api_key", "dummy-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "")
    monkeypatch.setenv("VECTOR_bailian__api_base", "https://example.com/compatible-mode/v1")
    monkeypatch.setenv("VECTOR_bailian__embed_model", "text-embedding-v1")
    monkeypatch.setattr(tasks.requests, "post", fake_post)

    result = tasks.embed({"input": ["hello", "world"], "model": "text-embedding-v1"})

    assert captured["url"].endswith("/embeddings")
    assert captured["json"]["model"] == "text-embedding-v1"
    assert captured["json"]["input"] == ["hello", "world"]
    assert captured["headers"]["Authorization"] == "Bearer dummy-key"
    assert result["data"][0]["embedding"] == [0.1, 0.2]


def test_rerank_calls_bailian_chat_completion(monkeypatch):
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
                        {
                            "message": {
                                "role": "assistant",
                                "content": '[{"index":0,"score":0.9,"text":"a"},{"index":1,"score":0.1,"text":"b"}]',
                            }
                        }
                    ]
                }

        return _Resp()

    monkeypatch.setenv("VECTOR_bailian__api_key", "dummy-key")
    monkeypatch.setenv("VECTOR_bailian__api_base", "https://example.com/compatible-mode/v1")
    monkeypatch.setenv("VECTOR_bailian__rerank_model", "qwen-plus")
    monkeypatch.setattr(tasks.requests, "post", fake_post)

    result = tasks.rerank({"query": "q", "passages": ["a", "b"], "top_k": 1, "model": "qwen-plus"})

    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["model"] == "qwen-plus"
    assert "q" in captured["json"]["messages"][1]["content"]
    assert captured["headers"]["Authorization"] == "Bearer dummy-key"
    assert result["ranked"][0]["index"] == 0
    assert result["ranked"][0]["score"] == 0.9
