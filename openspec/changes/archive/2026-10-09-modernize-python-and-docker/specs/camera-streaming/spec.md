# Spec Delta

## Purpose

Streams a Raspberry Pi camera as MJPEG over HTTP behind Basic authentication, configured entirely from environment variables, with an unauthenticated health endpoint for probes.

## ADDED Requirements

### Requirement: Configuration from the environment
The service SHALL read its settings once at startup from `AUTH_USERNAME` (default `pi`), `AUTH_PASSWORD` (no default), `RESOLUTION` as `<width>x<height>` (default `800x600`), `FRAMERATE` (default `24`), `ROTATE` (default `0`), `HFLIP` and `VFLIP` (`true`/`false`, case-insensitive, default `false`).

#### Scenario: Defaults apply
- **WHEN** only `AUTH_PASSWORD` is set
- **THEN** the service starts with user `pi`, 800×600 at 24 fps, no rotation and no flips

#### Scenario: Explicit values apply
- **WHEN** `RESOLUTION=1280x720`, `FRAMERATE=15`, `HFLIP=TRUE` are set
- **THEN** the camera is configured for 1280×720 at 15 fps with a horizontal flip

### Requirement: Password is required
The service SHALL refuse to start when `AUTH_PASSWORD` is unset or empty, exiting non-zero with a message naming `AUTH_PASSWORD`, before the camera is opened.

#### Scenario: Missing password
- **WHEN** the service starts without `AUTH_PASSWORD`
- **THEN** it exits with a non-zero status and an error that names `AUTH_PASSWORD`, and does not open the camera

### Requirement: Invalid configuration is rejected at startup
The service SHALL exit non-zero, naming the offending variable and value, when `RESOLUTION` is not two positive integers joined by `x`, `FRAMERATE` is not a positive integer, `ROTATE` is not `0` or `180`, or `HFLIP`/`VFLIP` is not `true` or `false`.

#### Scenario: Malformed resolution
- **WHEN** `RESOLUTION=800by600`
- **THEN** startup fails with an error naming `RESOLUTION` and `800by600`

#### Scenario: Unsupported rotation
- **WHEN** `ROTATE=90`
- **THEN** startup fails with an error stating that only `0` and `180` are supported

### Requirement: Listening address
The service SHALL accept HTTP connections on TCP port 8000 on all interfaces and serve concurrent clients.

#### Scenario: Two clients at once
- **WHEN** two authenticated clients open `/stream.mjpg` at the same time
- **THEN** both receive frames

### Requirement: Basic authentication
Every route except `/healthz` SHALL require HTTP Basic credentials equal to `AUTH_USERNAME` / `AUTH_PASSWORD`. A missing or wrong `Authorization` header SHALL get `401` with `WWW-Authenticate: Basic realm="picamera"`. Credentials SHALL be compared in constant time.

#### Scenario: No credentials
- **WHEN** a client requests `/index.html` without an `Authorization` header
- **THEN** the response is `401` with `WWW-Authenticate: Basic realm="picamera"`

#### Scenario: Wrong credentials
- **WHEN** a client sends Basic credentials with the wrong password
- **THEN** the response is `401`

#### Scenario: Correct credentials
- **WHEN** a client sends the configured username and password
- **THEN** the requested route is served

### Requirement: Index page
`GET /` SHALL redirect with `301` to `/index.html`. `GET /index.html` SHALL return `200` with an HTML page that embeds `stream.mjpg` at the configured width and height.

#### Scenario: Root redirects
- **WHEN** an authenticated client requests `/`
- **THEN** the response is `301` with `Location: /index.html`

#### Scenario: Page embeds the stream
- **WHEN** an authenticated client requests `/index.html` with `RESOLUTION=1280x720`
- **THEN** the response is `200` `text/html` containing an image of source `stream.mjpg`, width 1280 and height 720

### Requirement: MJPEG stream
`GET /stream.mjpg` SHALL return `200` with `Content-Type: multipart/x-mixed-replace; boundary=FRAME` and caching disabled, then send each new camera frame as a part with `Content-Type: image/jpeg` and a correct `Content-Length`, until the client disconnects.

#### Scenario: Frames arrive as parts
- **WHEN** an authenticated client reads `/stream.mjpg` while the camera produces frames
- **THEN** it receives successive `--FRAME` parts, each a complete JPEG whose length matches its `Content-Length`

#### Scenario: A client disconnects
- **WHEN** one streaming client closes its connection
- **THEN** the service logs the removal and keeps serving other clients

### Requirement: Health endpoint
`GET /healthz` SHALL NOT require authentication. It SHALL return `200` when the camera has produced a frame within the last 5 seconds and `503` otherwise.

#### Scenario: Camera producing frames
- **WHEN** a frame was produced less than 5 seconds ago
- **THEN** `/healthz` returns `200` without credentials

#### Scenario: Camera stalled or not started
- **WHEN** no frame has been produced in the last 5 seconds
- **THEN** `/healthz` returns `503`

### Requirement: Unknown paths
An authenticated request for any other path SHALL return `404`.

#### Scenario: Unknown path
- **WHEN** an authenticated client requests `/nope`
- **THEN** the response is `404`

### Requirement: Camera settings take effect
The camera SHALL capture at the configured resolution and frame rate, apply `HFLIP` and `VFLIP`, and rotate the image by 180° when `ROTATE=180`.

#### Scenario: Upside-down mount
- **WHEN** the service runs on a Raspberry Pi with `ROTATE=180`
- **THEN** the streamed image is rotated by 180° (verified on device)

### Requirement: Graceful shutdown
On `SIGTERM` or `SIGINT` the service SHALL stop accepting connections, release the camera and exit with status `0`.

#### Scenario: Container stop
- **WHEN** the process receives `SIGTERM`
- **THEN** it releases the camera and exits `0`

### Requirement: Entry points
The service SHALL be started by the `docker-picamera` command. A second command, `docker-picamera-example`, SHALL serve the same routes without authentication at a fixed 640×480 and 24 fps, with a page titled "Raspberry Pi - Surveillance Camera", and SHALL NOT require `AUTH_PASSWORD`.

#### Scenario: Example needs no password
- **WHEN** `docker-picamera-example` starts with no `AUTH_*` variables set
- **THEN** it serves `/index.html` and `/stream.mjpg` without asking for credentials
