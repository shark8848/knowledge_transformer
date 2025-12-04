"""Plugins converting common video formats to mp4 via FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class _BaseVideoToMp4Plugin(ConversionPlugin):
    target_format = "mp4"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for video files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path = input_path.with_suffix(".mp4")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-crf",
            "23",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "faststart",
            str(output_path),
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        metadata = {"note": f"Converted {self.source_format}->mp4 via FFmpeg"}
        return ConversionResult(output_path=output_path, metadata=metadata)


class AviToMp4Plugin(_BaseVideoToMp4Plugin):
    slug = "avi-to-mp4"
    source_format = "avi"


class MovToMp4Plugin(_BaseVideoToMp4Plugin):
    slug = "mov-to-mp4"
    source_format = "mov"


class MkvToMp4Plugin(_BaseVideoToMp4Plugin):
    slug = "mkv-to-mp4"
    source_format = "mkv"


class WebmToMp4Plugin(_BaseVideoToMp4Plugin):
    slug = "webm-to-mp4"
    source_format = "webm"


class MpegToMp4Plugin(_BaseVideoToMp4Plugin):
    slug = "mpeg-to-mp4"
    source_format = "mpeg"


for plugin_cls in (AviToMp4Plugin, MovToMp4Plugin, MkvToMp4Plugin, WebmToMp4Plugin, MpegToMp4Plugin):
    REGISTRY.register(plugin_cls)
