"""Camera adapter — the only module that imports picamera2.

picamera2 and libcamera come from the image's Raspberry Pi apt packages; they are
imported inside open_camera() so every other module, and the tests, run without them.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import metadata
from typing import Any

from docker_picamera.config import Config
from docker_picamera.frames import FrameBuffer

LOG = logging.getLogger(__name__)


class CameraUnavailable(RuntimeError):
    """The camera stack cannot be loaded on this host."""


class _FrameSink(io.BufferedIOBase):
    """File-like target for picamera2's FileOutput, which writes one JPEG per call."""

    def __init__(self, frames: FrameBuffer) -> None:
        super().__init__()
        self._frames = frames

    def writable(self) -> bool:
        return True

    def write(self, data: Any, /) -> int:
        return self._frames.write(bytes(data))


def transform_flags(config: Config) -> tuple[bool, bool]:
    """(hflip, vflip) for libcamera's Transform. A 180° rotation is both flips toggled."""
    rotated = config.rotation == 180
    return config.hflip != rotated, config.vflip != rotated


@contextmanager
def open_camera(config: Config, frames: FrameBuffer) -> Iterator[None]:
    """Record MJPEG into `frames` for the duration of the block."""
    try:
        from libcamera import Transform
        from picamera2 import Picamera2
        from picamera2.encoders import JpegEncoder, MJPEGEncoder
        from picamera2.outputs import FileOutput
    except ImportError as exc:
        raise CameraUnavailable(
            f"camera: picamera2/libcamera are not importable ({exc}); "
            "they exist only on a Raspberry Pi with python3-picamera2 installed"
        ) from exc

    hflip, vflip = transform_flags(config)
    camera = Picamera2()
    try:
        camera.configure(
            camera.create_video_configuration(
                main={"size": (config.width, config.height)},
                controls={"FrameRate": config.framerate},
                transform=Transform(hflip=hflip, vflip=vflip),
            )
        )
        try:
            encoder = MJPEGEncoder()
        except Exception as exc:  # no hardware JPEG block (e.g. Pi 5)
            LOG.info("hardware MJPEG encoder unavailable (%s); using software JPEG", exc)
            encoder = JpegEncoder()
        LOG.info(
            "camera %dx%d@%d hflip=%s vflip=%s encoder=%s picamera2=%s",
            config.width,
            config.height,
            config.framerate,
            hflip,
            vflip,
            type(encoder).__name__,
            _picamera2_version(),
        )
        camera.start_recording(encoder, FileOutput(_FrameSink(frames)))
        try:
            yield
        finally:
            camera.stop_recording()
    finally:
        camera.close()


def _picamera2_version() -> str:
    try:
        return metadata.version("picamera2")
    except metadata.PackageNotFoundError:
        return "unknown"
