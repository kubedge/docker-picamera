#!/usr/bin/env bash
# Run the stream on a Raspberry Pi with 64-bit Raspberry Pi OS and a libcamera camera.
# AUTH_PASSWORD must be set in the caller's environment; it is passed through by name,
# so the value never appears on a command line. AUTH_USERNAME, RESOLUTION, FRAMERATE,
# ROTATE, HFLIP and VFLIP are passed through the same way when set.
set -euo pipefail

if [[ -z "${AUTH_PASSWORD:-}" ]]; then
  echo "error: AUTH_PASSWORD must be set, e.g. AUTH_PASSWORD=... $0" >&2
  exit 2
fi

env_args=(-e AUTH_PASSWORD)
for var in AUTH_USERNAME RESOLUTION FRAMERATE ROTATE HFLIP VFLIP; do
  if [[ -n "${!var:-}" ]]; then
    env_args+=(-e "$var")
  fi
done

# libcamera needs the media, video, sub-device and DMA-heap nodes; their numbering
# varies by Pi model and kernel, so pass whatever exists.
device_args=()
shopt -s nullglob
for dev in /dev/media* /dev/video* /dev/v4l-subdev* /dev/dma_heap/*; do
  device_args+=(--device "$dev")
done
shopt -u nullglob
if [[ ${#device_args[@]} -eq 0 ]]; then
  echo "error: no camera device nodes under /dev — is the camera connected and enabled?" >&2
  exit 1
fi

docker run -d --restart=always --name picamera \
  "${device_args[@]}" \
  -v /run/udev:/run/udev:ro \
  --group-add video \
  -p 8000:8000 \
  "${env_args[@]}" \
  kubedge/picamera
