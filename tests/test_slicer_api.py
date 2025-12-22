from fastapi.testclient import TestClient

from slicer_service.app import create_app


def test_probe_profile_endpoint():
    app = create_app()
    client = TestClient(app)
    resp = client.post(
        "/api/v1/probe/profile",
        json={"samples": ["# Title\nParagraph text."]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "profile" in data
    assert 0.0 <= data["profile"].get("heading_ratio", 0) <= 1


def test_recommend_strategy_endpoint_custom_delimiter():
    app = create_app()
    client = TestClient(app)
    payload = {
        "samples": ["a---b---c---d---e---f"],
        "custom": {"enable": True, "delimiters": ["---"], "min_segments": 2},
        "emit_candidates": True,
    }
    resp = client.post("/api/v1/probe/recommend_strategy", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    rec = data.get("recommendation")
    assert rec
    assert rec["strategy_id"] == "custom_delimiter_split"
    assert rec["delimiter_hits"] >= 2
    assert rec["mode"] == "direct_delimiter"
    assert rec["mode_id"] == 1
    assert rec.get("mode_desc")
