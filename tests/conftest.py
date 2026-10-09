from __future__ import annotations

import base64
import http.client
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest

from docker_picamera.frames import FrameBuffer
from docker_picamera.server import (
    Site,
    StreamingServer,
    basic_auth_header,
    build_handler,
    render_page,
)

USERNAME = "pi"
PASSWORD = "s3cret"


def fake_jpeg(n: int) -> bytes:
    return b"\xff\xd8" + f"frame-{n};".encode() * 40 + b"\xff\xd9"


def credentials(username: str = USERNAME, password: str = PASSWORD) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class FakeCamera:
    """Pushes numbered fake JPEGs into a FrameBuffer until stopped."""

    def __init__(self, frames: FrameBuffer, interval: float = 0.02) -> None:
        self._frames = frames
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def _run(self) -> None:
        n = 0
        while not self._stop.wait(self._interval):
            n += 1
            self._frames.write(fake_jpeg(n))


@dataclass
class RunningServer:
    host: str
    port: int
    frames: FrameBuffer
    _cleanup: list[Callable[[], None]] = field(default_factory=list)

    def connect(self) -> http.client.HTTPConnection:
        return http.client.HTTPConnection(self.host, self.port, timeout=5)

    def get(
        self, path: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, str], bytes]:
        conn = self.connect()
        try:
            conn.request("GET", path, headers=headers or {})
            resp = conn.getresponse()
            return resp.status, dict(resp.getheaders()), resp.read()
        finally:
            conn.close()


def read_parts(resp: http.client.HTTPResponse, count: int) -> list[bytes]:
    """Read `count` multipart MJPEG parts, checking each part's framing."""
    parts: list[bytes] = []
    while len(parts) < count:
        line = resp.readline()
        if not line:
            raise EOFError("stream ended")
        if line != b"--FRAME\r\n":
            continue
        headers: dict[str, str] = {}
        while (header := resp.readline()) not in (b"\r\n", b""):
            name, value = header.decode().split(":", 1)
            headers[name.strip().lower()] = value.strip()
        assert headers["content-type"] == "image/jpeg"
        body = resp.read(int(headers["content-length"]))
        assert len(body) == int(headers["content-length"])
        assert resp.read(2) == b"\r\n"
        parts.append(body)
    return parts


StartServer = Callable[..., RunningServer]


@pytest.fixture
def start_server() -> Iterator[StartServer]:
    running: list[RunningServer] = []

    def _start(
        *,
        auth: bool = True,
        width: int = 800,
        height: int = 600,
        title: str = "picamera MJPEG streaming demo",
        frames: FrameBuffer | None = None,
        camera: bool = True,
    ) -> RunningServer:
        frames = frames or FrameBuffer()
        site = Site(
            frames=frames,
            page=render_page(title, title, width, height),
            expected_auth=basic_auth_header(USERNAME, PASSWORD) if auth else None,
        )
        server = StreamingServer(("127.0.0.1", 0), build_handler(site))
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True
        )
        thread.start()
        result = RunningServer("127.0.0.1", server.server_address[1], frames)
        if camera:
            fake = FakeCamera(frames)
            fake.start()
            result._cleanup.append(fake.stop)
        result._cleanup += [frames.close, server.shutdown, server.server_close]
        running.append(result)
        return result

    yield _start
    for server in running:
        for step in server._cleanup:
            step()
