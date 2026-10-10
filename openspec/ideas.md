# Ideas

## Raw ideas

- [x] picamera-on-device-check — run modernize-python-and-docker task 8.2 on a Pi camera (kube-node02, OV5647, via picluster-automation's ctr-smoke.yml): stream, /healthz 200, ROTATE=180, healthy, clean SIGTERM, memory.peak (the Rust change's baseline). Archived 2026-10-09 with this open.

## Suggested next-up

## Archived

- add-rust-hw-jpeg (2026-10-09) — picamera-rs ENCODER=software|hardware|auto + JPEG_QUALITY; V4L2 bcm2835-codec-encode_image (/dev/video31) by hand ioctls; fixes for 64-byte-padded I420 rows (0.4.2) and SIGTERM hang (0.4.3); on device hardware saves ~3 CPU points, default stays software.
- add-rust-streamer (2026-10-10) — picamera-rs (Rust, rpicam-vid), shared conformance suite, kubedge1/picamera-rs, charts/picamera-rs; on device 7.0 MiB vs Python 33.3 (21%).

- add-dashboard-discovery (2026-10-09) — chart label kubedge.device.name=camera + kubedge.io/stream-url / external-url annotations; matched by kubedge-dashboard PR #11.
- modernize-python-and-docker (2026-10-09) — src/ package, picamera2, arm64 image kubedge1/picamera, charts/picamera; 8.2 on-device check still open (Raw ideas).
