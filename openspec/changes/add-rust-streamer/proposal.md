# Proposal

## Why

The Python streamer, once on `picamera2`, carries numpy, PyAV, Pillow and the Python runtime into every camera pod — a large resident footprint on Raspberry Pi nodes that have 512 MiB–1 GiB to share with the kubelet and other workloads. A Rust implementation of the same HTTP contract, serving frames from Raspberry Pi's own `rpicam-vid`, lets memory-constrained nodes run the camera at a fraction of the cost while the Python version stays available.

## What Changes

- New Rust service `picamera-rs` under `rust/` that implements the same contract as the Python service (`camera-streaming`): same environment variables, Basic auth, routes, `/healthz`, MJPEG framing and shutdown behaviour, plus an `--example` mode equivalent to `docker-picamera-example`.
- Frames come from a supervised `rpicam-vid` child process emitting MJPEG on stdout; the service exits non-zero if the child dies, so the container restarts.
- Held to a memory budget: peak container memory at most 50% of the Python image's under the same load on the same Pi.
- New image `kubedge/picamera-rs` (Docker Hub, `linux/arm64`), cross-compiled natively — no emulated Rust build.
- New Helm chart `charts/picamera-rs`, separate from `charts/picamera`, with a default memory limit.
- A black-box HTTP conformance suite shared by both implementations, run in CI against each with a fake camera.
- CI: Rust format, lint and test jobs; the image workflow builds and publishes both images.

## Capabilities

### New Capabilities
- `rust-streamer`: the Rust implementation's conformance to `camera-streaming`, its camera-process supervision, and its memory budget.
- `rust-container-image`: the `kubedge/picamera-rs` image and how CI builds and publishes it.
- `rust-helm-deployment`: the `charts/picamera-rs` Helm chart.

### Modified Capabilities
<!-- none in openspec/specs/ yet. This change builds on capabilities introduced by
     modernize-python-and-docker (camera-streaming, container-image, helm-deployment),
     which must be archived first; their requirements are referenced, not changed. -->

## Impact

- **Ordering**: depends on `modernize-python-and-docker` being implemented and archived first — it references `camera-streaming`, reuses that change's Dockerfile pattern, workflow and chart, and needs the Python image on device for the memory comparison.
- **Code**: new `rust/` Cargo project; `tests/test_server.py` from the first change is split into a reusable black-box suite under `tests/conformance/`.
- **Container**: new `rust/Dockerfile`; `.github/workflows/image.yml` builds two images; new `.github/workflows/rust.yml`.
- **Deployment**: new `charts/picamera-rs/`. Kubernetes users pick an implementation by picking a chart.
- **Registry**: Docker Hub repository `kubedge/picamera-rs`, pushed with the existing `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` (the token needs write access to it).
- **Hardware**: the memory budget and camera path are verified on a Raspberry Pi; CI verifies conformance with a fake `rpicam-vid`.
