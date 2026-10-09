# docker-picamera

An MJPEG stream of a Raspberry Pi camera behind HTTP Basic authentication, shipped as an
arm64 container image (`kubedge/picamera` on Docker Hub) and a Helm chart for Kubernetes
camera nodes. A leaf in the kubedge fleet: it depends on no sibling, and anything that
reads MJPEG over HTTP — a browser, VLC, ffmpeg — consumes it.

## Install

    uv sync                       # development, on any host
    docker pull kubedge/picamera  # on a Raspberry Pi (64-bit Raspberry Pi OS)

## Run

On a Raspberry Pi with 64-bit Raspberry Pi OS and a libcamera-supported camera
(`rpicam-hello --list-cameras` lists it) — *device only*:

    AUTH_PASSWORD=<password> ./run.sh

then open `http://<pi>:8000/`. `run.sh` passes the camera's device nodes and `/run/udev`
into the container and forwards `AUTH_PASSWORD` (and any other variable below that is set)
by name, so the value never appears on a command line.

On Kubernetes — *cluster only*:

    kubectl create secret generic picamera-auth \
      --from-literal=username=pi --from-literal=password=<password>
    kubectl label node <camera-node> picameraInstalled=true
    helm install picamera charts/picamera --set auth.existingSecret=picamera-auth

The stream is then on `http://<node>:30456/`. The chart schedules only onto arm64 nodes
carrying that label, runs one pod per release (a camera has one owner), and probes
`/healthz`. See `charts/picamera/values.yaml` for every setting.

The unauthenticated example from the original picamera recipe (fixed 640×480, no
credentials) is in the same image:

    docker run --rm --entrypoint docker-picamera-example ... kubedge/picamera

Off a Pi, `uv run docker-picamera` validates its configuration and then exits with
`error: camera: …` (status 1), because picamera2 exists only on the device.

## Configuration

| variable | what it sets | default | required |
| --- | --- | --- | --- |
| `AUTH_PASSWORD` | Basic-auth password. The service refuses to start without it. | — | yes |
| `AUTH_USERNAME` | Basic-auth user name | `pi` | no |
| `RESOLUTION` | capture size, `<width>x<height>` | `800x600` | no |
| `FRAMERATE` | frames per second | `24` | no |
| `ROTATE` | `0` or `180` (libcamera cannot rotate by 90/270) | `0` | no |
| `HFLIP`, `VFLIP` | `true` / `false` | `false` | no |

Routes: `/` → `/index.html` (page), `/stream.mjpg` (stream), both authenticated;
`/healthz` is open and returns `200` while frames are less than 5 s old, `503` otherwise.
A bad value stops the service at startup with `error: <VARIABLE>: …` and exit status 2.

This project keeps no data tree; it writes nothing outside the repository.

## Development

    uv run pytest
    uv run ruff check . && uv run ruff format --check .
    uv run mypy src
    helm lint charts/picamera --set auth.existingSecret=lint
    ./build.sh                    # linux/arm64 image; needs Docker with buildx and QEMU
    pre-commit run --all-files

Tests run on any host: the camera is replaced by a fake, and the chart tests run when
`helm` is installed. CI (`ci.yml`, delivered by claude-meta) runs the Python gate;
`image.yml` lints the Dockerfile, tests the chart and builds the image on every pull
request, and publishes from `main` (`latest`, `sha-<short>`) and `v*` tags
(`X.Y.Z`, `X.Y`).

## Secrets

- **Run time** — `AUTH_PASSWORD`, supplied where the container runs: the caller's
  environment for `run.sh`, `docker run -e`, or the Kubernetes Secret named by
  `auth.existingSecret`. It is never in the repository, the image or chart values.
- **CI** — `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` (listed in [`.env.example`](.env.example)).
  They live in the macOS Keychain under service `com.kubedge.docker-picamera`
  (`bin/set-secret.sh <KEY>`) and are projected to GitHub Actions with
  `uv run --script bin/sync-secrets.py push DOCKERHUB_USERNAME DOCKERHUB_TOKEN --apply`.
  Never commit a `.env`.

## Upgrading from the 2018 image

- The camera stack is now picamera2 / libcamera: run on 64-bit Raspberry Pi OS; the
  container needs the libcamera device nodes (`run.sh`, the chart) instead of `/dev/vchiq`.
- `AUTH_PASSWORD` has no default any more — set it, or the container exits.
- `ROTATE` accepts only `0` and `180`.
- The image is `linux/arm64` only.
- The chart `charts/kubesim-picamera-arm32v7` is now `charts/picamera`: `helm uninstall`
  the old release, create the Secret, then install as above.

## Documentation

- [`architecture.md`](architecture.md) — how the code is organised; read it before changing it
- [`CLAUDE.md`](CLAUDE.md) — what a Claude session reads at start; a router, not a manual
- `openspec/` — `specs/` is what it must do; `changes/` is work in flight

## Credits

Derived from Philipp Schmitt's `docker-picamera` and the web-streaming recipe in the
picamera and picamera2 documentation.
