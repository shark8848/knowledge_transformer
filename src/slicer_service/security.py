"""Minimal authentication helper for the slicer service."""

from __future__ import annotations

from fastapi import Depends, Request

from .config import Settings, settings_dependency
from .errors import raise_error


def authenticate_request(
    request: Request, settings: Settings = Depends(settings_dependency)
) -> None:
    auth_cfg = settings.api_auth
    if not auth_cfg.required:
        return

    appid = request.headers.get(auth_cfg.header_appid)
    key = request.headers.get(auth_cfg.header_key)

    if not appid or not key:
        raise_error("ERR_AUTH_MISSING")

    if appid != auth_cfg.appid or key != auth_cfg.key:
        raise_error("ERR_AUTH_INVALID")
