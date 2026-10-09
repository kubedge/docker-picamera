# Spec Delta

## Purpose

Defines the `kubedge/picamera-rs` container image — the Rust streamer packaged with the camera tooling it drives — and how CI builds and publishes it.

## ADDED Requirements

### Requirement: Platform and name
The image SHALL be published to Docker Hub as `kubedge/picamera-rs` for `linux/arm64` only, and SHALL run on 64-bit Raspberry Pi OS with a libcamera-supported camera.

#### Scenario: Manifest platform
- **WHEN** the published manifest for `kubedge/picamera-rs:latest` is inspected
- **THEN** it lists `linux/arm64` and no other platform

### Requirement: Default command
The image SHALL start `picamera-rs` by default and expose port `8000`; example mode SHALL be reachable by passing `--example`.

#### Scenario: Example mode
- **WHEN** the container is started with argument `--example`
- **THEN** the unauthenticated example serves on port 8000

### Requirement: Same runtime contract as the Python image
The image SHALL carry no `AUTH_PASSWORD` value, SHALL run as a non-root user in the `video` group, SHALL reach the camera through the same host devices and read-only `/run/udev` as `kubedge/picamera`, and SHALL declare a health check on `GET /healthz` port 8000.

#### Scenario: Inspect the image
- **WHEN** `docker image inspect kubedge/picamera-rs` is run
- **THEN** `Env` has no `AUTH_PASSWORD`, `User` is non-root, and a health check is declared

#### Scenario: Same run line
- **WHEN** `run.sh` is pointed at `kubedge/picamera-rs`
- **THEN** the container streams with no other change to the command

### Requirement: CI build and publish
Every pull request SHALL lint the Rust image's Dockerfile and build it for `linux/arm64` without pushing. A push to `main` SHALL publish `latest` and `sha-<short-sha>`; a tag `vX.Y.Z` SHALL publish `X.Y.Z` and `X.Y` — the same tags, from the same events, as `kubedge/picamera`.

#### Scenario: Pull request
- **WHEN** a pull request is opened
- **THEN** the Rust image is linted and built and nothing is pushed

#### Scenario: Release tag
- **WHEN** tag `v0.3.0` is pushed
- **THEN** `kubedge/picamera-rs:0.3.0` and `:0.3` are pushed alongside the Python image's tags
