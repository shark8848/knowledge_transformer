#!/usr/bin/env python
"""Manual test: pull an existing mm-schema.json from MinIO, run metadata enrichment, upload result.

Usage:
  python scripts/run_meta_from_minio.py --object-key mm/video/<id>/json/mm-schema.json [--output-key custom/path.json]

Requires .env (or META_* envs) for MinIO and Bailian settings. Does not overwrite the source file.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Ensure local src/ is importable when running as a script
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from meta_service import tasks  # noqa: E402
from meta_service.storage import download_object, upload_file  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run meta_service enrichment against an existing manifest in MinIO")
    parser.add_argument("--object-key", required=True, help="Source mm-schema.json object key in MinIO")
    parser.add_argument(
        "--output-key",
        help="Destination object key for enriched manifest (default: derive from source with .meta.json)",
    )
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    with tempfile.TemporaryDirectory(prefix="meta-cli-") as tmpdir:
        tmpdir_path = Path(tmpdir)
        src_path = tmpdir_path / "mm-schema.json"

        print(f"[meta-cli] Downloading from MinIO: {args.object_key}")
        download_object(args.object_key, src_path)

        manifest = json.loads(src_path.read_text(encoding="utf-8"))
        total_chunks = len(manifest.get("chunks") or [])
        print(f"[meta-cli] Loaded manifest with {total_chunks} chunks")

        enriched = tasks._enrich_manifest(manifest)  # reuse service logic

        # Derive output key
        output_key = args.output_key
        if not output_key:
            src = Path(args.object_key)
            output_key = str(src.with_name(src.stem + ".meta.json"))

        out_path = tmpdir_path / "mm-schema.meta.json"
        out_path.write_text(json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8")

        stored = upload_file(out_path, output_key)
        doc_ex = (enriched.get("document_metadata") or {}).get("extraction") or {}
        print("[meta-cli] Uploaded enriched manifest:")
        print(f"  bucket: {stored['bucket']}")
        print(f"  object_key: {stored['object_key']}")
        print(f"  url: {stored['url']}")
        print(f"  chunks_with_extraction: {doc_ex.get('chunks_with_extraction')}")
        summary_preview = (doc_ex.get("summary") or "").split("\n")[0:1]
        if summary_preview:
            print(f"  summary: {summary_preview[0][:200]}")


if __name__ == "__main__":
    main()
