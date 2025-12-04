"""Plugin that uses Inkscape to convert svg -> png."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class SvgToPngPlugin(ConversionPlugin):
    slug = "svg-to-png"
    source_format = "svg"
    target_format = "png"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for svg files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path = input_path.with_suffix(".png")
        cmd = [
            "inkscape",
            str(input_path),
            "--export-type=png",
            f"--export-filename={output_path}",
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        metadata = {"note": "Converted via Inkscape CLI"}
        return ConversionResult(output_path=output_path, metadata=metadata)


REGISTRY.register(SvgToPngPlugin)
