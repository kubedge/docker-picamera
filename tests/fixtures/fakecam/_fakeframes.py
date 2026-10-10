"""Fake camera frames shared by both fakes: structurally valid JPEGs (SOI, APP0, SOS,
entropy data with byte stuffing and a restart marker, EOI), so the Rust splitter parses
them like real ones. Behaviour is driven by environment variables:

  FAKECAM_FRAMES=N       produce N frames, then stay alive and silent (default: no limit)
  FAKECAM_EXIT_AFTER=N   (fake rpicam-vid) exit with status 3 after N frames
  FAKECAM_GARBAGE=1      (fake rpicam-vid) write non-JPEG bytes between frames
  FAKECAM_ARGV_FILE=path (fake rpicam-vid) record argv as JSON
  FAKECAM_PID_FILE=path  (fake rpicam-vid) record its pid
"""

import os

APP0 = b"\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
SOS = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"


def jpeg(n: int) -> bytes:
    payload = (f"frame-{n};".encode() * 200).replace(b"\xff", b"")
    return b"\xff\xd8" + APP0 + SOS + payload + b"\xff\x00\x12\xff\xd0" + payload + b"\xff\xd9"


def frame_limit() -> int | None:
    raw = os.environ.get("FAKECAM_FRAMES")
    return int(raw) if raw else None
