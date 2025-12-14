"""Plugin registry responsible for managing conversion capabilities."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple, Type

import yaml

from .base import ConversionPlugin


DEFAULT_PLUGIN_MODULES: Sequence[str] = (
    "rag_converter.plugins.builtin.doc_to_docx",
    "rag_converter.plugins.builtin.doc_to_pdf",
    "rag_converter.plugins.builtin.docx_to_pdf",
    "rag_converter.plugins.builtin.ppt_to_pdf",
    "rag_converter.plugins.builtin.svg_to_png",
    "rag_converter.plugins.builtin.gif_to_mp4",
    "rag_converter.plugins.builtin.webp_to_png",
    "rag_converter.plugins.builtin.audio_to_mp3",
    "rag_converter.plugins.builtin.video_to_mp4",
    "rag_converter.plugins.builtin.html_to_md",
    "rag_converter.plugins.builtin.text_to_md",
    "rag_converter.plugins.builtin.xlsx_to_pdf",
    "rag_converter.plugins.builtin.xlsx_to_md",
)


class PluginRegistry:
    def __init__(self) -> None:
        self._registry: Dict[Tuple[str, str], Type[ConversionPlugin]] = {}

    def register(self, plugin_cls: Type[ConversionPlugin]) -> None:
        key = (plugin_cls.source_format.lower(), plugin_cls.target_format.lower())
        if key in self._registry:
            raise ValueError(f"Plugin already registered for {key}")
        self._registry[key] = plugin_cls

    def get(self, source: str, target: str) -> ConversionPlugin:
        key = (source.lower(), target.lower())
        if key not in self._registry:
            raise KeyError(f"No plugin registered for {source}->{target}")
        return self._registry[key]()

    def list(self) -> Iterable[ConversionPlugin]:
        for plugin_cls in self._registry.values():
            yield plugin_cls()


REGISTRY = PluginRegistry()


def load_plugins(module_names: Iterable[str] | None = None) -> None:
    """Import plugin modules and trigger their registration side-effects."""

    modules = list(module_names or DEFAULT_PLUGIN_MODULES)
    for module in modules:
        import_module(module)


def read_plugin_module_file(path: str | Path) -> List[str]:
    file_path = Path(path)
    if not file_path.exists():
        return []

    with file_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    modules = data.get("modules", []) if isinstance(data, dict) else []
    return [str(module) for module in modules]


def write_plugin_module_file(path: str | Path, modules: Iterable[str]) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    ordered_unique = list(dict.fromkeys(str(module) for module in modules if module))
    payload = {"modules": ordered_unique}

    with file_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, allow_unicode=False, sort_keys=False)


__all__ = [
    "REGISTRY",
    "DEFAULT_PLUGIN_MODULES",
    "load_plugins",
    "read_plugin_module_file",
    "write_plugin_module_file",
]
