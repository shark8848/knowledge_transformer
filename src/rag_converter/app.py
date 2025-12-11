"""FastAPI application factory for the conversion engine."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .api.routes import router as api_router
from .config import Settings, get_settings
from .logging import configure_logging
from .monitoring import ensure_metrics_server
from .plugins import load_plugins_from_settings


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.logging)
    load_plugins_from_settings(settings)

    metrics_disabled = os.getenv("RAG_DISABLE_METRICS", "false").lower() in {"1", "true", "yes"}
    if not metrics_disabled:
        ensure_metrics_server(settings.monitoring.prometheus_port)

    app = FastAPI(
        title="Knowledge Transformer Engine",
        version=settings.api_version,
        docs_url=f"{settings.base_url}/docs",
        redoc_url=f"{settings.base_url}/redoc",
        openapi_url=f"{settings.base_url}/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"])

    app.include_router(api_router, prefix=settings.base_url)

    @app.get("/healthz")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
