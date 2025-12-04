"""Plugin that uses LibreOffice to convert doc -> docx."""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class DocToDocxPlugin(ConversionPlugin):
    slug = "doc-to-docx"
    source_format = "doc"
    target_format = "docx"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for doc files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            cmd = [
                "soffice",
                "--headless",
                "--convert-to",
                "docx",
                "--outdir",
                str(tmpdir_path),
                str(input_path),
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            output_candidate = tmpdir_path / (input_path.stem + ".docx")
            if not output_candidate.exists():
                raise RuntimeError("LibreOffice conversion did not produce output")

            final_output = input_path.with_suffix(".docx")
            output_candidate.replace(final_output)

        metadata = {"note": "Converted via LibreOffice soffice"}
        return ConversionResult(output_path=final_output, metadata=metadata)


REGISTRY.register(DocToDocxPlugin)
