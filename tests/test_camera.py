"""open_camera() against a stub picamera2/libcamera — the real ones exist only on a Pi."""

from __future__ import annotations

import types
from typing import Any, ClassVar

import pytest

from docker_picamera.camera import open_camera, transform_flags
from docker_picamera.config import Config, load_config
from docker_picamera.frames import FrameBuffer


class StubCamera:
    instances: ClassVar[list[StubCamera]] = []

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.configured: dict[str, Any] = {}
        self.encoder: Any = None
        self.output: Any = None
        StubCamera.instances.append(self)

    def create_video_configuration(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def configure(self, configuration: dict[str, Any]) -> None:
        self.configured = configuration

    def start_recording(self, encoder: Any, output: Any) -> None:
        self.calls.append("start_recording")
        self.encoder, self.output = encoder, output

    def stop_recording(self) -> None:
        self.calls.append("stop_recording")

    def close(self) -> None:
        self.calls.append("close")


class StubTransform:
    def __init__(self, hflip: bool, vflip: bool) -> None:
        self.hflip, self.vflip = hflip, vflip


class StubFileOutput:
    def __init__(self, file: Any) -> None:
        self.file = file


class HardwareEncoder:
    pass


class SoftwareEncoder:
    pass


class MissingHardwareEncoder:
    def __init__(self) -> None:
        raise RuntimeError("no /dev/video11")


@pytest.fixture
def stub_picamera2(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    StubCamera.instances.clear()
    encoders = types.SimpleNamespace(MJPEGEncoder=HardwareEncoder, JpegEncoder=SoftwareEncoder)
    modules = {
        "picamera2": types.SimpleNamespace(Picamera2=StubCamera),
        "picamera2.encoders": encoders,
        "picamera2.outputs": types.SimpleNamespace(FileOutput=StubFileOutput),
        "libcamera": types.SimpleNamespace(Transform=StubTransform),
    }
    for name, module in modules.items():
        monkeypatch.setitem(__import__("sys").modules, name, module)
    return encoders


def config(**env: str) -> Config:
    return load_config({"AUTH_PASSWORD": "x", **env})


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, (False, False)),
        ({"HFLIP": "true"}, (True, False)),
        ({"ROTATE": "180"}, (True, True)),
        ({"ROTATE": "180", "HFLIP": "true"}, (False, True)),
        ({"ROTATE": "180", "HFLIP": "true", "VFLIP": "true"}, (False, False)),
    ],
)
def test_transform_flags(env: dict[str, str], expected: tuple[bool, bool]) -> None:
    assert transform_flags(config(**env)) == expected


def test_configures_size_framerate_and_transform(stub_picamera2: types.SimpleNamespace) -> None:
    with open_camera(
        config(RESOLUTION="1280x720", FRAMERATE="15", ROTATE="180", HFLIP="true"), FrameBuffer()
    ):
        camera = StubCamera.instances[0]
        assert camera.configured["main"] == {"size": (1280, 720)}
        assert camera.configured["controls"] == {"FrameRate": 15}
        transform = camera.configured["transform"]
        assert (transform.hflip, transform.vflip) == (False, True)
        assert isinstance(camera.encoder, HardwareEncoder)


def test_falls_back_to_software_jpeg(stub_picamera2: types.SimpleNamespace) -> None:
    stub_picamera2.MJPEGEncoder = MissingHardwareEncoder
    with open_camera(config(), FrameBuffer()):
        assert isinstance(StubCamera.instances[0].encoder, SoftwareEncoder)


def test_frames_written_by_the_output_reach_the_buffer(
    stub_picamera2: types.SimpleNamespace,
) -> None:
    frames = FrameBuffer()
    with open_camera(config(), frames):
        StubCamera.instances[0].output.file.write(memoryview(b"\xff\xd8jpeg\xff\xd9"))
        assert frames.wait_next(0, timeout=0) == (1, b"\xff\xd8jpeg\xff\xd9")


def test_stops_and_closes_on_exit_even_after_an_error(
    stub_picamera2: types.SimpleNamespace,
) -> None:
    with pytest.raises(KeyboardInterrupt), open_camera(config(), FrameBuffer()):
        raise KeyboardInterrupt
    assert StubCamera.instances[0].calls == ["start_recording", "stop_recording", "close"]
