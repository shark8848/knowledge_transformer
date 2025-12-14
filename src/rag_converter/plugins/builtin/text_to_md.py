"""Plugins that convert plain text or markdown inputs into Markdown artifacts."""

from __future__ import annotations

from pathlib import Path

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


def _ensure_input(payload: ConversionInput) -> Path:
    if not payload.input_path:
        raise ValueError("Conversion requires local input_path for text/markdown files")
    path = Path(payload.input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path


def _materialize_markdown(src: Path) -> Path:
    dest = src if src.suffix.lower() == ".md" else src.with_suffix(".md")
    if dest != src:
        content = src.read_text(encoding="utf-8", errors="ignore")
        dest.write_text(content, encoding="utf-8")
    return dest


class _BaseToMarkdown(ConversionPlugin):
    target_format = "md"
    note: str = "Copied into Markdown"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        src = _ensure_input(payload)
        dest = _materialize_markdown(src)
        return ConversionResult(output_path=dest, metadata={"note": self.note})


class PlainTextToMarkdownPlugin(_BaseToMarkdown):
    slug = "txt-to-md"
    source_format = "txt"
    note = "Copied text/plain into Markdown"


class PlainMimeTextToMarkdownPlugin(_BaseToMarkdown):
    slug = "textplain-to-md"
    source_format = "text/plain"
    note = "Copied text/plain into Markdown"


class MarkdownPassthroughPlugin(_BaseToMarkdown):
    slug = "md-to-md"
    source_format = "md"
    note = "Passthrough markdown"


class MarkdownAliasPassthroughPlugin(_BaseToMarkdown):
    slug = "markdown-to-md"
    source_format = "markdown"
    note = "Passthrough markdown"


class MarkdownMimePassthroughPlugin(_BaseToMarkdown):
    slug = "textmarkdown-to-md"
    source_format = "text/markdown"
    note = "Passthrough markdown"


for plugin_cls in (
    PlainTextToMarkdownPlugin,
    PlainMimeTextToMarkdownPlugin,
    MarkdownPassthroughPlugin,
    MarkdownAliasPassthroughPlugin,
    MarkdownMimePassthroughPlugin,
):
    REGISTRY.register(plugin_cls)
