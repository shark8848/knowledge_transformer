"""Plugin that converts HTML into Markdown for downstream probing."""

from __future__ import annotations

from pathlib import Path

from markdownify import markdownify as html_to_markdown

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class HtmlToMarkdownPlugin(ConversionPlugin):
    slug = "html-to-md"
    source_format = "html"
    target_format = "md"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for HTML files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        html = input_path.read_text(encoding="utf-8", errors="ignore")
        markdown = html_to_markdown(html, heading_style="ATX")

        output_path = input_path.with_suffix(".md")
        output_path.write_text(markdown, encoding="utf-8")

        metadata = {"note": "Converted HTML to Markdown"}
        return ConversionResult(output_path=output_path, metadata=metadata)


REGISTRY.register(HtmlToMarkdownPlugin)
