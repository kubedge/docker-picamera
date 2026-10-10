# rust-streamer Specification

## Purpose

A memory-lean Rust implementation of the camera streaming service that is a drop-in replacement for the Python one: same configuration, routes, authentication and health contract.

## Requirements

### Requirement: Conformance to the streaming contract
The Rust service SHALL satisfy every requirement of the `camera-streaming` capability except "Entry points" — configuration, password, validation, listening address, authentication, index page, MJPEG stream, health endpoint, unknown paths, camera settings and graceful shutdown — with identical variable names, defaults, status codes and headers.

#### Scenario: Same conformance suite passes
- **WHEN** the shared HTTP conformance suite runs against the Rust service with a fake camera
- **THEN** every case that passes against the Python service also passes

#### Scenario: Same configuration error
- **WHEN** the Rust service starts without `AUTH_PASSWORD`
- **THEN** it exits non-zero with an error naming `AUTH_PASSWORD`, before starting the camera

### Requirement: Entry points
The Rust service SHALL be started by the `picamera-rs` command. `picamera-rs --example` SHALL behave as `docker-picamera-example`: no authentication, fixed 640×480 at 24 fps, page titled "Raspberry Pi - Surveillance Camera", no `AUTH_PASSWORD` needed.

#### Scenario: Example mode
- **WHEN** `picamera-rs --example` starts with no `AUTH_*` variables
- **THEN** `/index.html` and `/stream.mjpg` are served without credentials

### Requirement: Camera process supervision
The service SHALL capture frames from the Raspberry Pi camera through a child process it starts with the configured resolution, frame rate, flips and rotation. If that process exits, the service SHALL log its exit status and exit non-zero. On shutdown the service SHALL stop the child before exiting.

#### Scenario: Camera process dies
- **WHEN** the capture process exits unexpectedly
- **THEN** the service logs the exit status and exits with a non-zero status

#### Scenario: Container stop
- **WHEN** the service receives `SIGTERM`
- **THEN** the capture process is terminated and the service exits `0`

### Requirement: Malformed camera output
The service SHALL deliver only complete JPEG frames to clients, and SHALL discard bytes that do not form a complete JPEG frame without terminating.

#### Scenario: Garbage between frames
- **WHEN** the capture process emits bytes outside a JPEG start/end pair
- **THEN** clients receive only the complete JPEG frames and the service keeps running

### Requirement: Memory budget
Under the same load on the same Raspberry Pi — 800×600 at 24 fps with two clients streaming for 10 minutes — the peak memory of the Rust container SHALL be at most 50% of the Python container's peak.

#### Scenario: On-device comparison
- **WHEN** both images are run in turn on one Pi under that load and their peak container memory is read from the container runtime
- **THEN** the Rust peak is no more than half the Python peak, and both figures are recorded in the release notes

### Requirement: Encoder selection
The Rust service SHALL read `ENCODER` at startup: `software` (default) encodes JPEG inside the capture process exactly as before this change; `hardware` encodes on the Raspberry Pi's V4L2 JPEG encoder; `auto` uses `hardware` when that encoder is present and `software` otherwise. Any other value SHALL be a startup error naming `ENCODER`. The chosen encoder SHALL be logged at startup.

#### Scenario: Default is unchanged
- **WHEN** the service starts without `ENCODER`
- **THEN** it captures with `rpicam-vid --codec mjpeg` and logs `encoder=software`

#### Scenario: Auto without the encoder
- **WHEN** `ENCODER=auto` on a host with no V4L2 JPEG encoder (for example a Pi 5)
- **THEN** the service runs with the software encoder and logs that the hardware encoder was not found

#### Scenario: Bad value
- **WHEN** `ENCODER=gpu`
- **THEN** startup fails with an error naming `ENCODER` and the value

### Requirement: Hardware encoder required when requested
With `ENCODER=hardware`, the service SHALL exit non-zero with an error naming the missing encoder when no V4L2 JPEG encoder can be opened, and SHALL NOT fall back to software.

#### Scenario: Hardware requested on a host without it
- **WHEN** `ENCODER=hardware` and no encoder device is present
- **THEN** the service exits non-zero with an error that says the hardware JPEG encoder was not found

### Requirement: Hardware encoding output
With the hardware encoder, every published frame SHALL be a complete JPEG of the configured resolution, captured with the configured frame rate, flips and rotation, and the HTTP contract (routes, multipart framing, health, shutdown) SHALL be unchanged.

#### Scenario: Stream on a Pi with the encoder
- **WHEN** the service runs with `ENCODER=hardware` on a Raspberry Pi 3 or 4 with a camera
- **THEN** `/stream.mjpg` delivers JPEG parts of the configured size and `/healthz` returns 200 (verified on device)

### Requirement: JPEG quality
`JPEG_QUALITY`, when set, SHALL be an integer from 1 to 100 and SHALL be applied to whichever encoder is in use; when unset, each encoder keeps its own default. Any other value SHALL be a startup error naming `JPEG_QUALITY`.

#### Scenario: Quality for the software encoder
- **WHEN** `JPEG_QUALITY=85` with the software encoder
- **THEN** the capture process is started with quality 85

#### Scenario: Out of range
- **WHEN** `JPEG_QUALITY=0`
- **THEN** startup fails with an error naming `JPEG_QUALITY`
