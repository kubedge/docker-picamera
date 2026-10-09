#!/usr/bin/env bash
# Build the linux/arm64 image, tagged `latest` and the package version. Pushing is manual,
# as for every kubedge1/* image: `docker login`, then `./build.sh --push`. CI only builds.
set -euo pipefail

cd "$(dirname "$0")"
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' src/docker_picamera/__init__.py)
docker buildx build --platform linux/arm64 \
  -t kubedge1/picamera:latest -t "kubedge1/picamera:${version}" "$@" .
