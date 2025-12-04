"""Plugin package exports and convenience loaders."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .registry import (
	DEFAULT_PLUGIN_MODULES,
	REGISTRY,
	load_plugins,
	read_plugin_module_file,
)

if TYPE_CHECKING:  # pragma: no cover - import guard for type checkers
	from rag_converter.config import Settings


def _modules_from_settings(settings: "Settings" | None) -> List[str]:
	if not settings:
		return []

	explicit = [module for module in settings.plugin_modules if module]
	if explicit:
		return explicit

	if settings.plugin_modules_file:
		modules = read_plugin_module_file(settings.plugin_modules_file)
		if modules:
			return modules

	return []


def load_plugins_from_settings(settings: "Settings" | None = None) -> None:
	"""Load plugin modules defined in settings or fallback to defaults."""

	modules = _modules_from_settings(settings)
	if not modules:
		modules = list(DEFAULT_PLUGIN_MODULES)
	load_plugins(modules)


__all__ = ["REGISTRY", "load_plugins_from_settings", "load_plugins", "DEFAULT_PLUGIN_MODULES"]
