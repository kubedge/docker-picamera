"""Shared pieces of the conformance suite: the camera-streaming contract as a black box,
run against both implementations.

Each case starts the real service as a subprocess on a free port with a fake camera:
- python: `python -m docker_picamera` with tests/fixtures/fakecam first on PYTHONPATH
  (a stand-in picamera2/libcamera);
- rust: rust/target/debug/picamera-rs with RPICAM_VID=tests/fixtures/fake-rpicam-vid.
The rust cases skip when the binary is not built, unless REQUIRE_RUST=1.
"""

from __future__ import annotations

import http.client
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
RUST_BIN = ROOT / "rust" / "target" / "debug" / "picamera-rs"
SCRUBBED = (
    "AUTH_USERNAME",
    "AUTH_PASSWORD",
    "RESOLUTION",
    "FRAMERATE",
    "ROTATE",
    "HFLIP",
    "VFLIP",
    "PORT",
    "RPICAM_VID",
)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@dataclass
class Service:
    proc: subprocess.Popen[bytes]
    port: int
    log: Path

    def connect(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)

    def get(
        self, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        conn = self.connect()
        try:
            conn.request("GET", path, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read()
        finally:
            conn.close()

    def stderr(self) -> str:
        return self.log.read_text(errors="replace")

    def wait_for_log(self, text: str, timeout: float = 5) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if text in self.stderr():
                return True
            time.sleep(0.05)
        return False

    def stop(self, sig: int = signal.SIGTERM, timeout: float = 5) -> int:
        if self.proc.poll() is None:
            self.proc.send_signal(sig)
        try:
            return self.proc.wait(timeout)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            raise


Start = Callable[..., Service]


def command(impl: str, example: bool) -> list[str]:
    if impl == "python":
        if example:
            entry = "import sys; from docker_picamera.cli import example_main as m; sys.exit(m())"
            return [sys.executable, "-c", entry]
        return [sys.executable, "-m", "docker_picamera"]
    return [str(RUST_BIN), *(["--example"] if example else [])]
