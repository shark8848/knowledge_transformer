"""Helpers for format normalization and markdown-preferring defaults."""

from __future__ import annotations

TEXTUAL_FORMATS = {
    "html",
    "txt",
    "text/plain",
    "md",
    "markdown",
    "text/markdown",
    "xlsx",
    "xls",
}
MARKDOWN_FORMATS = {"md", "markdown", "text/markdown"}


def normalize_format(fmt: str | None) -> str:
    return (fmt or "").strip().lower()


def normalize_source_format(fmt: str | None) -> str:
    raw = normalize_format(fmt)
    mapping = {
        "application/pdf": "pdf",
        "text/html": "html",
        "application/xhtml+xml": "html",
        "htm": "html",
        "text/plain": "text/plain",
        "plain": "text/plain",
        "text/markdown": "text/markdown",
    }
    return mapping.get(raw, raw)


def normalize_target_format(fmt: str | None) -> str:
    return normalize_format(fmt) or "pdf"


def prefer_markdown_target(source_format: str | None, target_format: str | None) -> str:
    source = normalize_source_format(source_format)
    target = normalize_target_format(target_format)
    if source in TEXTUAL_FORMATS and target == "pdf":
        return "md"
    return target


def is_markdown_target(fmt: str | None) -> bool:
    return normalize_target_format(fmt) in MARKDOWN_FORMATS
