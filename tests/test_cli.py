from __future__ import annotations

import http.client
import os
import signal
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from conftest import credentials, fake_jpeg

from docker_picamera import cli
from docker_picamera.config import Config
from docker_picamera.frames import FrameBuffer


def test_missing_password_exits_2_without_touching_the_camera(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AUTH_PASSWORD", raising=False)
    monkeypatch.delitem(sys.modules, "picamera2", raising=False)
    assert cli.main() == 2
    assert capsys.readouterr().err.startswith("error: AUTH_PASSWORD: ")
    assert "picamera2" not in sys.modules


def test_bad_setting_exits_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("AUTH_PASSWORD", "x")
    monkeypatch.setenv("ROTATE", "90")
    assert cli.main() == 2
    assert "ROTATE: only 0 and 180 are supported" in capsys.readouterr().err


def test_sigterm_releases_the_camera_and_returns_0(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "LISTEN_PORT", 0)
    events: list[str] = []
    started = threading.Event()

    @contextmanager
    def fake_camera(config: Config, frames: FrameBuffer) -> Iterator[None]:
        events.append("open")
        frames.write(fake_jpeg(1))
        started.set()
        try:
            yield
        finally:
            events.append("close")

    def send_sigterm() -> None:
        started.wait(timeout=5)
        os.kill(os.getpid(), signal.SIGTERM)

    before = signal.getsignal(signal.SIGTERM)
    threading.Timer(0.2, send_sigterm).start()
    status = cli.serve(
        Config("pi", "x", 800, 600, 24, 0, False, False),
        title="t",
        heading="t",
        auth=b"Basic x",
        camera=fake_camera,
    )
    assert status == 0
    assert events == ["open", "close"]
    assert signal.getsignal(signal.SIGTERM) is before


def test_serves_on_all_interfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "LISTEN_PORT", 0)
    bound: list[tuple[str, int]] = []
    probed: list[int] = []

    @contextmanager
    def fake_camera(config: Config, frames: FrameBuffer) -> Iterator[None]:
        frames.write(fake_jpeg(1))
        yield

    original = cli.StreamingServer

    class Recording(original):
        def server_activate(self) -> None:
            super().server_activate()
            bound.append(self.server_address)
            threading.Thread(target=self._probe_then_stop, daemon=True).start()

        def _probe_then_stop(self) -> None:
            conn = http.client.HTTPConnection("127.0.0.1", self.server_address[1], timeout=5)
            conn.request("GET", "/index.html", headers=credentials("pi", "x"))
            probed.append(conn.getresponse().status)
            conn.close()
            self.shutdown()

    monkeypatch.setattr(cli, "StreamingServer", Recording)
    status = cli.serve(
        Config("pi", "x", 800, 600, 24, 0, False, False),
        title="t",
        heading="t",
        auth=b"Basic " + credentials("pi", "x")["Authorization"].split()[1].encode(),
        camera=fake_camera,
    )
    assert status == 0
    assert bound[0][0] == "0.0.0.0"
    assert probed == [200]


def test_off_a_pi_the_camera_error_is_one_line_and_exit_1(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setitem(sys.modules, "libcamera", None)  # forces ImportError
    monkeypatch.setenv("AUTH_PASSWORD", "x")
    assert cli.main() == 1
    assert capsys.readouterr().err.startswith(
        "error: camera: picamera2/libcamera are not importable"
    )
