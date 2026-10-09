# Proposal

## Why

The image cannot be built or run on any current Raspberry Pi: its base image (`resin/raspberry-pi-python`) is gone, the legacy `picamera` library only drives the MMAL/VideoCore stack (`/dev/vchiq`) that Raspberry Pi OS dropped for libcamera, CI still points at Travis, and the Helm chart deploys an unrelated image with an LED config. Separately, the Python code predates the alemax tooling now in the repo: no `pyproject.toml`, no tests, nothing CI's python jobs can run, and a default password baked into the image.

## What Changes

- **BREAKING** — Camera stack moves from legacy `picamera` (MMAL) to `picamera2` / libcamera. The container no longer uses `/dev/vchiq`; it needs the libcamera media devices instead.
- **BREAKING** — No default credentials. `AUTH_PASSWORD` must be set; the service refuses to start without it. The image and `run.sh` no longer carry `AUTH_PASSWORD=picamera`.
- **BREAKING** — `ROTATE` accepts only `0` and `180`; libcamera transforms cannot rotate by 90/270. Any other value is a startup error instead of a silent no-op.
- **BREAKING** — Image is `linux/arm64` only (64-bit Raspberry Pi OS). 32-bit (`arm32v7`) is dropped.
- Python code becomes a package (`src/docker_picamera/`) with `pyproject.toml` + `uv.lock`, console scripts `docker-picamera` (authenticated stream) and `docker-picamera-example` (the ported `example.py`: unauthenticated, fixed 640×480), and is ruff-, mypy- and pytest-clean so CI's python jobs run and pass. Top-level `web_streaming.py` and `example.py` move into the package.
- New unauthenticated `GET /healthz` for container and Kubernetes probes.
- Dockerfile rebuilt: Debian trixie slim + the Raspberry Pi apt archive for `python3-picamera2`, app in a venv that sees the system packages, non-root user, `HEALTHCHECK`, no secrets in `ENV`.
- `.travis.yml` is removed; a GitHub Actions workflow lints the Dockerfile, builds `linux/arm64` on every PR and pushes `kubedge/picamera` to Docker Hub from `main` and version tags.
- Helm chart `charts/kubesim-picamera-arm32v7` becomes `charts/picamera`: image `kubedge/picamera`, arm64 node selection, credentials from a Kubernetes Secret, `/healthz` probes, libcamera devices; the LED ConfigMap and external health sidecar are removed.
- `build.sh` / `run.sh` updated for buildx/arm64 and libcamera devices; README, `CLAUDE.md` § 1–5 placeholders and a new `architecture.md` describe the result.

## Capabilities

### New Capabilities
- `camera-streaming`: the HTTP MJPEG streaming service — configuration from the environment, Basic authentication, routes (index, stream, health), camera control, and the two entry points.
- `container-image`: the published `kubedge/picamera` image — platform, base, runtime user, health check, credential handling, and how CI builds and publishes it.
- `helm-deployment`: the `charts/picamera` Helm chart — what it deploys, where it schedules, how it receives credentials and devices, and how it probes health.

### Modified Capabilities
<!-- none: openspec/specs/ is empty -->

## Impact

- **Code**: `web_streaming.py`, `example.py` → `src/docker_picamera/`; new `tests/`, `pyproject.toml`, `uv.lock`.
- **Container**: `Dockerfile`, `build.sh`, `run.sh` rewritten; `.travis.yml` removed; new `.github/workflows/image.yml`.
- **Deployment**: `charts/kubesim-picamera-arm32v7/` renamed and rewritten as `charts/picamera/`. Existing releases of the old chart must be uninstalled and reinstalled with a Secret.
- **CI**: adding `pyproject.toml` switches on `ci.yml`'s python jobs (`ruff`, `mypy src`, `pytest`). Meta-owned trees (`bin/`, `plugins/`, `.claude/`, `.agents/`) do not pass ruff today and are excluded from this project's ruff config.
- **Secrets**: new repo secrets `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` for the publish job; `AUTH_PASSWORD` documented in `.env.example`.
- **Hardware**: needs a 64-bit Raspberry Pi OS host with a libcamera-supported camera. Nothing here can be verified on a camera from CI — the camera path is covered by a fake in tests and a manual on-device check.
