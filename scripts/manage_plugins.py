#!/usr/bin/env python3
"""Command line utility for managing plugin module registration."""

from __future__ import annotations

import argparse
from importlib import import_module
from pathlib import Path
from typing import Iterable, List

from rag_converter.plugins.registry import (
    DEFAULT_PLUGIN_MODULES,
    read_plugin_module_file,
    write_plugin_module_file,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_PLUGIN_FILE = ROOT_DIR / "config" / "plugins.yaml"


def _resolve_file(path: str | None) -> Path:
    return Path(path).resolve() if path else DEFAULT_PLUGIN_FILE


def _load_modules(file_path: Path) -> List[str]:
    if not file_path.exists():
        return []
    return read_plugin_module_file(file_path)


def _ensure_file(file_path: Path) -> None:
    if not file_path.exists():
        write_plugin_module_file(file_path, DEFAULT_PLUGIN_MODULES)


def _write_modules(file_path: Path, modules: Iterable[str]) -> None:
    write_plugin_module_file(file_path, modules)


def _verify_importable(module_name: str) -> None:
    try:
        import_module(module_name)
    except Exception as exc:  # pragma: no cover - defensive
        raise SystemExit(f"Failed to import '{module_name}': {exc}")


def handle_list(args: argparse.Namespace) -> int:
    file_path = _resolve_file(args.file)
    modules = _load_modules(file_path)
    if not modules:
        print("No plugin modules configured. Use 'register' to add one.")
        return 0

    for module in modules:
        print(module)
    return 0


def handle_register(args: argparse.Namespace) -> int:
    file_path = _resolve_file(args.file)
    _ensure_file(file_path)

    modules = _load_modules(file_path)
    module_name = args.module.strip()
    if not module_name:
        raise SystemExit("Module name cannot be empty.")

    if module_name in modules and not args.force:
        print(f"Module '{module_name}' already registered; use --force to duplicate.")
        return 0

    if not args.no_verify:
        _verify_importable(module_name)

    modules.append(module_name)
    _write_modules(file_path, modules)
    print(f"Registered plugin module '{module_name}'.")
    return 0


def handle_unregister(args: argparse.Namespace) -> int:
    file_path = _resolve_file(args.file)
    if not file_path.exists():
        print(f"No plugin module file at {file_path}")
        return 0

    modules = _load_modules(file_path)
    module_name = args.module.strip()
    if module_name not in modules:
        print(f"Module '{module_name}' not found.")
        return 0

    modules = [module for module in modules if module != module_name]
    _write_modules(file_path, modules)
    print(f"Removed plugin module '{module_name}'.")
    return 0


def handle_reset(args: argparse.Namespace) -> int:
    file_path = _resolve_file(args.file)
    _write_modules(file_path, DEFAULT_PLUGIN_MODULES)
    print(f"Plugin module file reset to defaults at {file_path}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage plugin module registration.")
    parser.add_argument(
        "--file",
        dest="file",
        default=str(DEFAULT_PLUGIN_FILE),
        help="Path to the plugin module YAML file (default: %(default)s)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List registered plugin modules")
    list_parser.set_defaults(func=handle_list)

    register_parser = subparsers.add_parser("register", help="Register a plugin module")
    register_parser.add_argument("module", help="Python import path of the module")
    register_parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip import verification when registering",
    )
    register_parser.add_argument(
        "--force",
        action="store_true",
        help="Allow duplicate entries if needed",
    )
    register_parser.set_defaults(func=handle_register)

    unregister_parser = subparsers.add_parser(
        "unregister", help="Remove a plugin module from the registry"
    )
    unregister_parser.add_argument("module", help="Python import path of the module")
    unregister_parser.set_defaults(func=handle_unregister)

    reset_parser = subparsers.add_parser("reset", help="Reset to default builtin modules")
    reset_parser.set_defaults(func=handle_reset)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)

if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
