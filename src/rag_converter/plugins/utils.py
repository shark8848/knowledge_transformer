"""Shared plugin utilities."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter


def trim_pdf_pages(pdf_path: Path, max_pages: int) -> None:
    """Keep only the first `max_pages` pages of the PDF in-place."""
    if max_pages <= 0:
        return
    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()

    for idx, page in enumerate(reader.pages):
        if idx >= max_pages:
            break
        writer.add_page(page)

    with pdf_path.open("wb") as handle:
        writer.write(handle)

