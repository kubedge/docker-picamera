#!/usr/bin/env bash
# Build the linux/arm64 Rust image, tagged `latest` and the crate version. Pushing is
# manual, as for every kubedge1/* image: `docker login`, then `rust/build.sh --push`.
set -euo pipefail

cd "$(dirname "$0")/.."
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' rust/Cargo.toml | head -1)
docker buildx build --platform linux/arm64 -f rust/Dockerfile \
  -t kubedge1/picamera-rs:latest -t "kubedge1/picamera-rs:${version}" "$@" .
