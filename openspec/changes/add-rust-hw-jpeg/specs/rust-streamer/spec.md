# Spec Delta

## ADDED Requirements

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
