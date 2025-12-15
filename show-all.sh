#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_script() {
  local script_path="$1" label="$2"
  if [[ ! -x "$script_path" ]]; then
    echo "[show-all] Skipping $label (missing or not executable: $script_path)" >&2
    return
  fi
  echo "[show-all] === $label ==="
  "$script_path" || echo "[show-all] Warning: $label exited with non-zero status" >&2
  echo ""
}

run_script "$ROOT_DIR/show_converter.sh" "converter"
run_script "$ROOT_DIR/show_slicer.sh" "slicer"
run_script "$ROOT_DIR/show_pipeline.sh" "pipeline"
run_script "$ROOT_DIR/show_ui.sh" "ui"
run_script "$ROOT_DIR/show_llm.sh" "llm"
run_script "$ROOT_DIR/show_vector.sh" "vector"
run_script "$ROOT_DIR/show_asr.sh" "asr"
run_script "$ROOT_DIR/show_multimodal.sh" "multimodal"
run_script "$ROOT_DIR/show_video.sh" "video"

echo "[show-all] Done." 
