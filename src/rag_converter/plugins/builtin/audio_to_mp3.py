"""Plugins converting common audio formats to mp3 via FFmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Type

from ..base import ConversionInput, ConversionPlugin, ConversionResult
from ..registry import REGISTRY


class _BaseAudioToMp3Plugin(ConversionPlugin):
    target_format = "mp3"

    def convert(self, payload: ConversionInput) -> ConversionResult:
        if not payload.input_path:
            raise ValueError("Conversion requires local input_path for audio files")

        input_path = Path(payload.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path = input_path.with_suffix(".mp3")
        duration = None
        if payload.metadata:
            duration = payload.metadata.get("duration_seconds")

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-q:a",
            "2",
            str(output_path),
        ]
        if duration:
            cmd.insert(6, str(duration))
            cmd.insert(6, "-t")
        subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        metadata = {"note": f"Converted {self.source_format}->mp3 via FFmpeg"}
        return ConversionResult(output_path=output_path, metadata=metadata)


class WavToMp3Plugin(_BaseAudioToMp3Plugin):
    slug = "wav-to-mp3"
    source_format = "wav"


class FlacToMp3Plugin(_BaseAudioToMp3Plugin):
    slug = "flac-to-mp3"
    source_format = "flac"


class OggToMp3Plugin(_BaseAudioToMp3Plugin):
    slug = "ogg-to-mp3"
    source_format = "ogg"


class AacToMp3Plugin(_BaseAudioToMp3Plugin):
    slug = "aac-to-mp3"
    source_format = "aac"


for plugin_cls in (WavToMp3Plugin, FlacToMp3Plugin, OggToMp3Plugin, AacToMp3Plugin):
    REGISTRY.register(plugin_cls)
