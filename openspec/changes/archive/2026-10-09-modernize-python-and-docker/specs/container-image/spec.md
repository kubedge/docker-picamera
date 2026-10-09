# Spec Delta

## Purpose

Defines the `kubedge1/picamera` container image: what it runs on, how it runs, what it must never contain, and how CI builds and publishes it.

## ADDED Requirements

### Requirement: Platform and name
The image SHALL be published to Docker Hub as `kubedge1/picamera` for `linux/arm64` only, and SHALL run on 64-bit Raspberry Pi OS with a libcamera-supported camera.

#### Scenario: Manifest platform
- **WHEN** the published manifest for `kubedge1/picamera:latest` is inspected
- **THEN** it lists `linux/arm64` and no other platform

### Requirement: Default command
The image SHALL start the authenticated stream (`docker-picamera`) by default, expose port `8000`, and let the example (`docker-picamera-example`) be run by overriding the command.

#### Scenario: Run the example instead
- **WHEN** the container is started with command `docker-picamera-example`
- **THEN** the unauthenticated example serves on port 8000

### Requirement: No credentials in the image
The image SHALL NOT contain a value for `AUTH_PASSWORD` in its environment, labels or files. Non-secret defaults (`RESOLUTION`, `FRAMERATE`) MAY be set.

#### Scenario: Inspect the image config
- **WHEN** `docker image inspect kubedge1/picamera` is run
- **THEN** its `Env` has no `AUTH_PASSWORD` entry

#### Scenario: Started without a password
- **WHEN** the container starts without `-e AUTH_PASSWORD=…`
- **THEN** it exits non-zero with an error naming `AUTH_PASSWORD`

### Requirement: Non-root runtime user
The container SHALL run as a non-root user that belongs to the `video` group, so camera device access comes from group membership, not root.

#### Scenario: Effective user
- **WHEN** `id` is run in the container with the default user
- **THEN** the uid is not 0 and the groups include `video`

### Requirement: Camera device access
The container SHALL reach the camera through the host's libcamera device nodes (`/dev/media*`, `/dev/video*`, `/dev/v4l-subdev*`, `/dev/dma_heap`) and read-only udev data (`/run/udev`), and SHALL NOT require `/dev/vchiq`.

#### Scenario: Run on a Raspberry Pi
- **WHEN** the container runs on 64-bit Raspberry Pi OS with those devices and `/run/udev` passed through
- **THEN** `/stream.mjpg` delivers camera frames (verified on device)

### Requirement: Container health check
The image SHALL declare a health check that probes `GET /healthz` on port 8000, with a start period long enough for the camera to start.

#### Scenario: Healthy once frames flow
- **WHEN** the camera has produced a frame within the last 5 seconds
- **THEN** `docker inspect` reports the container `healthy`

### Requirement: CI builds and never publishes
Every pull request and every push to `main` SHALL lint the Dockerfile and build the `linux/arm64` image. CI SHALL NOT log in to a registry, push an image, or hold registry credentials.

#### Scenario: Pull request
- **WHEN** a pull request changes any file
- **THEN** the image workflow lints and builds the image and pushes nothing

#### Scenario: Merge to main
- **WHEN** a commit lands on `main`
- **THEN** the image is built and nothing is pushed

### Requirement: Manual publishing
The image SHALL be published by an operator with push rights to `kubedge1`, using the project's build script after a local `docker login`, tagged `latest` and the package version.

#### Scenario: Publish a release
- **WHEN** the operator runs `docker login` and then `./build.sh --push` with package version `0.2.0`
- **THEN** `kubedge1/picamera:latest` and `kubedge1/picamera:0.2.0` are pushed for `linux/arm64`
