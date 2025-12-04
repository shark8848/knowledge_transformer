"""Plugin that uses FFmpeg to convert webp -> png."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class WebpToPngPlugin(ConversionPlugin):
    slug = "webp-to-png"
    source_format = "webp"
    target_format = "png"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for webp files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path = input_path.with_suffix(".png")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            str(output_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        metadata = {"note": "Converted via FFmpeg webp->png"}
        return ConversionResult(output_path=output_path, metadata=metadata)


REGISTRY.register(WebpToPngPlugin)
