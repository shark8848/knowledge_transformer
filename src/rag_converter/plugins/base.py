"""Base classes for conversion plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass
class ConversionInput:
    source_format: str
    target_format: str
    input_path: Path | None = None
    input_url: str | None = None
    object_key: str | None = None
    metadata: Dict[str, Any] | None = None


@dataclass
class ConversionResult:
    output_path: Path | None = None
    output_url: str | None = None
    object_key: str | None = None
    metadata: Dict[str, Any] | None = None


class ConversionPlugin(ABC):
    slug: str = ""
    source_format: str = ""
    target_format: str = ""

    def __init__(self) -> None:
        self.slug = self.slug or f"{self.source_format}_to_{self.target_format}"

    @abstractmethod
    def convert(self, payload: ConversionInput) -> ConversionResult:
        """Execute the conversion and return a result."""

    def describe(self) -> Dict[str, str]:
        return {
            "slug": self.slug,
            "source": self.source_format,
            "target": self.target_format,
        }
