# Tasks

## 1. Python project scaffolding

- [ ] 1.1 Add `pyproject.toml` (name `docker-picamera`, version `0.2.0`, `requires-python >=3.11`, `dependencies = []`, hatchling, `[project.scripts]` `docker-picamera` → `docker_picamera.cli:main` and `docker-picamera-example` → `docker_picamera.cli:example_main`, dev group pytest/ruff/mypy, ruff/mypy/pytest config per design incl. `extend-exclude` of meta trees) and an empty `src/docker_picamera/__init__.py` with `__version__`; verify `uv lock` writes `uv.lock` and `uv sync --locked` succeeds
- [ ] 1.2 Verify the meta-tree exclusion: `uv run ruff check .` and `uv run ruff format --check .` report nothing under `bin/`, `plugins/`, `.claude/`, `.agents/`

## 2. Configuration

- [ ] 2.1 Implement `config.py` (`Config`, `ConfigError`, `load_config(environ)`) per spec "Configuration from the environment", "Password is required", "Invalid configuration is rejected at startup"; verify `tests/test_config.py` covers defaults, explicit values, case-insensitive flips, missing/empty password, malformed resolution, non-positive framerate, `ROTATE=90`, bad flip value — `uv run pytest tests/test_config.py` passes

## 3. Streaming core

- [ ] 3.1 Implement `frames.py` (`FrameBuffer`: `write`, `wait_next` with timeout, `age`); verify `tests/test_frames.py` covers a reader woken by a write, timeout with no frame, and `age()` before/after the first frame
- [ ] 3.2 Implement `server.py` (`build_handler`, `StreamingServer`, page rendering) per spec "Basic authentication", "Index page", "MJPEG stream", "Health endpoint", "Unknown paths", "Listening address"; verify `tests/test_server.py` runs a real server on port 0 with a fake frame producer and covers: 401 + `WWW-Authenticate` without/with wrong credentials, 301 on `/`, page embeds resolution, two concurrent stream clients each parse ≥2 `--FRAME` parts with matching `Content-Length`, a disconnecting client does not stop the other, `/healthz` 200/503 without credentials, 404, and no-auth mode for the example

## 4. Camera adapter and entry points

- [ ] 4.1 Implement `camera.py` (`open_camera(config, sink)`: lazy `picamera2` import, video configuration with size and `FrameRate`, `Transform` for flips/180°, `MJPEGEncoder` → `JpegEncoder` fallback, logs encoder and `picamera2` version, stops and closes on exit); verify `uv run mypy src` passes and `tests/test_camera.py` drives it against a stub `picamera2` module in `sys.modules` (transform for `ROTATE=180`+`HFLIP`, fallback when `MJPEGEncoder` raises, stop/close on exit)
- [ ] 4.2 Implement `cli.py` (`main`, `example_main`, logging setup, SIGTERM/SIGINT → `server.shutdown()` from a helper thread, config errors → stderr + exit 2) and `__main__.py`; verify `tests/test_cli.py` covers exit code and message for a missing `AUTH_PASSWORD` without importing `picamera2`, and that a SIGTERM delivered to a running `main` (camera stubbed) returns 0
- [ ] 4.3 Delete top-level `web_streaming.py` and `example.py`; verify `git ls-files '*.py'` lists no Python outside `src/`, `tests/` and meta trees, and `uv run docker-picamera` with no `AUTH_PASSWORD` prints the error and exits non-zero
- [ ] 4.4 Run the full CI python gate locally — `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest` — and verify every step exits 0

## 5. Container image

- [ ] 5.1 Verify the pinned uv builder tag exists (`docker manifest inspect ghcr.io/astral-sh/uv:<version>-python3.13-trixie-slim` or the GHCR tags API) before writing it into the Dockerfile
- [ ] 5.2 Rewrite `Dockerfile` per design (native `builder` stage → wheel; `debian:trixie-slim` runtime with Raspberry Pi archive keyring + source, `python3-picamera2 python3-venv` with `--no-install-recommends`, venv with system site packages, non-root `picamera` user in `video`, `ENV` without credentials, `EXPOSE 8000`, `HEALTHCHECK`, `ENTRYPOINT ["docker-picamera"]`); add `.dockerignore` (`.git`, `.venv`, `.local`, `tests`, meta trees); verify `hadolint Dockerfile` (via `docker run --rm -i hadolint/hadolint < Dockerfile` or the CI job) reports nothing
- [ ] 5.3 Rewrite `build.sh` (`docker buildx build --platform linux/arm64 -t kubedge/picamera .`) and `run.sh` (device globbing, `/run/udev:ro`, `--group-add video`, `AUTH_PASSWORD` required from the caller's environment, no literal credential); verify `shellcheck` and `shfmt -d -i 2 -ci -bn` pass on both and `run.sh` without `AUTH_PASSWORD` exits non-zero before calling docker
- [ ] 5.4 Add `.github/workflows/image.yml` per design (hadolint, QEMU, buildx, metadata, login+push only off pull requests, `linux/arm64`, GHA cache, `timeout-minutes`); delete `.travis.yml`; verify `actionlint` (or `gh workflow view` after push) accepts it and the PR run builds the image without pushing
- [ ] 5.5 Add `AUTH_PASSWORD`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` with descriptions to `.env.example`; verify `gitleaks detect --source . --redact` is clean

## 6. Helm chart

- [ ] 6.1 `git mv charts/kubesim-picamera-arm32v7 charts/picamera`; rewrite `Chart.yaml` (v2, `appVersion: "0.2.0"`), `values.yaml`, `_helpers.tpl`, `deployment.yaml`, `service.yaml`, `ingress.yaml` (`networking.k8s.io/v1`); delete `requirements.yaml` and `configmap-etc.yaml`; verify `helm lint charts/picamera --set auth.existingSecret=x` passes (via `brew install helm` or `docker run alpine/helm`)
- [ ] 6.2 Verify rendering against the spec with `helm template`: fails without `auth.existingSecret` naming it; with it, one container, `secretKeyRef` for both credentials, node selector has `kubernetes.io/arch: arm64` and `picameraInstalled: "true"`, `/healthz` probes on 8000, host `/dev` + read-only `/run/udev`, no `vchiq`, Service NodePort 30456→9090→8000, no Ingress; `camera.resolution=1280x720` sets `RESOLUTION`

## 7. Documentation

- [ ] 7.1 Fill `README.md` (what it is, Install, Run with `docker run`/`run.sh`/Helm, Configuration table of the environment variables, Development commands, Secrets, the breaking changes and migration from the design); verify every command in it runs as written (the device-only ones excepted and marked so)
- [ ] 7.2 Fill `CLAUDE.md` § 1–6 placeholders (what, stack, run command; no data tree; no project skills; produces image + chart; reads only its own tree; routing) and remove the bootstrap nudge; write `architecture.md` (module table, camera-import and no-credentials invariants, image and chart layout); verify `python3 bin/check-doc-set.py` and `python3 bin/claude-md-check.py` pass
- [ ] 7.3 Record the meta findings (ruff on meta-shipped Python, `citrim` labelling `lint`/`test` python-only, `.meta-version` not bumped by broadcast, `bin/*` in `.gitignore`) via `/alemax:feedback`; verify `alemax feedback list` shows them

## 8. Integration

- [ ] 8.1 Run `pre-commit run --all-files` and verify only project files are touched and every hook passes; then open the PR and verify `ci.yml` (lint, type-check, test, secret-scan) and `image.yml` (hadolint, arm64 build, no push) are green
- [ ] 8.2 On-device check (operator, before the first release tag): on 64-bit Raspberry Pi OS with a camera, `AUTH_PASSWORD=… ./run.sh`, then confirm `/index.html` streams, `/healthz` is 200, `ROTATE=180` flips the image, `docker inspect` shows `healthy`, and `docker stop` exits cleanly
