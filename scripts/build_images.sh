#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Usage: ./scripts/build_images.sh [target]
# target defaults to "all" defined in docker/docker-bake.hcl

TARGET="${1:-all}"

if ! command -v docker &>/dev/null; then
  echo "docker is required" >&2
  exit 1
fi

if ! docker buildx version &>/dev/null; then
  echo "docker buildx is required (Docker 20.10+)" >&2
  exit 1
fi

echo "[build] building target '${TARGET}' via docker buildx bake"
docker buildx bake -f docker/docker-bake.hcl "${TARGET}"
