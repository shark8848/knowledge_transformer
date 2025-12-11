"""Unit tests for the centralized error helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException, status

from rag_converter.errors import ErrorCodeSpec, ErrorRegistry, raise_error


def test_raise_error_returns_structured_payload():
    with pytest.raises(HTTPException) as exc:
        raise_error("ERR_AUTH_MISSING", detail="custom detail")

    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    detail = exc.value.detail
    assert detail["error_code"] == "ERR_AUTH_MISSING"
    assert detail["error_status"] == 4010
    assert detail["message"] == "custom detail"
    assert detail["zh_message"]


def test_error_registry_rejects_duplicate_code():
    registry = ErrorRegistry()
    spec = ErrorCodeSpec(
        code="ERR_DUPLICATED",
        zh="重复",
        en="duplicate",
        status=4000,
        http_status=status.HTTP_400_BAD_REQUEST,
    )

    registry.register(spec)
    with pytest.raises(ValueError):
        registry.register(spec)
