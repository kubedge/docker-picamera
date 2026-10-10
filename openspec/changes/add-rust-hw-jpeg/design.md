# Design

## Context

`rust/src/camera.rs` today: `spawn()` starts `rpicam-vid -t 0 -n --codec mjpeg … -o -`, `run()` reads stdout through the structural splitter (`mjpeg.rs`) and publishes each frame into `watch<Latest>`; `main.rs` supervises it (child exit → exit 1; SIGTERM → abort, `kill_on_drop`). kube-node02 (Pi 3, Ubuntu 24.04, kernel 6.8) has `bcm2835_codec` loaded with nodes `/dev/video10–12, 18, 31`; on upstream kernels `video31` is `bcm2835-codec-encode_image`, a V4L2 M2M JPEG encoder. Measured 2026-10-09: RS 51.5% CPU / ~7 KB frames vs PY 42.9% / ~18 KB at 800x600@24.

## Goals / Non-Goals

**Goals:** a second, opt-in frame source using the hardware JPEG encoder; zero behaviour change when `ENCODER` is unset; the HTTP contract, supervision and fan-out untouched.
**Non-Goals:** dropping `rpicam-vid` (it still does sensor setup, ISP and tuning); H.264; Pi 5 hardware (it has none); changing the Python implementation.

## Decisions

### A frame-source seam inside `camera.rs`
```
enum Encoder { Software, Hardware }
fn args(config, encoder) -> Vec<String>     // --codec mjpeg | --codec yuv420, plus --quality
async fn run(child, encoder, tx)            // dispatches to the source below
  software: read stdout → Splitter → publish            (today's code, moved, unchanged)
  hardware: read stdout in exact frame-size chunks → HwJpeg::encode → publish
```
Both publish into the same `watch<Latest>`, so server, health and shutdown do not change. Alternative — a trait object per source — buys nothing for two variants.

### Raw frames from `rpicam-vid --codec yuv420`
Each frame is `width*height*3/2` bytes (I420). `rpicam-vid` writes the buffer row by row; when `width` is not a multiple of the ISP's stride alignment the rows carry padding. The hardware path reads `stride*height*3/2` with `stride = align_up(width, 64)` and hands the encoder that stride (`bytesperline`), so no copy is needed to strip padding. **To verify on device first** (task 1.2): the exact frame size `rpicam-vid` emits at 640x480 and 800x600.

### `hwjpeg.rs`: V4L2 M2M encode
- **Find the device by name**, not number: scan `/dev/video*`, `VIDIOC_QUERYCAP`, pick `card == "bcm2835-codec-encode_image"` (M2M, streaming). `ENCODER=auto` uses this probe; `hardware` fails startup if it finds nothing.
- **Formats:** OUTPUT queue (raw in) `V4L2_PIX_FMT_YUV420`, width/height/bytesperline from config; CAPTURE queue (JPEG out) `V4L2_PIX_FMT_JPEG`. `JPEG_QUALITY` → `V4L2_CID_JPEG_COMPRESSION_QUALITY`.
- **Buffers:** MMAP, 2 per queue; per frame: copy raw into the OUTPUT buffer, `QBUF` both, `DQBUF` CAPTURE, copy `bytesused` into a `Bytes`, publish. Synchronous per frame on a blocking thread (`spawn_blocking` loop fed by a bounded channel of 1, newest wins) so the async runtime stays single-threaded and a slow encoder drops frames instead of queueing.
- **Crate:** `v4l` (pure Rust over `ioctl`) if it covers M2M OUTPUT+CAPTURE on one fd; otherwise hand-written ioctls with `nix`. Decided in task 2.1 by a spike; either keeps the binary free of C libraries, so the cross-compile is unchanged.

### Settings
`ENCODER` (`software` default) and `JPEG_QUALITY` (unset → `rpicam-vid`'s default 50 for software, the driver's default for hardware) parsed in `config.rs` with the same error style. `--quality N` is passed to `rpicam-vid` only on the software path.

### Testing
- CI: config cases; argv cases (`--codec yuv420` vs `mjpeg`, `--quality`); selection (`auto` with no encoder → software, `hardware` with none → exit non-zero), via an injectable device-probe directory (`PICAMERA_V4L2_DIR`, test-only, defaults to `/dev`); raw plumbing — the fake `rpicam-vid` gains `--codec yuv420` output, and a fake encoder (behind a cargo feature or test seam) proves frames flow and the contract holds.
- Device: kube-node02 via picluster-automation — `ENCODER=hardware` and `auto`, both resolutions, frames per 5 s, frame size, CPU %, memory.peak; compared with `software` and with Python.

## Risks / Trade-offs

- [`rpicam-vid` yuv420 padding/stride differs from the assumption] → verified on device before the hardware source is written (task 1.2).
- [Ubuntu's `bcm2835-codec` lacks `encode_image`, or its name differs] → `auto` falls back; `hardware` fails loudly; the device check (task 1.1) settles it before coding.
- [Pipe copy of raw frames: 720 KB/frame, ~17 MB/s at 800x600@24] → acceptable on Pi 3/4; measured on device. DMA-buf sharing with `rpicam-vid` would avoid it but needs libcamera in-process — out of scope.
- [Encoder busy or wedged] → a frame that doesn't come back within 1 s is logged and the source restarts the encoder session; repeated failure exits non-zero like a dead camera process.

## Migration Plan

Opt-in: deployments change nothing until they set `ENCODER`. Recommended rollout: `ENCODER=auto` on Pi 3/4 nodes after the on-device comparison; the chart default stays `software` until then.

## Implementation notes (2026-10-10)

- **Ioctls by hand** (task 2.1): the encoder is multi-planar (as picamera2's V4L2 encoder); the `v4l` crate's M2M multi-planar support is thin, so `hwjpeg.rs` declares the seven structures and eight ioctls it needs over `libc`, with compile-time `size_of` checks against the 64-bit kernel layouts. Still no C library; cross-compile unchanged. Linux-only; a stub elsewhere.
- **Probe via sysfs name** (`/sys/class/video4linux/videoN/name`), overridable with `PICAMERA_V4L2_SYSFS` for tests, rather than `VIDIOC_QUERYCAP` on every node.
- **No in-process restart on encoder timeout**: a 1 s timeout (or any encode error) ends the pipeline with an error and the service exits 1, like a dead camera process; the container restarts. Simpler than the planned session restart; same observable outcome for an orchestrator.
- **Device facts (kube-node02, Pi 3, OV5647, 2026-10-10)**: the encoder is `/dev/video31` (`bcm2835-codec-encode_image`, `root:video`, so the container needs gid 44). `rpicam-vid --codec yuv420` pads luma rows to 64 bytes: 640x480 → 460800 bytes/frame (unpadded), 800x600 → 748800 = Y 832×600 + U/V 416×300 each. 0.4.1 assumed unpadded and would have read 800x600 frames out of step.
- **Stride (0.4.2)**: frames are read with luma stride `align_up(w,64)`, chroma half, and each is repacked into the layout the driver returns from `VIDIOC_S_FMT` (`bytesperline`, rows = `sizeimage / (1.5·bytesperline)`), so a driver that rounds stride or height differently still gets aligned planes. Formats are confirmed by a streaming hardware run (task 5.2), not `v4l2-ctl`, which the image does not ship.
- **Encoder error at camera EOF** is now returned, not swallowed (surfaced by a Linux test run during the stride fix).
- **`auto` falls back also when the encoder is present but cannot be opened**, logged as `hardware JPEG encoder unusable (…)`; `hardware` exits 1 in both cases.

## Open Questions

- Whether `auto` should become the default once measured — a later, separate decision.
