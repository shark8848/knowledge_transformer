#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_script() {
  local script_path="$1" label="$2"; shift 2
  if [[ ! -x "$script_path" ]]; then
    echo "[start-all] Skipping $label (missing or not executable: $script_path)" >&2
    return
  fi
  echo "[start-all] Starting $label ..."
  "$script_path" "$@" || echo "[start-all] Warning: $label exited with non-zero status" >&2
}

# Start core services first to satisfy dependencies.
run_script "$ROOT_DIR/start_converter.sh" "converter"
run_script "$ROOT_DIR/start_slicer.sh" "slicer"
# Pipeline handles downstream orchestration; disable its dependency autostart to avoid duplication.
DEPEND_START_CONVERTER=false DEPEND_START_SLICER=false \
  run_script "$ROOT_DIR/start_pipeline.sh" "pipeline"

echo "[start-all] Done." 
