#!/usr/bin/env bash
# Measure an image's peak container memory under the reference load (rust-streamer
# "Memory budget"): 800x600 @ 24 fps, two /stream.mjpg clients, for DURATION seconds.
# Run on the Raspberry Pi, once per image, and compare:
#   AUTH_PASSWORD=... rust/scripts/measure-memory.sh kubedge1/picamera
#   AUTH_PASSWORD=... rust/scripts/measure-memory.sh kubedge1/picamera-rs
# Prints the cgroup v2 memory.peak (the container's whole cgroup, including rpicam-vid).
set -euo pipefail

if [[ ${1:-} == -h || ${1:-} == --help || $# -lt 1 ]]; then
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
  echo "Environment: AUTH_PASSWORD (required), DURATION (default 600), PORT (default 8000)."
  exit 0
fi
image=$1
duration=${DURATION:-600}
port=${PORT:-8000}
: "${AUTH_PASSWORD:?AUTH_PASSWORD must be set}"

device_args=()
shopt -s nullglob
for dev in /dev/media* /dev/video* /dev/v4l-subdev* /dev/dma_heap/*; do
  device_args+=(--device "$dev")
done
shopt -u nullglob

name="measure-$(basename "${image%%:*}")-$$"
cid=$(docker run -d --name "$name" "${device_args[@]}" -v /run/udev:/run/udev:ro \
  --group-add video -p "$port:8000" -e AUTH_PASSWORD -e RESOLUTION=800x600 -e FRAMERATE=24 \
  "$image")
trap 'docker rm -f "$cid" >/dev/null' EXIT

for _ in $(seq 60); do
  curl -fs "http://127.0.0.1:$port/healthz" >/dev/null && break
  sleep 1
done
curl -fs "http://127.0.0.1:$port/healthz" >/dev/null || {
  docker logs "$cid" >&2
  echo "error: $image never became healthy" >&2
  exit 1
}

for _ in 1 2; do
  curl -s -u "pi:$AUTH_PASSWORD" --max-time "$duration" -o /dev/null \
    "http://127.0.0.1:$port/stream.mjpg" &
done
wait

peak=$(cat "/sys/fs/cgroup/system.slice/docker-${cid}.scope/memory.peak")
echo "$image memory.peak ${peak} bytes ($((peak / 1024 / 1024)) MiB) after ${duration}s, 2 clients"
