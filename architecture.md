# Architecture

How docker-picamera is put together, for whoever is about to change it. What it does
and how to run it: [`README.md`](README.md). What it must do: `openspec/specs/`.

## Shape

One process: a camera writes JPEG frames into a shared buffer; a threaded HTTP server
reads the newest frame for each client.

    picamera2 encoder ──write()──▶ FrameBuffer ◀──wait_next()── one thread per HTTP client
                                        ▲
                                     age() ◀── /healthz

## Modules — `src/docker_picamera/`

| module | role |
| --- | --- |
| `config.py` | `load_config(environ)` → frozen `Config`; `ConfigError` messages start with the variable name. Pure. `EXAMPLE_CONFIG` is the example's fixed settings. |
| `frames.py` | `FrameBuffer`: newest frame, sequence number, timestamp, under one `Condition`. Readers wait for a sequence newer than the last they sent, so none misses a wake-up and a slow reader skips frames rather than queueing them. `close()` ends every wait. |
| `server.py` | `build_handler(Site)` returns a request-handler class closed over its `Site` (frames, page, expected `Authorization` value or `None`). Routes, Basic auth (constant-time compare), MJPEG multipart, `/healthz`. No module globals. |
| `camera.py` | `open_camera(config, frames)`: the **only** module that imports picamera2/libcamera, and only inside the function. Hardware `MJPEGEncoder`, falling back to software `JpegEncoder` where the Pi has no JPEG block. Rotation 180° = both flips toggled. |
| `cli.py` | `main` (`docker-picamera`) and `example_main` (`docker-picamera-example`); `serve()` wires camera → buffer → server, turns SIGTERM/SIGINT into `server.shutdown()` from a helper thread, and returns the exit status. Config errors → stderr, exit 2. |

## Invariants

- **Camera code stays in `camera.py`.** Everything else imports and tests without
  picamera2, which exists only on the device (Raspberry Pi apt packages). A new import of
  it elsewhere breaks the tests, ruff, mypy and CI on every non-Pi host.
- **No credentials in the image or the chart.** `AUTH_PASSWORD` has no default anywhere;
  the image's `ENV` carries only non-secret defaults; the chart reads a Secret by name.
- **No runtime dependency from PyPI.** `dependencies = []`; the image installs the wheel
  with `--no-deps` into a venv that sees apt's packages via `--system-site-packages`.
- **One camera owner.** One process per camera; the chart runs one replica with the
  `Recreate` strategy.

## Image — `Dockerfile`

Two stages. `builder` (uv on the build host's own platform) builds the pure-Python wheel
natively; the `linux/arm64` runtime is `debian:trixie-slim` plus the Raspberry Pi archive
for `python3-picamera2`, installed without recommends. The archive's signing key is
vendored as `docker/raspberrypi-archive-keyring.pgp`, taken from the archive's own keyring
package: the downloadable copy has SHA-1 self-signatures that trixie's apt rejects. Runs
as `picamera` (uid 10001, group `video`), health-checked on `/healthz`.

## Chart — `charts/picamera`

Deployment (privileged, because Kubernetes grants host device nodes only to privileged
containers; host `/dev` and read-only `/run/udev` for libcamera), NodePort Service, optional
Ingress. `tests/test_chart.py` renders it and checks it against the `helm-deployment` spec.
Dashboard discovery is pod-template metadata only: the label `kubedge.device.name=camera`
and the annotations `kubedge.io/stream-url` / `kubedge.io/external-url`, never the Deployment
selector (immutable, so adding to it would break `helm upgrade`). The label key is the one
kubedge-dashboard already selects on; renaming it is a change in both repos.

## CI

`ci.yml` is delivered by claude-meta (do not edit it here); it runs ruff, mypy and pytest
once `pyproject.toml` exists. `image.yml` is this project's: hadolint, chart tests and the
arm64 build. It never logs in or pushes; images are pushed by hand (`./build.sh --push`). Ruff
excludes the meta-owned trees (`bin/`, `plugins/`, `.claude/`, `.agents/`).

## Rust implementation — `rust/`

`picamera-rs` serves the same contract (`openspec/specs/camera-streaming`) with frames from
Raspberry Pi's `rpicam-vid` instead of picamera2. The executable is overridable with
`RPICAM_VID`, which is how the tests substitute a fake camera.

| module | role |
| --- | --- |
| `config.rs` | same variables, defaults and error messages as `config.py` (identical text, checked by the conformance suite) |
| `mjpeg.rs` | structural JPEG splitter: walks marker segments to SOS, scans entropy data honouring `FF 00` stuffing and `FF D0–D7` restarts; emits only complete SOI..EOI frames; bounded buffer (max(1 MiB, 4× largest frame)) |
| `camera.rs` | spawns `rpicam-vid -t 0 -n --codec mjpeg … -o -` (`kill_on_drop`), forwards its stderr to the log, publishes each frame into a `watch` channel; returns the child's exit status |
| `server.rs` / `auth.rs` | axum fallback router reproducing `server.py` routes, headers and bodies; constant-time Basic auth; the stream is an `unfold` over the `watch` receiver |
| `main.rs` | current-thread tokio runtime; `--example`, `--healthcheck`; SIGTERM/SIGINT or camera exit → stop the child, end the streams, stop the server |

Invariants, in addition to the Python ones:
- **One runtime thread, shared frames.** Every client holds the same reference-counted
  `Bytes`; a slow client skips frames. Memory does not grow with clients or with a
  corrupt camera stream.
- **The camera process dies with the service, and vice versa.** A child exit is a
  non-zero exit (the container restarts); shutdown kills the child.
- **The conformance suite is the contract.** `tests/conformance/` runs every
  camera-streaming case against both implementations (`REQUIRE_RUST=1` in CI). A
  behaviour tested only on one side is a review flag.

Image `rust/Dockerfile`: `xx-cargo` cross-compiles on the build host (no emulated Rust
build); the runtime is `debian:trixie-slim` plus `rpicam-apps-core` from the Raspberry Pi
archive (same vendored key). Chart `charts/picamera-rs` is a copy of `charts/picamera` with
its own name, image and default memory request/limit; `tests/test_chart_rs.py` checks that
the two render identically apart from those.
