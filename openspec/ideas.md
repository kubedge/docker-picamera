# Ideas

## Raw ideas

- [ ] picamera-on-device-check — run modernize-python-and-docker task 8.2 on a Pi camera (kube-node02, OV5647, via picluster-automation's ctr-smoke.yml): stream, /healthz 200, ROTATE=180, healthy, clean SIGTERM, memory.peak (the Rust change's baseline). Archived 2026-10-09 with this open.

## Suggested next-up

## Archived

- add-dashboard-discovery (2026-10-09) — chart label kubedge.device.name=camera + kubedge.io/stream-url / external-url annotations; matched by kubedge-dashboard PR #11.
- modernize-python-and-docker (2026-10-09) — src/ package, picamera2, arm64 image kubedge1/picamera, charts/picamera; 8.2 on-device check still open (Raw ideas).
