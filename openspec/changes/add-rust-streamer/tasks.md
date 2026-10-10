# Tasks

## 1. Prerequisite

- [ ] 1.1 Confirm `modernize-python-and-docker` is archived (`openspec list --specs` shows `camera-streaming`, `container-image`, `helm-deployment`) and its image has been measured on device; verify `openspec show camera-streaming --type spec` lists the requirements this change references

## 2. Shared conformance suite

- [x] 2.1 Move the black-box cases from `tests/test_server.py` into `tests/conformance/` behind `base_url` / frame-source fixtures; add `python_impl`; verify `uv run pytest tests/conformance` passes against Python with the same case count as before
- [x] 2.2 Add `tests/fixtures/fake-rpicam-vid` (writes fixture JPEGs at the requested rate, records argv, optional garbage-between-frames and exit-after-N modes) and the `rust_impl` fixture that skips when `rust/target/debug/picamera-rs` is absent; verify the suite reports the Rust cases as skipped, not failed, before the binary exists

## 3. Rust service

- [x] 3.1 Scaffold `rust/` (`Cargo.toml` with release profile per design, `rust-toolchain.toml` pinned to 1.99, `Cargo.lock`, `.gitignore` for `target/`); verify `cargo build` and `cargo clippy --all-targets -- -D warnings` pass on an empty `main`
- [x] 3.2 Implement `config.rs` (variables, defaults, validation, messages, exit 2 on error); verify unit tests cover every case in `tests/test_config.py` with identical messages
- [x] 3.3 Implement `mjpeg.rs` (structural JPEG splitter, bounded buffer, dropped-byte counter); verify unit tests cover split-across-reads, `FF D9` inside entropy data with stuffing, garbage before SOI, and buffer overflow reset
- [x] 3.4 Implement `camera.rs` (argv builder, `RPICAM_VID` override, `kill_on_drop`, stderr forwarding, exit → error) and the `watch<Bytes>` publisher; verify unit tests assert the argv for defaults, `ROTATE=180`, `HFLIP`/`VFLIP`, and that a child exit surfaces as an error
- [x] 3.5 Implement `auth.rs` and `server.rs` (routes, Basic auth with constant-time compare, `/healthz` age check, multipart stream, 404) and `main.rs` (current-thread runtime, `--example`, `--healthcheck`, SIGTERM/SIGINT handling); verify `cargo build` then `uv run pytest tests/conformance` passes for both `python_impl` and `rust_impl` with no skips
- [x] 3.6 Add conformance cases for the Rust-only requirements (camera process dies → non-zero exit; garbage between frames → only complete frames delivered; SIGTERM → child terminated, exit 0) using the fake's modes; verify they pass

## 4. Container image and CI

- [ ] 4.1 Write `rust/Dockerfile` per design (native `xx-cargo` builder, `xx-verify`, trixie runtime with `rpicam-apps-core` `--no-install-recommends`, non-root `video` user, no credentials, `HEALTHCHECK` via `--healthcheck`); verify hadolint is clean and `docker buildx build --platform linux/arm64 -f rust/Dockerfile .` succeeds (CI if no local daemon)
- [ ] 4.2 Add `.github/workflows/rust.yml` (fmt, clippy, test, build, conformance, RSS regression guard) with `timeout-minutes`; verify it runs green on the PR
- [ ] 4.3 Extend `.github/workflows/image.yml` to a two-image matrix with per-Dockerfile hadolint, build-only; add `rust/build.sh` (`--push` after manual `docker login`); verify the PR run builds both images and pushes neither
- [x] 4.4 Make `run.sh` accept the image as an optional argument (default `kubedge1/picamera`); verify `shellcheck`/`shfmt` pass and `./run.sh kubedge1/picamera-rs` composes the same device flags

## 5. Helm chart

- [x] 5.1 Create `charts/picamera-rs` from `charts/picamera` (names, image, `appVersion`, placeholder resources); verify `helm lint charts/picamera-rs --set auth.existingSecret=x` passes
- [x] 5.2 Add a CI step that renders one values file through both charts and diffs them, allowing only names, image and resources to differ; verify it passes, and that rendering without `auth.existingSecret` fails naming it
- [x] 5.3 Document in `charts/picamera-rs/README.md` and the main README how to choose a chart, the one-camera-per-node caveat, and side-by-side install with distinct node ports; verify `helm install --dry-run` of both charts in one namespace with distinct `service.nodePort` succeeds

## 6. Documentation

- [x] 6.1 Update `architecture.md` (Rust layout, frame fan-out, splitter, camera supervision, conformance suite as the contract) and `CLAUDE.md` § 1 and § 4 (two implementations, two images, two charts); verify `python3 bin/check-doc-set.py` and `python3 bin/claude-md-check.py` pass
- [x] 6.2 Add `rust/scripts/measure-memory.sh` (runs an image under the reference load, reads cgroup `memory.peak`, prints peaks and ratio); verify `shellcheck` passes and `--help` documents the reference load

## 7. Integration

- [ ] 7.1 Open the PR and verify `ci.yml`, `rust.yml` and `image.yml` are green with nothing pushed
- [ ] 7.2 On-device check (operator, before the release tag): run `measure-memory.sh` for both images on the same Pi; verify the Rust peak is ≤ 50% of Python's, write both figures into the release notes, set `charts/picamera-rs` default resources to measured peak × 1.5, and confirm streaming, `/healthz`, `ROTATE=180` and `docker stop` behave as with the Python image
