"""Unified logging configuration for pipeline service.

Sets up console + daily rotating file handler with detailed context
(timestamp, level, logger, function, line).
"""
from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from .config import get_settings

_configured = False


def setup_logging(force: bool = False, log_level: Optional[str] = None) -> None:
    """Configure root logging for pipeline.

    - Console + daily rotating file handler under settings.logging.log_dir
    - Format includes time, logger, level, function, and line number.
    - Idempotent unless force=True.
    """

    global _configured
    if _configured and not force:
        return

    settings = get_settings()
    log_dir = Path(settings.log_dir or "./logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    level_name = (log_level or settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_file = log_dir / "pipeline.log"

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s %(funcName)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handlers = []

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

    file_handler = TimedRotatingFileHandler(
        filename=str(log_file),
        when="midnight",
        interval=1,
        backupCount=int(getattr(settings, "log_backup_count", 7)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    handlers.append(file_handler)

    root = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs when reloading.
    root.handlers.clear()
    root.setLevel(level)
    for h in handlers:
        root.addHandler(h)

    _configured = True


__all__ = ["setup_logging"]
