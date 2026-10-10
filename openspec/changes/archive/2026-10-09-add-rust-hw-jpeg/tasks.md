# Tasks

## 1. Prerequisites and device facts

- [x] 1.1 Confirm `add-rust-streamer` is archived (`openspec list --specs` shows `rust-streamer`); via picluster-automation (read-only on kube-node02) confirm a `/dev/video*` whose V4L2 card name is `bcm2835-codec-encode_image` and that it lists `YU12` on OUTPUT and `JPEG` on CAPTURE; record the result in design.md
- [x] 1.2 Via picluster (one approved run) capture 3 frames of `rpicam-vid --codec yuv420 -o -` at 640x480 and 800x600 and report the byte count per frame; fix the stride rule in design.md to what was observed

## 2. Hardware source

- [x] 2.1 Spike: open the encoder through the `v4l` crate (M2M OUTPUT+CAPTURE on one fd) or hand-written ioctls; record the choice in design.md; verify `cargo build` for `aarch64-unknown-linux-gnu` in `rust/Dockerfile` still has no C library dependency
- [x] 2.2 `config.rs`: `ENCODER` (`software|hardware|auto`, default software) and `JPEG_QUALITY` (1–100, optional) with Python-style messages; verify unit tests cover defaults, each valid value and each bad value
- [x] 2.3 `camera.rs`: `Encoder` enum; `args()` switches `--codec mjpeg|yuv420` and adds `--quality` on the software path; move today's read loop behind the software branch unchanged; verify existing unit tests and the conformance suite still pass with `ENCODER` unset
- [x] 2.4 `hwjpeg.rs`: device probe by card name (probe directory overridable for tests), format setup, MMAP buffers, per-frame encode on a blocking thread with newest-wins handoff, `JPEG_QUALITY` control, 1 s timeout → restart, repeated failure → error; verify unit tests for the probe and the frame-size/stride arithmetic
- [x] 2.5 Selection in `main.rs`: `auto` probe and log `encoder=…`; `hardware` without device → exit 1 with the spec's message; verify with conformance cases using an empty probe directory

## 3. Tests

- [x] 3.1 Fake `rpicam-vid` emits I420 frames for `--codec yuv420` and records `--quality`; conformance cases: default argv unchanged, `JPEG_QUALITY=85` reaches the software argv, `ENCODER=auto` without encoder streams via software, `ENCODER=hardware` without encoder exits non-zero, bad `ENCODER`/`JPEG_QUALITY` exit 2; verify `make check` passes with no skips under `REQUIRE_RUST=1`

## 4. Chart and docs

- [x] 4.1 `charts/picamera-rs`: optional `camera.encoder` and `camera.jpegQuality` values → `ENCODER` / `JPEG_QUALITY` env only when set; verify chart tests (values interchangeability with `charts/picamera` still holds because the keys are unset by default)
- [x] 4.2 README § Configuration (Rust-only rows), `architecture.md` Rust section (frame-source seam, hardware path); verify `bin/check-doc-set.py` passes

## 5. Integration

- [x] 5.1 Open the PR; verify `ci.yml`, `rust.yml`, `image.yml` green
- [x] 5.2 On device via picluster (operator-approved): `ENCODER=software|hardware|auto` at 640x480@15 and 800x600@24 — frames in 5 s, typical frame size, CPU %, memory.peak, plus `JPEG_QUALITY=85` on both encoders; record the numbers in design.md and decide the chart default — run at 800x600@24, `JPEG_QUALITY=50` only (640x480 and quality 85 dropped as not decision-relevant); results and decision in design.md
