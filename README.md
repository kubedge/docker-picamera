# docker-picamera

An MJPEG stream of a Raspberry Pi camera behind HTTP Basic authentication, shipped as an
arm64 container image (`kubedge1/picamera` on Docker Hub) and a Helm chart for Kubernetes
camera nodes. A leaf in the kubedge fleet: it depends on no sibling, and anything that
reads MJPEG over HTTP — a browser, VLC, ffmpeg — consumes it.

## Install

    uv sync                       # development, on any host
    docker pull kubedge1/picamera  # on a Raspberry Pi (64-bit Raspberry Pi OS)

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

kubedge-dashboard finds the pod by its label `kubedge.device.name=camera` and reads two
annotations: `kubedge.io/stream-url` (the in-cluster stream address, always set) and
`kubedge.io/external-url`, set from `--set dashboard.externalUrl=http://<node>:30456/stream.mjpg`.
That is the link the dashboard shows; without it, the camera is listed with no link.
`--set dashboard.discoverable=false` removes all three.

A Rust implementation with the same contract and much less memory is
`kubedge1/picamera-rs`: `./run.sh kubedge1/picamera-rs` on a Pi, or `charts/picamera-rs`
(same values) on Kubernetes — see [`charts/picamera-rs/README.md`](charts/picamera-rs/README.md).
Only one of the two can own a node's camera at a time.

The unauthenticated example from the original picamera recipe (fixed 640×480, no
credentials) is in the same image:

    docker run --rm --entrypoint docker-picamera-example ... kubedge1/picamera

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
| `PORT` | TCP port to listen on | `8000` | no |
| `ENCODER` | Rust only: `software` (JPEG in `rpicam-vid`, CPU), `hardware` (the Pi 3/4's V4L2 JPEG encoder; fails if absent), `auto` (hardware if present) | `software` | no |
| `JPEG_QUALITY` | Rust only: 1–100 for whichever encoder runs | encoder default | no |

Routes: `/` → `/index.html` (page), `/stream.mjpg` (stream), both authenticated;
`/healthz` is open and returns `200` while frames are less than 5 s old, `503` otherwise.
A bad value stops the service at startup with `error: <VARIABLE>: …` and exit status 2.

This project keeps no data tree; it writes nothing outside the repository.

## Development

    make check                    # rust + all of the below except the image builds
    uv run pytest
    uv run ruff check . && uv run ruff format --check .
    uv run mypy src
    helm lint charts/picamera --set auth.existingSecret=lint
    ./build.sh                    # linux/arm64 image; needs Docker with buildx and QEMU
    pre-commit run --all-files

Tests run on any host: the camera is replaced by a fake, and the chart tests run when
`helm` is installed. CI (`ci.yml`, delivered by claude-meta) runs the Python gate;
`image.yml` lints the Dockerfile, tests the chart and builds the image on every pull
request and push to `main`. CI never logs in to a registry and holds no secrets.

## Publishing

Images are pushed by hand, as for every `kubedge1/*` image:

    docker login                  # once; an account with push rights to kubedge1
    make push                     # make check, then kubedge1/picamera:latest and :<version>
    make push-rs                  # make check, then kubedge1/picamera-rs:latest and :<version>

The version is `__version__` in `src/docker_picamera/__init__.py`; keep the chart's
`appVersion` equal to it.

## Secrets

- **Run time** — `AUTH_PASSWORD`, supplied where the container runs: the caller's
  environment for `run.sh`, `docker run -e`, or the Kubernetes Secret named by
  `auth.existingSecret`. It is never in the repository, the image or chart values.
- **CI** — none. Registry credentials stay in your local `docker login`; nothing is
  stored in GitHub. [`.env.example`](.env.example) lists no keys. Never commit a `.env`.

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
