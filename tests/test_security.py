"""Test suite for the security helpers."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from rag_converter.config import settings_dependency
from rag_converter.security import AppKeyValidator, authenticate_request


def _build_protected_app(settings) -> FastAPI:
    app = FastAPI()

    @app.get("/protected", dependencies=[Depends(authenticate_request)])
    def protected_endpoint() -> dict[str, str]:  # pragma: no cover - trivial
        return {"status": "ok"}

    app.dependency_overrides[settings_dependency] = lambda: settings
    return app


def test_appkeyvalidator_reloads_file_when_changed(tmp_path):
    secrets = tmp_path / "appkeys.json"
    secrets.write_text(json.dumps({"demo": "secret"}), encoding="utf-8")

    validator = AppKeyValidator(str(secrets))
    assert validator.is_valid("demo", "secret")
    assert not validator.is_valid("demo", "wrong")

    secrets.write_text(json.dumps({"demo": "new-secret"}), encoding="utf-8")
    current = secrets.stat().st_mtime
    os.utime(secrets, (current + 1, current + 1))
    assert validator.is_valid("demo", "new-secret")


def test_authenticate_request_accepts_valid_headers(test_settings, noop_validator):
    app = _build_protected_app(test_settings)
    client = TestClient(app)

    headers = {
        test_settings.api_auth.header_appid: "test-app",
        test_settings.api_auth.header_key: "secret-key",
    }

    response = client.get("/protected", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert noop_validator.checked == [("test-app", "secret-key")]


def test_authenticate_request_falls_back_to_query_params(test_settings, noop_validator):
    app = _build_protected_app(test_settings)
    client = TestClient(app)

    params = {"appid": "query-app", "key": "query-secret"}
    response = client.get("/protected", params=params)

    assert response.status_code == 200
    assert noop_validator.checked == [("query-app", "query-secret")]


def test_authenticate_request_rejects_missing_credentials(test_settings, noop_validator):
    app = _build_protected_app(test_settings)
    client = TestClient(app)

    headers = {test_settings.api_auth.header_appid: "test-app"}
    response = client.get("/protected", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "ERR_AUTH_MISSING"
    assert noop_validator.checked == []


def test_authenticate_request_rejects_invalid_credentials(test_settings, monkeypatch):
    def _fake_validator(path: str) -> Any:
        class _Validator:
            def __init__(self) -> None:
                self.path = path

            def is_valid(self, appid: str, key: str) -> bool:
                return False

        return _Validator()

    monkeypatch.setattr("rag_converter.security.get_validator", _fake_validator)
    app = _build_protected_app(test_settings)
    client = TestClient(app)

    headers = {
        test_settings.api_auth.header_appid: "test-app",
        test_settings.api_auth.header_key: "secret-key",
    }
    response = client.get("/protected", headers=headers)

    assert response.status_code == 401
    assert response.json()["detail"]["error_code"] == "ERR_AUTH_INVALID"
