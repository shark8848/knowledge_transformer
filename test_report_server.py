"""Lightweight FastAPI server that serves the latest pytest HTML report."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
import uvicorn

DEFAULT_REPORT_PATH = Path(__file__).resolve().parent / "test-report.html"

app = FastAPI(
    title="Test Report Server",
    description="Serves pytest HTML reports for quick sharing",
    version="1.0.0",
)


def _get_report_path() -> Path:
    env_path = os.getenv("TEST_REPORT_PATH")
    path = Path(env_path).expanduser() if env_path else DEFAULT_REPORT_PATH
    path = path.resolve()
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Report not found: {path}")
    return path


@app.get("/", response_class=HTMLResponse)
async def view_report() -> str:
    """Return the HTML markup so browsers can render inline."""

    path = _get_report_path()
    return path.read_text(encoding="utf-8")


@app.get("/download")
async def download_report() -> FileResponse:
    """Provide the HTML report for downloading."""

    path = _get_report_path()
    return FileResponse(path, media_type="text/html", filename=path.name)


@app.get("/healthz", response_class=PlainTextResponse)
async def health_check() -> str:
    return "ok"


def main() -> None:
    host = os.getenv("TEST_REPORT_HOST", "0.0.0.0")
    port = int(os.getenv("TEST_REPORT_PORT", "8088"))
    reload_enabled = os.getenv("TEST_REPORT_RELOAD", "false").lower() in {"1", "true", "yes"}
    uvicorn.run(
        "test_report_server:app",
        host=host,
        port=port,
        reload=reload_enabled,
    )


if __name__ == "__main__":
    main()
