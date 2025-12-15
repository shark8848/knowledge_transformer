import copy

from src.meta_service import tasks


def test_enrich_manifest_aggregates(monkeypatch):
    # Arrange: manifest with two chunks
    manifest = {
        "document_metadata": {"source_info": {"title": "demo"}},
        "chunks": [
            {
                "chunk_id": "c1",
                "temporal": {"start_time": 0, "end_time": 1},
                "content": {"text": {"segments": [{"text": "hello"}]}},
            },
            {
                "chunk_id": "c2",
                "temporal": {"start_time": 1, "end_time": 2},
                "content": {"text": {"full_text": "world"}},
            },
        ],
    }

    fake_payloads = [
        {
            "summary": "s1",
            "tags": ["t1", "t2"],
            "keywords": ["k1"],
            "questions": ["q1"],
        },
        {
            "summary": "s2",
            "tags": ["t2", "t3"],
            "keywords": ["k2"],
            "questions": ["q2"],
        },
    ]
    calls = {"count": 0}

    def fake_call_llm(prompt: str):
        idx = calls["count"]
        calls["count"] += 1
        return copy.deepcopy(fake_payloads[idx])

    monkeypatch.setattr(tasks, "_call_llm", fake_call_llm)

    # Act
    enriched = tasks._enrich_manifest(copy.deepcopy(manifest))

    # Assert chunk-level metadata injected
    assert enriched["chunks"][0]["metadata"]["extraction"]["summary"] == "s1"
    assert enriched["chunks"][1]["metadata"]["extraction"]["summary"] == "s2"

    # full_text backfilled from segments for first chunk
    assert enriched["chunks"][0]["content"]["text"]["full_text"] == "hello"
    # segments backfilled from full_text for second chunk
    assert enriched["chunks"][1]["content"]["text"]["segments"][0]["text"] == "world"

    # Assert document-level aggregation
    doc_ex = enriched["document_metadata"]["extraction"]
    assert doc_ex["chunks_with_extraction"] == 2
    assert doc_ex["summary"] == "s1\ns2"
    assert doc_ex["tags"] == ["t1", "t2", "t3"]  # dedup preserves order
    assert doc_ex["keywords"] == ["k1", "k2"]
    assert doc_ex["questions"] == ["q1", "q2"]

    # Processing status present
    meta_proc = enriched["processing"]["metadata_extraction"]
    assert meta_proc["status"] == "success"
    assert meta_proc["processed_chunks"] == 2
