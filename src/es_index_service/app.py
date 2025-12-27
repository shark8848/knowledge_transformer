"""FastAPI application for ES schema/index management."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from .api.routes import router as api_router
from .config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ES Index Service",
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

    app.include_router(api_router, prefix=settings.base_url or "")

    @app.get("/healthz")
    async def root_health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
