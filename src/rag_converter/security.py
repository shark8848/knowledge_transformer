"""API authentication helpers for appid/key validation."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict

from fastapi import Depends, Request

from .config import Settings, settings_dependency
from .errors import raise_error


class AppKeyValidator:
    """Validates incoming appid/key pairs against the secrets file."""

    def __init__(self, secrets_path: str) -> None:
        self._path = Path(secrets_path)
        self._cache: Dict[str, str] = {}
        self._last_mtime: float | None = None
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            self._cache = {}
            self._last_mtime = None
            return
        mtime = self._path.stat().st_mtime
        if self._last_mtime == mtime:
            return
        with self._path.open("r", encoding="utf-8") as handle:
            data = json.load(handle) or {}
        if not isinstance(data, dict):
            raise ValueError("App secrets file must contain a JSON object of {appid: key}")
        self._cache = {str(k): str(v) for k, v in data.items()}
        self._last_mtime = mtime

    def is_valid(self, appid: str, key: str) -> bool:
        self._load()
        return self._cache.get(appid) == key


@lru_cache
def get_validator(secrets_path: str) -> AppKeyValidator:
    Path(secrets_path).parent.mkdir(parents=True, exist_ok=True)
    if not Path(secrets_path).exists():
        # initialize empty file for convenience
        Path(secrets_path).write_text("{}", encoding="utf-8")
    return AppKeyValidator(secrets_path)


def authenticate_request(
    request: Request, settings: Settings = Depends(settings_dependency)
) -> None:
    auth_cfg = settings.api_auth
    if not auth_cfg.required:
        return

    appid = request.headers.get(auth_cfg.header_appid) or request.query_params.get("appid")
    key = request.headers.get(auth_cfg.header_key) or request.query_params.get("key")

    if not appid or not key:
        raise_error("ERR_AUTH_MISSING")

    validator = get_validator(auth_cfg.app_secrets_path)
    if not validator.is_valid(appid, key):
        raise_error("ERR_AUTH_INVALID")
