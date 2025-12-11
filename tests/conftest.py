"""Shared pytest fixtures for the conversion service tests."""

from __future__ import annotations

import json
from typing import Callable

import pytest

from rag_converter.config import (
    APIAuthSettings,
    ConversionFormat,
    FileLimitSettings,
    RateLimitSettings,
    Settings,
)


@pytest.fixture()
def secrets_file(tmp_path):
    path = tmp_path / "appkeys.json"
    path.write_text(json.dumps({"test-app": "secret-key"}), encoding="utf-8")
    return path


@pytest.fixture()
def test_settings(secrets_file) -> Settings:
    return Settings(
        service_name="rag-conversion-engine-test",
        environment="test",
        api_version="v1",
        base_url="/api/v1",
        file_limits=FileLimitSettings(
            default_max_size_mb=50,
            per_format_max_size_mb={"doc": 20, "svg": 5},
            max_total_upload_size_mb=80,
            max_files_per_task=3,
        ),
        convert_formats=[ConversionFormat(source="doc", target="docx", plugin="doc-to-docx")],
        api_auth=APIAuthSettings(
            required=True,
            app_secrets_path=str(secrets_file),
            header_appid="X-Appid",
            header_key="X-Key",
        ),
        rate_limit=RateLimitSettings(enabled=False, interval_sec=60, max_requests=100),
    )


@pytest.fixture()
def noop_validator(monkeypatch) -> Callable[[str, str], bool]:
    class _Validator:
        def __init__(self) -> None:
            self.checked: list[tuple[str, str]] = []

        def is_valid(self, appid: str, key: str) -> bool:
            self.checked.append((appid, key))
            return True

    validator = _Validator()
    monkeypatch.setattr("rag_converter.security.get_validator", lambda path: validator)
    return validator
