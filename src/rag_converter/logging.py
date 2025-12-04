"""Logging configuration helpers for structured output."""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path
from typing import Any, Dict

import structlog

from .config import LoggingSettings


def configure_logging(settings: LoggingSettings) -> None:
    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    level_value = getattr(logging, settings.level.upper(), logging.INFO)

    logging_config: Dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "plain": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "plain",
                "level": settings.level,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": str(log_dir / "service.log"),
                "formatter": "plain",
                "maxBytes": settings.max_log_file_size_mb * 1024 * 1024,
                "backupCount": settings.backup_count,
                "level": settings.level,
            },
        },
        "root": {
            "handlers": ["console", "file"],
            "level": settings.level,
        },
    }

    logging.config.dictConfig(logging_config)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level_value),
        cache_logger_on_first_use=True,
    )
