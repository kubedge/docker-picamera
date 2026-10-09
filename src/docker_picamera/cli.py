"""Entry points: `docker-picamera` (authenticated) and `docker-picamera-example` (open)."""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from types import FrameType

from docker_picamera.camera import CameraUnavailable, open_camera
from docker_picamera.config import EXAMPLE_CONFIG, Config, ConfigError, load_config
from docker_picamera.frames import FrameBuffer
from docker_picamera.server import (
    Site,
    StreamingServer,
    basic_auth_header,
    build_handler,
    render_page,
)

LOG = logging.getLogger(__name__)

LISTEN_PORT = 8000
EXIT_CAMERA_UNAVAILABLE = 1
EXIT_CONFIG_ERROR = 2

CameraFactory = Callable[[Config, FrameBuffer], AbstractContextManager[None]]


def main() -> int:
    _setup_logging()
    try:
        config = load_config(os.environ)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    return serve(
        config,
        title="picamera MJPEG streaming demo",
        heading="PiCamera MJPEG Streaming Demo",
        auth=basic_auth_header(config.username, config.password),
    )


def example_main() -> int:
    _setup_logging()
    title = "Raspberry Pi - Surveillance Camera"
    return serve(EXAMPLE_CONFIG, title=title, heading=title, auth=None)


def serve(
    config: Config,
    *,
    title: str,
    heading: str,
    auth: bytes | None,
    camera: CameraFactory | None = None,
) -> int:
    """Run the camera and HTTP server until SIGTERM or SIGINT; return the exit status."""
    frames = FrameBuffer()
    site = Site(
        frames=frames,
        page=render_page(title, heading, config.width, config.height),
        expected_auth=auth,
    )
    try:
        with (camera or open_camera)(config, frames):
            server = StreamingServer(("", LISTEN_PORT), build_handler(site))
            previous = _install_shutdown_handlers(server)
            LOG.info("serving on port %d", server.server_address[1])
            try:
                server.serve_forever()
            finally:
                for signum, handler in previous.items():
                    signal.signal(signum, handler)
                frames.close()
                server.server_close()
    except CameraUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CAMERA_UNAVAILABLE
    LOG.info("stopped")
    return 0


def _install_shutdown_handlers(
    server: StreamingServer,
) -> dict[int, Callable[[int, FrameType | None], object] | int | None]:
    def on_signal(signum: int, _frame: FrameType | None) -> None:
        LOG.info("received %s, shutting down", signal.Signals(signum).name)
        # shutdown() blocks until serve_forever() returns, so it cannot run on the
        # thread that is serving.
        threading.Thread(target=server.shutdown, daemon=True).start()

    return {signum: signal.signal(signum, on_signal) for signum in (signal.SIGTERM, signal.SIGINT)}


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
