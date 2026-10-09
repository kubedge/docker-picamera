# Design

## Context

Today: two top-level scripts (`web_streaming.py`, `example.py`) that share ~70 copied lines, run under the legacy `picamera` MMAL binding, with `os.environ` parsed at import time and module-level globals (`output`) reached from the request handler. No packaging, no tests. The alemax CI (`ci.yml`) switches its python jobs on when `pyproject.toml` exists and then runs `uv sync --locked`, `ruff check .`, `ruff format --check .`, `mypy src` and `pytest` — so the moment this change adds `pyproject.toml`, all five must pass.

Constraints that shape the approach:
- `picamera2` is not usable from PyPI alone: it needs the `python3-libcamera` bindings, which only ship as Debian packages from the Raspberry Pi archive (`archive.raspberrypi.com/debian`, suite `trixie`, `python3-picamera2` 0.3.37 for arm64 — checked 2026-10-09). Dev machines (macOS) and CI runners (x86_64) have neither.
- Meta-owned trees (`bin/`, `plugins/`, `.claude/`, `.agents/`) fail ruff today (60 findings) and arrive by cherry-pick; editing them here would conflict with the next broadcast.
- No local Docker daemon or camera: the image is verified by CI's arm64 build; the camera path only on a device.

## Goals / Non-Goals

**Goals:**
- One shared streaming core used by both entry points; camera code is the only part that imports `picamera2`.
- Everything except the camera adapter testable on any host with stdlib + pytest.
- Image buildable from a cold cache in CI under QEMU in reasonable time.

**Non-Goals:**
- No new features beyond `/healthz` (no TLS, no multi-camera, no PORT variable, no web UI changes).
- No `armv7` image, no Pi 5 vs Pi 4 tuning beyond encoder fallback.
- No changes to meta-owned files; their lint failures go to `.local/feedback.md`.

## Decisions

### Package layout: `src/docker_picamera/`

| module | role |
| --- | --- |
| `config.py` | `Config` frozen dataclass + `load_config(environ)`; raises `ConfigError` naming variable and value. Pure, no I/O. |
| `frames.py` | `FrameBuffer`: latest JPEG + `threading.Condition` + timestamp of last frame; `write(bytes)` is the camera sink, `wait_next()` the reader side, `age()` feeds `/healthz`. |
| `server.py` | `build_handler(frames, page, credentials | None)` returns a `BaseHTTPRequestHandler` subclass closed over its dependencies; `StreamingServer` (`ThreadingHTTPServer`, daemon threads, address reuse). No globals. |
| `camera.py` | `open_camera(config, sink)` context manager. Imports `picamera2` inside the function. The only module mypy is told to treat as untyped-import. |
| `cli.py` | `main()` (authenticated) and `example_main()` (no auth, 640×480@24); signal handling; logging setup. |

Why: the handler-factory removes the module-global `output` that made the old code untestable, and keeping `picamera2` behind one lazily-imported function lets tests, ruff and mypy run without camera libraries. Alternative — a `Camera` protocol with dependency injection everywhere — is more ceremony than two entry points need; the context-manager seam is enough for tests to substitute a fake that pushes JPEG bytes into `FrameBuffer`.

`FrameBuffer.write` receives whole frames: `picamera2`'s `FileOutput` calls `write` once per encoded JPEG, so the legacy "split on `\xff\xd8`" buffering is dropped.

### Encoder: hardware MJPEG, falling back to software JPEG
`camera.py` tries `MJPEGEncoder` (V4L2 hardware, Pi 4 and earlier) and falls back to `JpegEncoder` (software, `simplejpeg`) when it is unavailable — the Pi 5 has no hardware JPEG block. Alternative — always software — costs CPU on the Pi 3/Zero 2 class the project historically targeted. The chosen encoder is logged at startup.

### Rotation and flips via libcamera `Transform`
`Transform(hflip=…, vflip=…)`, with `ROTATE=180` composed as both flips toggled. libcamera has no 90/270 transform on these sensors, so config validation rejects them (spec: Invalid configuration). Frame rate goes in `controls={"FrameRate": n}` of `create_video_configuration`.

### Auth
Precompute the expected `Authorization` header once; compare with `hmac.compare_digest`. `/healthz` is routed before the auth check. `AUTH_USERNAME` keeps its `pi` default — a username is not a secret — while `AUTH_PASSWORD` has none.

### Shutdown
`SIGTERM`/`SIGINT` handlers call `server.shutdown()` from a helper thread (calling it from the serving thread deadlocks); `serve_forever()` returns, the camera context manager stops recording and closes the camera, `main()` returns 0.

### Packaging and tooling
- `pyproject.toml`: `name = "docker-picamera"`, `requires-python = ">=3.11"`, `dependencies = []` (runtime camera stack comes from apt), hatchling backend, `[project.scripts]` for both commands, `[dependency-groups] dev = [pytest, ruff, mypy]`.
- ruff: `target-version = "py311"`, `line-length = 100`, explicit `select` (E, F, W, I, UP, B, SIM, LOG, RUF); `extend-exclude = ["bin", "plugins", ".claude", ".agents"]` so CI's `ruff check .` covers project code only.
- mypy: `strict = true`; override `ignore_missing_imports` for `picamera2.*` and `libcamera.*`.
- `uv.lock` committed (CI runs `--locked`).

### Dockerfile: two stages, build stage native, runtime arm64
1. `builder` — `FROM --platform=$BUILDPLATFORM ghcr.io/astral-sh/uv:<pinned>-python3.13-trixie-slim`: `uv build --wheel`. The wheel is pure Python, so building it natively skips QEMU for this stage.
2. `runtime` — `FROM debian:trixie-slim` (arm64): add the Raspberry Pi archive key (`/usr/share/keyrings/`) and `trixie main` source; `apt-get install --no-install-recommends python3-picamera2 python3-venv`; `python3 -m venv --system-site-packages /opt/venv`; `pip install --no-deps` the wheel; create user `picamera` (uid 10001) in group `video`; `ENV PATH=/opt/venv/bin:$PATH RESOLUTION=800x600 FRAMERATE=24`; `EXPOSE 8000`; `HEALTHCHECK --start-period=30s CMD python -c "urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3)"`; `USER picamera`; `ENTRYPOINT ["docker-picamera"]`.

Why trixie: it is Debian stable and the Raspberry Pi archive's current suite; its system Python (3.13) satisfies `>=3.11`. Why `--system-site-packages`: the app must see apt's `picamera2`/`libcamera`, while staying in its own venv rather than `pip install --break-system-packages`. Alternatives: `balenalib` base images (deprecated), or building libcamera from source (slow, fragile under QEMU).

`--no-install-recommends` matters: `python3-picamera2` recommends the Qt/OpenCV preview stack, hundreds of MB the server never uses.

### Host device access
`run.sh`: `--device` for each existing `/dev/media*`, `/dev/video*`, `/dev/v4l-subdev*` and `/dev/dma_heap/*` (globbed at run time, because numbering varies by Pi model and kernel), `-v /run/udev:/run/udev:ro`, `--group-add video`, `-e AUTH_PASSWORD` passed through from the caller's environment (fails if unset). The Helm chart cannot enumerate devices per node, so it mounts host `/dev` and `/run/udev` with `privileged: true` — the same privilege the old chart used, now documented as the reason.

### CI: `.github/workflows/image.yml`
Separate from meta-owned `ci.yml` (class M; a local edit would conflict on the next broadcast).
- `hadolint/hadolint-action@v3.5.0` on `Dockerfile`.
- `docker/setup-qemu-action@v4`, `setup-buildx-action@v4`, `metadata-action@v6` (tags: `latest` on default branch, `sha-<short>`, semver `{{version}}` and `{{major}}.{{minor}}`), `build-push-action@v7` with `platforms: linux/arm64`, GitHub Actions cache.
- `login-action@v4` and `push: true` only when `github.event_name != 'pull_request'`. Triggers: `pull_request`, `push` to `main`, tags `v*`. All tags verified to resolve on 2026-10-09.
- `timeout-minutes` set, matching `ci.yml`'s convention.
- Docker Hub images (QEMU's binfmt, BuildKit, the `debian` base) are pulled through `mirror.gcr.io`: Docker Hub's anonymous per-IP limit fails shared runners, and pull requests carry no credentials. Found on the first PR run.

### Helm chart: rename, then rewrite
`git mv charts/kubesim-picamera-arm32v7 charts/picamera` so history follows, then rewrite: `Chart.yaml` `apiVersion: v2`, `appVersion` = package version; `requirements.yaml` and `configmap-etc.yaml` deleted; helpers renamed `picamera.*`; `required` on `auth.existingSecret`; Ingress moved to `networking.k8s.io/v1`. Values keys: `image.*`, `auth.existingSecret`, `camera.{resolution,framerate,rotate,hflip,vflip}`, `service.*`, `ingress.*`, `nodeSelector`, `resources`.

### Docs
README filled from the template headings (Install / Run / Configuration / Development / Secrets). `CLAUDE.md` § 1 states what the project is; § 2 says there is no data tree; § 3 says no project skills yet; § 4 names the image and chart; § 5 says it reads only its own tree. New `architecture.md` with the module table above and the invariants (camera import confined to `camera.py`; no credentials in image or chart). `.env.example` lists `AUTH_PASSWORD` and the Docker Hub secrets.

## Risks / Trade-offs

- [Camera path unverifiable in CI] → tests cover config, HTTP, auth, streaming and health against a fake camera; tasks end with an on-device checklist the operator runs before tagging a release.
- [`picamera2` API drift] → the adapter is ~40 lines in one module; the archive's version is pinned implicitly by suite, and the startup log prints the `picamera2` version.
- [QEMU arm64 build of the apt stage is slow] → only the runtime stage runs emulated; buildx GitHub Actions cache keeps rebuilds to the changed layers.
- [Privileged pod in the chart] → unchanged from the old chart, now explicit in values comments and `architecture.md`; non-root user still applies inside.
- [Breaking changes for existing deployments] → listed in the proposal; release notes for the first tag repeat them with the migration below.
- [Excluding meta trees from ruff hides their lint] → recorded as meta feedback; meta owns the fix.

## Migration Plan

1. Merge; CI publishes `kubedge/picamera:latest` once `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` exist (operator adds them before merging, or the publish job fails on `main`).
2. On each Pi: move to 64-bit Raspberry Pi OS (trixie), confirm `rpicam-hello` sees the camera, then `AUTH_PASSWORD=… ./run.sh`.
3. Kubernetes: `kubectl create secret generic picamera-auth --from-literal=username=pi --from-literal=password=…`; `helm uninstall` the old `kubesim-picamera-arm32v7` release; `helm install picamera charts/picamera --set auth.existingSecret=picamera-auth`; label camera nodes `picameraInstalled=true`.
4. Rollback: the previous image tags stay on Docker Hub untouched; the old chart is in git history at `2b033df`.

## Open Questions

- Whether `kubedge1/kubesim_picamera-arm32v7` (the old chart's image) has consumers elsewhere — it is not touched here; retiring it is a Docker Hub housekeeping decision.
