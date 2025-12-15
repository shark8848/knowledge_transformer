"""FastAPI entrypoint for the Whisper ASR service."""

from __future__ import annotations

from fastapi import FastAPI

from .api.routes import router as api_router
from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ASR Service",
        version=settings.api_version,
        docs_url=f"{settings.base_url}/docs",
        redoc_url=f"{settings.base_url}/redoc",
        openapi_url=f"{settings.base_url}/openapi.json",
    )
    app.include_router(api_router, prefix=settings.base_url)

    @app.get("/healthz")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
