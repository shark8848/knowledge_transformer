#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

run_script() {
  local script_path="$1" label="$2"
  if [[ ! -x "$script_path" ]]; then
    echo "[stop-all] Skipping $label (missing or not executable: $script_path)" >&2
    return
  fi
  echo "[stop-all] Stopping $label ..."
  "$script_path" || echo "[stop-all] Warning: $label exited with non-zero status" >&2
}

# Stop dependent consumers before providers.
run_script "$ROOT_DIR/stop_video.sh" "video"
run_script "$ROOT_DIR/stop_pipeline.sh" "pipeline"
run_script "$ROOT_DIR/stop_ui.sh" "ui"
run_script "$ROOT_DIR/stop_llm.sh" "llm"
run_script "$ROOT_DIR/stop_vector.sh" "vector"
run_script "$ROOT_DIR/stop_es_search_service.sh" "es_search_service"
run_script "$ROOT_DIR/stop_es_index_service.sh" "es_index_service"
run_script "$ROOT_DIR/stop_multimodal.sh" "multimodal"
run_script "$ROOT_DIR/stop_asr.sh" "asr"
run_script "$ROOT_DIR/stop_slicer.sh" "slicer"
run_script "$ROOT_DIR/stop_converter.sh" "converter"
run_script "$ROOT_DIR/stop_mineru.sh" "mineru"

echo "[stop-all] Done." 
