"""Error code registry and helpers for consistent API responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from fastapi import HTTPException, status


@dataclass(frozen=True)
class ErrorCodeSpec:
    code: str
    zh: str
    en: str
    status: int
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

    def to_dict(self) -> Dict[str, ErrorCodeSpec]:
        return dict(self._codes)


ERRORS = ErrorRegistry()


def register_default_errors() -> None:
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_AUTH_MISSING",
            zh="认证信息缺失",
            en="Missing authentication information",
            status=4010,
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_AUTH_INVALID",
            zh="认证失败，appid或key错误",
            en="Authentication failed: invalid appid or key",
            status=4011,
            http_status=status.HTTP_401_UNAUTHORIZED,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_FILE_TOO_LARGE",
            zh="单个文件大小超出限制",
            en="File exceeds per-format size limit",
            status=4201,
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_BATCH_LIMIT_EXCEEDED",
            zh="批量任务超出数量或体积限制",
            en="Batch exceeds allowed number or total size",
            status=4202,
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_FORMAT_UNSUPPORTED",
            zh="文件格式暂不支持",
            en="Unsupported source format",
            status=4203,
            http_status=status.HTTP_400_BAD_REQUEST,
        )
    )
    ERRORS.register(
        ErrorCodeSpec(
            code="ERR_TASK_FAILED",
            zh="任务执行失败",
            en="Conversion task failed",
            status=5001,
            http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
    )


register_default_errors()


def raise_error(code: str, *, detail: Optional[str] = None) -> None:
    spec = ERRORS.get(code)
    raise HTTPException(
        status_code=spec.http_status,
        detail={
            "status": "failure",
            "error_code": spec.code,
            "error_status": spec.status,
            "message": detail or spec.en,
            "zh_message": spec.zh,
        },
    )
