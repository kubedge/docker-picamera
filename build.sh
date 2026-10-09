#!/usr/bin/env bash
# Build the linux/arm64 image locally. CI builds and publishes it: .github/workflows/image.yml.
set -euo pipefail

cd "$(dirname "$0")"
docker buildx build --platform linux/arm64 -t kubedge/picamera "$@" .
