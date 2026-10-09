"""HTTP routes — index page, MJPEG stream and health check — optionally behind Basic auth."""

from __future__ import annotations

import base64
import hmac
import logging
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from docker_picamera.frames import FrameBuffer

LOG = logging.getLogger(__name__)

AUTH_REALM = "picamera"
HEALTH_MAX_AGE = 5.0
# How long a stream client waits for a frame before re-checking for shutdown.
FRAME_WAIT = 1.0

PAGE_TEMPLATE = """\
<html>
<head>
<title>{title}</title>
</head>
<body>
<h1>{heading}</h1>
<img src="stream.mjpg" width="{width}" height="{height}" />
</body>
</html>
"""


def render_page(title: str, heading: str, width: int, height: int) -> bytes:
    return PAGE_TEMPLATE.format(title=title, heading=heading, width=width, height=height).encode()


def basic_auth_header(username: str, password: str) -> bytes:
    """The exact `Authorization` value a client must send."""
    return b"Basic " + base64.b64encode(f"{username}:{password}".encode())


@dataclass(frozen=True)
class Site:
    frames: FrameBuffer
    page: bytes
    # None serves every route without credentials (docker-picamera-example).
    expected_auth: bytes | None


class StreamingServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def build_handler(site: Site) -> type[BaseHTTPRequestHandler]:
    """A request handler class bound to one Site — no module globals."""

    class StreamingHandler(BaseHTTPRequestHandler):
        server_version = "docker-picamera"

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._health()
            elif not self._authorized():
                self._challenge()
            elif self.path == "/":
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                self.send_header("Location", "/index.html")
                self.end_headers()
            elif self.path == "/index.html":
                self._send(HTTPStatus.OK, "text/html", site.page)
            elif self.path == "/stream.mjpg":
                self._stream()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 — stdlib name
            LOG.info("%s %s", self.address_string(), format % args)

        def _authorized(self) -> bool:
            if site.expected_auth is None:
                return True
            received = self.headers.get("Authorization")
            if received is None:
                return False
            # Header text was decoded as latin-1 by the parser; re-encoding is lossless.
            return hmac.compare_digest(received.encode("latin-1"), site.expected_auth)

        def _challenge(self) -> None:
            body = (
                b"no auth header received"
                if self.headers.get("Authorization") is None
                else b"not authenticated"
            )
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", f'Basic realm="{AUTH_REALM}"')
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _health(self) -> None:
            age = site.frames.age()
            if age is not None and age <= HEALTH_MAX_AGE:
                self._send(HTTPStatus.OK, "text/plain", b"ok\n")
            else:
                self._send(HTTPStatus.SERVICE_UNAVAILABLE, "text/plain", b"no recent frame\n")

        def _send(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self.end_headers()
            sequence = 0
            try:
                while not site.frames.closed:
                    item = site.frames.wait_next(sequence, timeout=FRAME_WAIT)
                    if item is None:
                        continue
                    sequence, frame = item
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except OSError as exc:
                LOG.info("Removed streaming client %s: %s", self.client_address, exc)

    return StreamingHandler
