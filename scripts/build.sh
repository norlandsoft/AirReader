#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

IMAGE_NAME="${IMAGE_NAME:-airfilereader}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

echo "=== Building AirFileReader container ==="
echo "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""

docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

echo ""
echo "=== Build complete ==="
echo "Run with: docker run -p 8000:8000 ${IMAGE_NAME}:${IMAGE_TAG}"
echo "Or: docker compose up -d"
