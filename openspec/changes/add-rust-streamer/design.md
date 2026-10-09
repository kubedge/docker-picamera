# Design

## Context

Builds on `modernize-python-and-docker` (must be archived first): the `camera-streaming` contract, the trixie + Raspberry Pi archive Dockerfile pattern, `.github/workflows/image.yml`, `run.sh` device handling, and `charts/picamera` all exist when this starts. Facts checked 2026-10-09: `rpicam-vid` ships in `rpicam-apps-core` 1.13.0 (Raspberry Pi archive, trixie, arm64; ~1 MiB, pulls `libcamera0.7` and `librpicam-app1`, no Python stack); `tonistiigi/xx` v1.9.0; Rust stable 1.99.0. Operator decisions: wrap `rpicam-vid`, separate Docker Hub repo `kubedge1/picamera-rs`, ≤50% of Python's measured peak, separate chart.

## Goals / Non-Goals

**Goals:**
- Byte-compatible HTTP behaviour with the Python service, proven by one shared test suite.
- Small steady-state memory: no per-client frame copies, one async runtime thread, bounded buffers.
- No emulated Rust compile in CI.

**Non-Goals:**
- Talking to libcamera directly, hardware JPEG tuning, or encoding in Rust — `rpicam-vid` owns capture and encoding.
- Replacing the Python implementation; both are maintained and released together.
- Any HTTP feature the Python service lacks.

## Decisions

### Layout: `rust/` Cargo project, binary `picamera-rs`
`rust/Cargo.toml`, `rust/rust-toolchain.toml` (pinned stable), `rust/src/{main,config,auth,mjpeg,camera,server}.rs`. Kept beside the Python package rather than in a second repo so one PR changes the contract, both implementations and the shared tests together. `Cargo.lock` committed (binary crate).

### Runtime: tokio current-thread + axum
One OS thread for all I/O (`#[tokio::main(flavor = "current_thread")]`) — the multi-thread runtime's per-core workers buy nothing at these frame rates and cost stacks and allocator arenas. axum/hyper for HTTP: mature streaming bodies and header handling, avoiding hand-written HTTP parsing. Alternative `tiny_http` + thread per client: smaller dependency tree but one stack per stream client and no async child-process I/O. Release profile: `opt-level = "s"`, `lto = true`, `codegen-units = 1`, `panic = "abort"`, `strip = true`.

### Frame fan-out: `tokio::sync::watch<Bytes>`
The camera task publishes each frame as a `Bytes` into a `watch` channel; each stream client holds a receiver and awaits `changed()`. `Bytes` is reference-counted, so N clients share one allocation per frame; a slow client skips frames instead of buffering them — the same "latest frame wins" semantics as the Python `Condition`. `/healthz` reads the timestamp stored with the frame.

### MJPEG splitting
`rpicam-vid` writes concatenated JPEGs. The splitter walks JPEG structure rather than searching for `FF D9`: SOI, then length-prefixed segments up to SOS, then entropy-coded data scanned for `FF` followed by a byte that is not `00` or `D0–D7`; that marker must be EOI. Bytes before an SOI are dropped and counted. The read buffer is capped (4× the largest frame seen, floor 1 MiB); overflow resets the splitter. This satisfies "Malformed camera output" and keeps memory bounded if the stream is corrupt.

### Camera process
`tokio::process::Command` runs `rpicam-vid -t 0 -n --codec mjpeg --width W --height H --framerate F [--hflip] [--vflip] [--rotation 180] -o -` with `kill_on_drop(true)`, stdout piped, stderr forwarded to the log. The executable is `rpicam-vid` on `PATH`, overridable by `RPICAM_VID` — the seam that lets tests substitute a fake. A child exit ends the camera task with an error and the process exits non-zero. On `SIGTERM`/`SIGINT`: stop accepting, send `SIGTERM` to the child, wait briefly, exit 0.

Why `rpicam-vid` rather than `libcamera-rs`: the Rust binary has no C dependencies, so it cross-compiles natively; `rpicam-vid` already handles sensor setup, ISP tuning and the JPEG encoder (hardware or software) per Pi model.

### Auth and config
`config.rs` mirrors `load_config`: same variables, defaults and messages (config errors print `error: <VARIABLE>: <reason>` to stderr and exit 2, matching the Python CLI). Expected `Authorization` value precomputed; compared with `subtle::ConstantTimeEq`. Messages and status codes are checked by the conformance suite, not by convention.

### Shared conformance suite
`tests/conformance/` holds black-box pytest cases parameterised by a `base_url` fixture and a fake-frame source. Two fixtures provide it:
- `python_impl`: the in-process Python server fed by a fake producer (what `tests/test_server.py` does today, moved here).
- `rust_impl`: spawns `rust/target/debug/picamera-rs` with `RPICAM_VID=tests/fixtures/fake-rpicam-vid` — a small Python script writing fixture JPEGs at the requested frame rate, recording its argv so tests can assert flags (`--rotation 180`, `--hflip`).
Cases for configuration errors run the binaries as subprocesses. The `rust_impl` fixture skips when the binary is not built, so `uv run pytest` still runs anywhere; the Rust CI job builds it first, so nothing is skipped there.

### Image: `rust/Dockerfile`
1. `builder` — `FROM --platform=$BUILDPLATFORM rust:1.99-slim-trixie` with `tonistiigi/xx:1.9.0` copied in; `xx-cargo build --release --target-dir /out` for `$TARGETPLATFORM` (`aarch64-unknown-linux-gnu`); `xx-verify` the binary. Native compile, cross-link — no QEMU for Rust.
2. `runtime` — `debian:trixie-slim` (arm64), Raspberry Pi archive as in the Python image, `apt-get install --no-install-recommends rpicam-apps-core`, user `picamera` (uid 10001, group `video`), binary at `/usr/local/bin/picamera-rs`, `ENV RESOLUTION=800x600 FRAMERATE=24`, `EXPOSE 8000`, `HEALTHCHECK` via a `picamera-rs --healthcheck` flag that GETs `http://127.0.0.1:8000/healthz` (the runtime image has no curl or Python), `USER picamera`, `ENTRYPOINT ["picamera-rs"]`.
The keyring/source snippet is duplicated from the Python Dockerfile; extracting it into a shared base image was rejected as a third image to publish for six lines.

### CI
- `.github/workflows/rust.yml` (project-owned; `ci.yml` is meta class M): `cargo fmt --check`, `cargo clippy --all-targets -- -D warnings`, `cargo test`, then `cargo build` and `uv run pytest tests/conformance` so the Rust fixture runs. Triggered on paths `rust/**`, `tests/conformance/**`, the workflow itself.
- `.github/workflows/image.yml` gains a matrix `{image: kubedge1/picamera, context: ., file: Dockerfile}` / `{image: kubedge1/picamera-rs, context: ., file: rust/Dockerfile}`; hadolint runs per Dockerfile; still build-only, no login, no push. A `rust/build.sh` mirrors `build.sh` (`--push` after a manual `docker login`).

### Chart: `charts/picamera-rs`
Copied from `charts/picamera` (operator chose separate charts) with names, image and defaults changed; `resources` defaults set from the on-device measurement (initial placeholder `requests.memory: 32Mi`, `limits.memory: 96Mi`, replaced by measured peak × 1.5 before release). A CI step renders a `charts/picamera` values file with both charts and diffs the results to enforce "Values are interchangeable".

### Memory measurement
On device: run each image for 10 minutes at 800×600@24 with two `curl` stream clients, read peak from cgroup v2 `memory.peak` of the container (`/sys/fs/cgroup/system.slice/docker-<id>.scope/memory.peak`), which includes the `rpicam-vid` child. A script `rust/scripts/measure-memory.sh` automates this and prints both peaks and the ratio. CI adds a regression guard only: the Rust binary's max RSS while serving the fake camera to two clients for 30 s stays under a threshold set from the first measurement.

## Risks / Trade-offs

- [`rpicam-vid` CLI flags change between releases] → flags are built in one function with a unit test of the argv; the fake records argv; the image pins the suite, and a flag change surfaces in the on-device check.
- [`rpicam-vid`'s software JPEG on a Pi 5 dominates memory/CPU] → it is inside the container's cgroup and counted in the budget; if the 50% target fails on a Pi 5, the fallback is a lower default `FRAMERATE` for the Rust chart, decided with measurements in hand.
- [Two processes in one container] → the service owns the child (`kill_on_drop`, signal forwarding); there is no supervisor to leave an orphan.
- [Both charts on one node fight over one camera] → libcamera allows one owner per camera; coexistence is for clusters with different camera nodes or migration, and the charts' `nodeSelector` can be split by a node label. Documented in the chart README.
- [Contract drift between implementations] → the shared conformance suite is the contract's executable form; a Python-only test outside it is a review flag.

## Migration Plan

1. Ship after `modernize-python-and-docker` is released and measured.
2. Push by hand with an account that can push `kubedge1/picamera-rs` (create the repository if the org disallows create-on-push).
3. Per node: `helm uninstall picamera` then `helm install picamera-rs charts/picamera-rs -f <same values>`; rollback is the reverse — same Secret, same values.

## Open Questions

- Final default memory request/limit for `charts/picamera-rs` — filled from the first on-device measurement; does not change specs or tasks.
