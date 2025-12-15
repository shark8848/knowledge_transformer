"""Shared error codes for the ASR service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from fastapi import HTTPException, status


@dataclass(frozen=True)
class ErrorCodeSpec:
    code: str
    zh: str
    en: str
    http_status: int


class ErrorRegistry:
    def __init__(self) -> None:
        self._codes: Dict[str, ErrorCodeSpec] = {}

    def register(self, spec: ErrorCodeSpec) -> None:
        if spec.code in self._codes:
            raise ValueError(f"Error code {spec.code} already registered")
        self._codes[spec.code] = spec

    def get(self, code: str) -> ErrorCodeSpec:
        if code not in self._codes:
            raise KeyError(f"Unknown error code: {code}")
        return self._codes[code]


ERRORS = ErrorRegistry()


def register_default_errors() -> None:
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_AUTH_MISSING",
            zh="认证信息缺失",
            en="Missing authentication information",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_AUTH_INVALID",
            zh="认证失败",
            en="Authentication failed",
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_BAD_REQUEST",
            zh="请求参数错误",
            en="Invalid request payload",
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    )


register_default_errors()


def raise_error(code: str, *, detail: str | None = None) -> None:
    spec = ERRORS.get(code)
    raise HTTPException(status_code=spec.http_status, detail=detail or spec.en)
