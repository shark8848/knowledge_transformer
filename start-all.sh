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
# Generic LLM service (independent provider)
run_script "$ROOT_DIR/start_llm.sh" "llm"
# Vector service (embeddings/rerank)
run_script "$ROOT_DIR/start_vector.sh" "vector"
# Pipeline handles downstream orchestration; disable its dependency autostart to avoid duplication.
DEPEND_START_CONVERTER=false DEPEND_START_SLICER=false \
  run_script "$ROOT_DIR/start_pipeline.sh" "pipeline"
# UI service (Gradio frontend)
run_script "$ROOT_DIR/start_ui.sh" "ui"

# ASR and multimodal are independent entrypoints used by video.
run_script "$ROOT_DIR/start_asr.sh" "asr"
run_script "$ROOT_DIR/start_multimodal.sh" "multimodal"

# Video service depends on asr/multimodal availability.
run_script "$ROOT_DIR/start_video.sh" "video"

# MinerU OCR/structure service (optional standalone)
run_script "$ROOT_DIR/start_mineru.sh" "mineru"

echo "[start-all] Done." 
