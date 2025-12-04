"""RAG document normalization conversion engine package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:  # pragma: no cover
	from fastapi import FastAPI


def create_app() -> "FastAPI":
	from .app import create_app as _create_app

	return _create_app()


__all__ = ["create_app"]
