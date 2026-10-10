"""HTTP helpers shared by the unit and conformance tests."""

from __future__ import annotations

import base64
import http.client

USERNAME = "pi"
PASSWORD = "s3cret"


def credentials(username: str = USERNAME, password: str = PASSWORD) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


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


def fake_jpeg(n: int) -> bytes:
    return b"\xff\xd8" + f"frame-{n};".encode() * 40 + b"\xff\xd9"
