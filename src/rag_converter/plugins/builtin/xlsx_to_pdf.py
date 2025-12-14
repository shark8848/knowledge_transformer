"""Plugins that convert Excel spreadsheets to PDF via LibreOffice."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY
from ..utils import trim_pdf_pages


class _BaseExcelToPdf(ConversionPlugin):
    target_format = "pdf"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for Excel files")

        input_path = Path(payload.input_path)
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

        page_limit = None
        if payload.metadata:
            page_limit = payload.metadata.get("page_limit")
        if page_limit:
            trim_pdf_pages(final_output, int(page_limit))

        metadata = {"note": "Converted Excel via LibreOffice soffice"}
        return ConversionResult(output_path=final_output, metadata=metadata)


class XlsxToPdfPlugin(_BaseExcelToPdf):
    slug = "xlsx-to-pdf"
    source_format = "xlsx"


class XlsToPdfPlugin(_BaseExcelToPdf):
    slug = "xls-to-pdf"
    source_format = "xls"


REGISTRY.register(XlsxToPdfPlugin)
REGISTRY.register(XlsToPdfPlugin)
