#!/usr/bin/env bash
# If invoked with sh (e.g., sudo sh script), re-exec with bash so pipefail is supported.
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

# Quick environment check for ASR service: verifies ffmpeg, python + whisper, and pre-downloads a model.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_BIN="$ROOT_DIR/.venv/bin"
PY_CMD="$VENV_BIN/python"
MODEL_NAME="${ASR_MODEL_NAME:-base}"  # override to pin a specific Whisper model size
export PYTHONPATH="$ROOT_DIR/src"

require_bin() {
  if [[ ! -x "$1" ]]; then
    echo "[asr-env] Missing executable: $1" >&2
    exit 1
  fi
}

require_bin "$PY_CMD"
require_bin "$(command -v ffmpeg || true)"

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[asr-env] ffmpeg not found in PATH" >&2
  exit 1
fi

echo "[asr-env] Using python: $PY_CMD"
echo "[asr-env] Using ffmpeg: $(command -v ffmpeg)"
echo "[asr-env] Checking whisper import and ensuring model '$MODEL_NAME' is available..."

"$PY_CMD" - "$MODEL_NAME" <<'PY'
import sys
model_name = sys.argv[1]
try:
    import whisper
except Exception as exc:  # noqa: BLE001
    print(f"[asr-env] Failed to import whisper: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    model = whisper.load_model(model_name)
    print(f"[asr-env] Whisper model '{model_name}' ready (device={model.device})")
except Exception as exc:  # noqa: BLE001
    print(f"[asr-env] Failed to load/download model '{model_name}': {exc}", file=sys.stderr)
    sys.exit(1)
PY

echo "[asr-env] Environment check passed."
