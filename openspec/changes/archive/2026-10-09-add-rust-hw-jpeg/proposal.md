# Proposal

## Why

On kube-node02 (Pi 3, 2026-10-09) picamera-rs used 21% of the Python image's memory but more CPU (51.5% vs 42.9% of a core at 800x600@24), and produced ~7 KB frames against Python's ~18 KB. The cause is the encoder: `rpicam-vid --codec mjpeg` encodes JPEG in software with libjpeg at quality 50, while picamera2 uses the Pi's hardware JPEG block. The Pi 3/4 GPU exposes that block through the `bcm2835-codec` V4L2 memory-to-memory driver, and the node has it. The operator wants the hardware path available in Rust without giving up the current one.

## What Changes

- New optional setting `ENCODER`: `software` (default, today's behaviour unchanged), `hardware`, or `auto`.
- `hardware`: `rpicam-vid` still captures (sensor, ISP, tuning) but emits raw YUV420 frames; picamera-rs encodes each one to JPEG on the hardware encoder found by name (`bcm2835-codec-encode_image`) and publishes it through the same frame fan-out.
- `auto`: hardware when that encoder is present, software otherwise (e.g. Pi 5), with the choice logged.
- New optional setting `JPEG_QUALITY` (1–100), applied to whichever encoder runs. Unset keeps each encoder's own default.
- `hardware` requested but no encoder found is a startup error, not a silent fallback.
- The software path — `rpicam-vid --codec mjpeg` plus the structural splitter — is kept intact and stays the default.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `rust-streamer`: adds encoder selection, hardware JPEG encoding and JPEG quality. The capability is introduced by `add-rust-streamer`, which must be archived first; this change only adds requirements.

## Impact

- **Code**: `rust/src/camera.rs` splits into a frame-source interface with the existing software source and a new hardware source (`rust/src/hwjpeg.rs`, V4L2 ioctls via a crate such as `v4l`); `config.rs` gains `ENCODER` and `JPEG_QUALITY`.
- **Image**: unchanged packages; the hardware encoder node is already among the `/dev/video*` devices `run.sh` and the chart pass.
- **Python**: unchanged. `JPEG_QUALITY` and `ENCODER` are Rust-only settings.
- **Tests**: config, selection and fallback, and the raw-frame plumbing with a fake `rpicam-vid` in CI; the hardware encoder itself only on a Pi (kube-node02 via picluster-automation).
- **Charts**: `charts/picamera-rs` gains optional `camera.encoder` / `camera.jpegQuality` values. `charts/picamera` ignores them.
