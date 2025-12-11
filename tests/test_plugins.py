"""Tests for plugin registry helpers."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from rag_converter.plugins.base import ConversionInput, ConversionPlugin, ConversionResult
from rag_converter.plugins.builtin.svg_to_png import SvgToPngPlugin
from rag_converter.plugins.registry import (
    PluginRegistry,
    load_plugins,
    read_plugin_module_file,
    write_plugin_module_file,
)


class _EchoPlugin(ConversionPlugin):
    slug = "echo"
    source_format = "doc"
    target_format = "docx"

    def convert(self, payload):  # pragma: no cover - trivial example
        return ConversionResult(output_path=Path("/tmp/output.docx"))


def test_plugin_registry_register_and_get():
    registry = PluginRegistry()
    registry.register(_EchoPlugin)

    plugin = registry.get("doc", "docx")
    assert isinstance(plugin, _EchoPlugin)

    with pytest.raises(ValueError):
        registry.register(_EchoPlugin)

    with pytest.raises(KeyError):
        registry.get("mp3", "wav")

    assert any(isinstance(entry, _EchoPlugin) for entry in registry.list())


def test_load_plugins_imports_all_modules(monkeypatch):
    imports: list[str] = []
    monkeypatch.setattr(
        "rag_converter.plugins.registry.import_module",
        lambda name: imports.append(name),
    )

    load_plugins(["mod.alpha", "mod.beta"])
    assert imports == ["mod.alpha", "mod.beta"]


def test_read_plugin_module_file_returns_modules(tmp_path):
    file_path = tmp_path / "plugins.yaml"
    file_path.write_text("modules:\n  - foo.bar\n  - baz.qux\n", encoding="utf-8")

    modules = read_plugin_module_file(file_path)
    assert modules == ["foo.bar", "baz.qux"]


def test_read_plugin_module_file_missing(tmp_path):
    file_path = tmp_path / "missing.yaml"
    assert read_plugin_module_file(file_path) == []


def test_write_plugin_module_file_deduplicates_and_orders(tmp_path):
    file_path = tmp_path / "nested" / "modules.yaml"
    write_plugin_module_file(file_path, ["foo.bar", "foo.bar", "baz.qux"])

    data = yaml.safe_load(file_path.read_text(encoding="utf-8"))
    assert data == {"modules": ["foo.bar", "baz.qux"]}


def test_svg_to_png_plugin_converts_image(tmp_path, monkeypatch):
    assets_dir = Path(__file__).resolve().parent / "assets" / "images"
    source_svg = assets_dir / "kt_logo.svg"
    assert source_svg.exists(), "sample SVG asset missing"

    input_file = tmp_path / source_svg.name
    input_file.write_text(source_svg.read_text(encoding="utf-8"), encoding="utf-8")
    output_file = input_file.with_suffix(".png")

    def fake_run(cmd, check, stdout, stderr):  # pragma: no cover - patched behavior
        assert cmd[0] == "inkscape"
        assert cmd[1] == str(input_file)
        assert f"--export-filename={output_file}" in cmd
        output_file.write_bytes(b"fake-png-bytes")

    monkeypatch.setattr("rag_converter.plugins.builtin.svg_to_png.subprocess.run", fake_run)

    plugin = SvgToPngPlugin()
    result = plugin.convert(
        ConversionInput(
            source_format="svg",
            target_format="png",
            input_path=input_file,
        )
    )

    assert result.output_path == output_file
    assert result.metadata == {"note": "Converted via Inkscape CLI"}