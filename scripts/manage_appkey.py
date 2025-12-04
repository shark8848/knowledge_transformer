#!/usr/bin/env python3
"""Command-line tool to manage appid/key pairs for the conversion API."""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import uuid
from pathlib import Path
from typing import Dict

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rag_converter.config import get_settings  # noqa: E402


def _load_store(path: Path) -> Dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError("Secrets file must be a JSON object")
    return {str(k): str(v) for k, v in data.items()}


def _save_store(path: Path, data: Dict[str, str]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def cmd_generate(args: argparse.Namespace) -> None:
    settings = get_settings()
    path = Path(args.path or settings.api_auth.app_secrets_path)
    store = _load_store(path)
    appid = args.appid or uuid.uuid4().hex[:12]
    key = secrets.token_urlsafe(32)
    if appid in store and not args.force:
        raise SystemExit(f"appid {appid} already exists; use --force to overwrite")
    store[appid] = key
    _save_store(path, store)
    print(f"Generated appid={appid} key={key}")


def cmd_delete(args: argparse.Namespace) -> None:
    settings = get_settings()
    path = Path(args.path or settings.api_auth.app_secrets_path)
    store = _load_store(path)
    if args.appid not in store:
        raise SystemExit(f"appid {args.appid} not found")
    store.pop(args.appid)
    _save_store(path, store)
    print(f"Removed appid={args.appid}")


def cmd_list(args: argparse.Namespace) -> None:
    settings = get_settings()
    path = Path(args.path or settings.api_auth.app_secrets_path)
    store = _load_store(path)
    if not store:
        print("No app credentials found")
        return
    for appid, key in store.items():
        print(f"appid={appid} key={key}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage API appid/key secrets")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="Generate a new appid/key pair")
    gen.add_argument("--appid", help="Custom appid, defaults to random")
    gen.add_argument("--path", help="Override path to secrets file")
    gen.add_argument("--force", action="store_true", help="Overwrite existing appid")
    gen.set_defaults(func=cmd_generate)

    delete = sub.add_parser("delete", help="Delete an existing appid")
    delete.add_argument("appid", help="appid to remove")
    delete.add_argument("--path", help="Override path to secrets file")
    delete.set_defaults(func=cmd_delete)

    list_cmd = sub.add_parser("list", help="List all stored app credentials")
    list_cmd.add_argument("--path", help="Override path to secrets file")
    list_cmd.set_defaults(func=cmd_list)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
