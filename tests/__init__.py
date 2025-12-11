"""Pytest package configuration for shared test artifacts."""

from __future__ import annotations

import os
from pathlib import Path

_ARTIFACT_ROOT = Path(__file__).resolve().parent / "artifacts" / "conversions"
_ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)

os.environ.setdefault("RAG_TEST_ARTIFACTS_DIR", str(_ARTIFACT_ROOT))
