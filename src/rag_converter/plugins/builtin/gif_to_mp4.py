"""Plugin that uses FFmpeg to convert gif -> mp4."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class GifToMp4Plugin(ConversionPlugin):
    slug = "gif-to-mp4"
    source_format = "gif"
    target_format = "mp4"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for gif files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path = input_path.with_suffix(".mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vf",
            "scale=ceil(iw/2)*2:ceil(ih/2)*2",
            "-movflags",
            "faststart",
            "-pix_fmt",
            "yuv420p",
        ]

        # Support optional duration trimming via payload.metadata['duration_seconds']
        duration = None
        if payload.metadata:
            duration = payload.metadata.get("duration_seconds")
        if duration:
            cmd.extend(["-t", str(duration)])

        cmd.append(str(output_path))

        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        metadata = {"note": "Converted via FFmpeg"}
        return ConversionResult(output_path=output_path, metadata=metadata)


REGISTRY.register(GifToMp4Plugin)
