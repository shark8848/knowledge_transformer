"""Plugins that use LibreOffice to convert ppt/pptx -> pdf."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY
from ..utils import trim_pdf_pages


def _convert_presentation_to_pdf(input_path: Path) -> Path:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(tmpdir_path),
            str(input_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        output_candidate = tmpdir_path / (input_path.stem + ".pdf")
        if not output_candidate.exists():
            raise RuntimeError("LibreOffice conversion did not produce output")

        final_output = input_path.with_suffix(".pdf")
        output_candidate.replace(final_output)
        return final_output


class PptToPdfPlugin(ConversionPlugin):
    slug = "ppt-to-pdf"
    source_format = "ppt"
    target_format = "pdf"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for ppt files")

        input_path = Path(payload.input_path)
        output_path = _convert_presentation_to_pdf(input_path)
        page_limit = None
        if payload.metadata:
            page_limit = payload.metadata.get("page_limit")
        if page_limit:
            trim_pdf_pages(output_path, int(page_limit))
        metadata = {"note": "Converted via LibreOffice soffice"}
        return ConversionResult(output_path=output_path, metadata=metadata)


class PptxToPdfPlugin(ConversionPlugin):
    slug = "pptx-to-pdf"
    source_format = "pptx"
    target_format = "pdf"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for pptx files")

        input_path = Path(payload.input_path)
        output_path = _convert_presentation_to_pdf(input_path)
        page_limit = None
        if payload.metadata:
            page_limit = payload.metadata.get("page_limit")
        if page_limit:
            trim_pdf_pages(output_path, int(page_limit))
        metadata = {"note": "Converted via LibreOffice soffice"}
        return ConversionResult(output_path=output_path, metadata=metadata)


REGISTRY.register(PptToPdfPlugin)
REGISTRY.register(PptxToPdfPlugin)
