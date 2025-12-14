"""FastAPI application entrypoint for the slicer service."""

from __future__ import annotations

from fastapi import FastAPI, Response

from prometheus_client import CONTENT_TYPE_LATEST

from .config import get_settings
from .api.routes import router as api_router
from .monitoring import render_metrics


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Slicer Recommendation Service",
        version=settings.api_version,
        docs_url=f"{settings.base_url}/docs",
        redoc_url=f"{settings.base_url}/redoc",
        openapi_url=f"{settings.base_url}/openapi.json",
    )

    app.include_router(api_router, prefix=settings.base_url)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        data, content_type = render_metrics()
        return Response(content=data, media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
