"""rust-streamer requirements that only the rpicam-vid supervisor has."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from httphelp import credentials, read_parts
from service import Start


@pytest.fixture
def impl() -> str:  # overrides the two-implementation parameter: rust only
    from service import RUST_BIN

    if not RUST_BIN.exists():
        if os.environ.get("REQUIRE_RUST") == "1":
            pytest.fail(f"REQUIRE_RUST=1 but {RUST_BIN} is not built")
        pytest.skip("rust binary not built (cargo build in rust/)")
    return "rust"


def test_camera_process_death_exits_non_zero(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "x", "FAKECAM_EXIT_AFTER": "3"})
    assert service.proc.wait(10) != 0
    assert "camera process exited" in service.stderr()


def test_garbage_between_frames_yields_only_complete_jpegs(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "FAKECAM_GARBAGE": "1"})
    conn = service.connect()
    conn.request("GET", "/stream.mjpg", headers=credentials())
    parts = read_parts(conn.getresponse(), 4)
    conn.close()
    assert all(p.startswith(b"\xff\xd8") and p.endswith(b"\xff\xd9") for p in parts)
    assert not any(b"garbage" in p for p in parts)


def test_sigterm_terminates_the_camera_process(start: Start, tmp_path: Path) -> None:
    pid_file = tmp_path / "rpicam.pid"
    service = start({"AUTH_PASSWORD": "x", "FAKECAM_PID_FILE": str(pid_file)})
    deadline = time.monotonic() + 5
    while not pid_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    child = int(pid_file.read_text())
    assert service.stop() == 0
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    pytest.fail(f"rpicam-vid {child} still running after shutdown")


def test_camera_settings_reach_rpicam_vid(start: Start, tmp_path: Path) -> None:
    argv_file = tmp_path / "argv.json"
    env = {
        "AUTH_PASSWORD": "x",
        "FAKECAM_ARGV_FILE": str(argv_file),
        "RESOLUTION": "1280x720",
        "FRAMERATE": "15",
        "ROTATE": "180",
        "HFLIP": "true",
    }
    start(env)
    deadline = time.monotonic() + 5
    while not argv_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    argv = json.loads(argv_file.read_text())
    joined = " ".join(argv)
    assert "--codec mjpeg" in joined
    assert "--width 1280 --height 720 --framerate 15" in joined
    assert "--hflip" in argv and "--vflip" not in argv
    assert "--rotation 180" in joined
    assert argv[-2:] == ["-o", "-"]


# --- encoder selection (rust-streamer "Encoder selection", "JPEG quality") ---------------


def argv_of(start: Start, tmp_path: Path, env: dict[str, str]) -> list[str]:
    argv_file = tmp_path / "argv.json"
    start({"AUTH_PASSWORD": "x", "FAKECAM_ARGV_FILE": str(argv_file), **env})
    deadline = time.monotonic() + 5
    while not argv_file.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    return list(json.loads(argv_file.read_text()))


def test_default_encoder_is_software_and_unchanged(start: Start, tmp_path: Path) -> None:
    argv = argv_of(start, tmp_path, {})
    assert "--codec" in argv and argv[argv.index("--codec") + 1] == "mjpeg"
    assert "--quality" not in argv


def test_jpeg_quality_reaches_the_software_encoder(start: Start, tmp_path: Path) -> None:
    argv = argv_of(start, tmp_path, {"JPEG_QUALITY": "85"})
    assert argv[argv.index("--quality") + 1] == "85"


def test_auto_without_encoder_streams_with_software(start: Start, tmp_path: Path) -> None:
    sysfs = tmp_path / "sysfs"
    sysfs.mkdir()
    service = start(
        {"AUTH_PASSWORD": "s3cret", "ENCODER": "auto", "PICAMERA_V4L2_SYSFS": str(sysfs)}
    )
    conn = service.connect()
    conn.request("GET", "/stream.mjpg", headers=credentials())
    parts = read_parts(conn.getresponse(), 2)
    conn.close()
    assert all(p.startswith(b"\xff\xd8") for p in parts)
    assert service.wait_for_log("hardware JPEG encoder not found; using software")
    assert service.wait_for_log("encoder=software")


def fake_sysfs_with_encoder(tmp_path: Path) -> Path:
    sysfs = tmp_path / "sysfs"
    (sysfs / "video99").mkdir(parents=True)
    (sysfs / "video99" / "name").write_text("bcm2835-codec-encode_image\n")
    return sysfs  # names /dev/video99, which does not exist: present but unusable


def test_auto_with_unusable_encoder_falls_back(start: Start, tmp_path: Path) -> None:
    sysfs = fake_sysfs_with_encoder(tmp_path)
    service = start(
        {"AUTH_PASSWORD": "s3cret", "ENCODER": "auto", "PICAMERA_V4L2_SYSFS": str(sysfs)}
    )
    assert service.wait_for_log("hardware JPEG encoder unusable")
    assert service.wait_for_log("encoder=software")


def test_hardware_without_encoder_exits_non_zero(start: Start, tmp_path: Path) -> None:
    sysfs = tmp_path / "sysfs"
    sysfs.mkdir()
    service = start(
        {"AUTH_PASSWORD": "x", "ENCODER": "hardware", "PICAMERA_V4L2_SYSFS": str(sysfs)},
        wait=False,
    )
    assert service.proc.wait(10) == 1
    assert "error: camera: hardware JPEG encoder not found" in service.stderr()


def test_hardware_with_unusable_encoder_exits_non_zero(start: Start, tmp_path: Path) -> None:
    sysfs = fake_sysfs_with_encoder(tmp_path)
    service = start(
        {"AUTH_PASSWORD": "x", "ENCODER": "hardware", "PICAMERA_V4L2_SYSFS": str(sysfs)},
        wait=False,
    )
    assert service.proc.wait(10) == 1
    assert "error: camera: hardware JPEG encoder:" in service.stderr()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ENCODER", "gpu", "ENCODER: expected software, hardware or auto, got 'gpu'"),
        ("JPEG_QUALITY", "0", "JPEG_QUALITY: expected an integer from 1 to 100, got '0'"),
    ],
)
def test_bad_encoder_settings_exit_2(start: Start, name: str, value: str, message: str) -> None:
    service = start({"AUTH_PASSWORD": "x", name: value}, wait=False)
    assert service.proc.wait(10) == 2
    assert f"error: {message}" in service.stderr()
