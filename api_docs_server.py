"""Standalone FastAPI server that serves Swagger/OpenAPI documentation."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
import uvicorn

# Avoid double-starting Prometheus exporters when importing the application.
os.environ.setdefault("RAG_DISABLE_METRICS", "1")

from rag_converter.app import create_app  # noqa: E402  (import after env var)
from rag_converter.config import reload_settings  # noqa: E402

app = FastAPI(
  title="API Documentation Server",
  description="Serves Swagger UI backed by the Knowledge Transformer OpenAPI schema",
  version="1.0.0",
  docs_url=None,
  redoc_url=None,
  openapi_url=None,
)


def _truthy(value: str | None, default: bool = False) -> bool:
  if value is None:
    return default
  return value.lower() in {"1", "true", "yes", "on"}


_ALWAYS_REFRESH = _truthy(os.getenv("API_DOCS_ALWAYS_REFRESH"), default=False)
_OPENAPI_CACHE: dict[str, Any] | None = None


def _target_server_url() -> str:
  """Return the base URL where the primary FastAPI service is reachable."""

  return os.getenv("API_DOCS_TARGET_URL", "http://127.0.0.1:8000")


def _build_openapi_spec() -> dict[str, Any]:
  config_file = os.getenv("API_DOCS_CONFIG")
  if config_file:
    os.environ["RAG_CONFIG_FILE"] = config_file
  reload_settings()
  source_app = create_app()
  spec = jsonable_encoder(
    get_openapi(
      title=source_app.title,
      version=source_app.version,
      routes=source_app.routes,
      description=source_app.description,
    )
  )
  spec["servers"] = [
    {
      "url": _target_server_url(),
      "description": "Knowledge Transformer API base URL",
    }
  ]
  return spec


def _get_openapi_spec() -> dict[str, Any]:
  global _OPENAPI_CACHE
  if _OPENAPI_CACHE is None or _ALWAYS_REFRESH:
    _OPENAPI_CACHE = _build_openapi_spec()
  return _OPENAPI_CACHE


@app.get("/", response_class=HTMLResponse)
async def swagger_ui() -> HTMLResponse:
  title = os.getenv("API_DOCS_TITLE", "Knowledge Transformer API Docs")
  favicon = os.getenv("API_DOCS_FAVICON")
  return get_swagger_ui_html(
    title=title,
    openapi_url="/openapi.json",
    swagger_favicon_url=favicon,
  )


@app.get("/redoc", response_class=HTMLResponse)
async def redoc_ui() -> HTMLResponse:
  title = os.getenv("API_DOCS_TITLE", "Knowledge Transformer API Docs")
  return get_redoc_html(
    title=title,
    openapi_url="/openapi.json",
  )


@app.get("/openapi.json", response_class=JSONResponse)
async def openapi_document() -> JSONResponse:
  spec = _get_openapi_spec()
  return JSONResponse(spec)


@app.get("/healthz", response_class=PlainTextResponse)
async def healthz() -> PlainTextResponse:
  return PlainTextResponse("ok")


def main() -> None:
  host = os.getenv("API_DOCS_HOST", "0.0.0.0")
  port = int(os.getenv("API_DOCS_PORT", "8090"))
  reload_enabled = _truthy(os.getenv("API_DOCS_RELOAD"), default=False)
  uvicorn.run(
    "api_docs_server:app",
    host=host,
    port=port,
    reload=reload_enabled,
  )


if __name__ == "__main__":
  main()
