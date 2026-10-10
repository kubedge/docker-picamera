"""Regression guard for picamera-rs memory: peak RSS (VmHWM) while serving two stream clients
for 30 s with the fake camera stays under RSS_GUARD_KIB. Linux only; CI sets the threshold.
The fake camera is a separate process and is not counted — this guards the Rust binary
alone; the on-device budget (rust-streamer "Memory budget") is measured with
rust/scripts/measure-memory.sh."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest
from httphelp import credentials, read_parts
from service import RUST_BIN, Start

LIMIT = os.environ.get("RSS_GUARD_KIB")
pytestmark = pytest.mark.skipif(
    not LIMIT or not sys.platform.startswith("linux"), reason="RSS_GUARD_KIB unset or not Linux"
)


@pytest.fixture
def impl() -> str:
    if not RUST_BIN.exists():
        pytest.fail(f"{RUST_BIN} is not built")
    return "rust"


def test_rust_peak_rss_under_limit(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "RESOLUTION": "800x600", "FRAMERATE": "24"})
    stop = threading.Event()

    def client() -> None:
        conn = service.connect()
        conn.request("GET", "/stream.mjpg", headers=credentials())
        resp = conn.getresponse()
        while not stop.is_set():
            read_parts(resp, 1)
        conn.close()

    clients = [threading.Thread(target=client, daemon=True) for _ in range(2)]
    for c in clients:
        c.start()
    time.sleep(30)
    status = Path(f"/proc/{service.proc.pid}/status").read_text()
    stop.set()
    peak = int(next(line.split()[1] for line in status.splitlines() if line.startswith("VmHWM:")))
    print(f"picamera-rs VmHWM {peak} KiB (limit {LIMIT} KiB)")
    assert peak <= int(str(LIMIT)), f"peak RSS {peak} KiB > {LIMIT} KiB"
