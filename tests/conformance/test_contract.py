"""camera-streaming requirements, checked identically against both implementations."""

from __future__ import annotations

import threading
import time

from httphelp import credentials, read_parts
from service import Start


def wait_status(service, path: str, want: int, timeout: float) -> bool:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if service.get(path)[0] == want:
            return True
        time.sleep(0.1)
    return False


# --- configuration ---------------------------------------------------------------------


def test_missing_password_exits_2(start: Start) -> None:
    service = start({}, wait=False)
    assert service.proc.wait(10) == 2
    assert "error: AUTH_PASSWORD: must be set to a non-empty value" in service.stderr()


def test_unsupported_rotation_exits_2(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "x", "ROTATE": "90"}, wait=False)
    assert service.proc.wait(10) == 2
    assert "error: ROTATE: only 0 and 180 are supported, got '90'" in service.stderr()


def test_malformed_resolution_exits_2(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "x", "RESOLUTION": "800by600"}, wait=False)
    assert service.proc.wait(10) == 2
    assert "RESOLUTION: expected <width>x<height> with positive integers, got '800by600'" in (
        service.stderr()
    )


# --- authentication --------------------------------------------------------------------


def test_no_credentials_get_a_basic_challenge(start: Start) -> None:
    status, headers, _ = start().get("/index.html")
    assert status == 401
    assert headers["www-authenticate"] == 'Basic realm="picamera"'


def test_wrong_credentials_are_refused(start: Start) -> None:
    status, headers, _ = start().get("/index.html", credentials(password="wrong"))
    assert status == 401
    assert headers["www-authenticate"] == 'Basic realm="picamera"'


def test_unknown_path_without_credentials_is_challenged(start: Start) -> None:
    assert start().get("/nope")[0] == 401


def test_custom_username(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "AUTH_USERNAME": "cam"})
    assert service.get("/index.html", credentials("cam", "s3cret"))[0] == 200
    assert service.get("/index.html", credentials("pi", "s3cret"))[0] == 401


# --- routes ------------------------------------------------------------------------------


def test_root_redirects_to_index(start: Start) -> None:
    status, headers, _ = start().get("/", credentials())
    assert status == 301
    assert headers["location"] == "/index.html"


def test_index_embeds_the_stream_at_the_configured_size(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "RESOLUTION": "1280x720"})
    status, headers, body = service.get("/index.html", credentials())
    assert status == 200
    assert headers["content-type"] == "text/html"
    assert b'<img src="stream.mjpg" width="1280" height="720" />' in body
    assert b"<title>picamera MJPEG streaming demo</title>" in body


def test_unknown_path_is_404(start: Start) -> None:
    assert start().get("/nope", credentials())[0] == 404


# --- stream ------------------------------------------------------------------------------


def test_two_clients_stream_concurrently(start: Start) -> None:
    service = start()
    results: dict[int, list[bytes]] = {}

    def client(index: int) -> None:
        conn = service.connect()
        conn.request("GET", "/stream.mjpg", headers=credentials())
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "multipart/x-mixed-replace; boundary=FRAME"
        assert resp.getheader("Cache-Control") == "no-cache, private"
        assert resp.getheader("Pragma") == "no-cache"
        results[index] = read_parts(resp, 3)
        conn.close()

    threads = [threading.Thread(target=client, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=15)
    assert sorted(results) == [0, 1]
    for parts in results.values():
        assert all(p.startswith(b"\xff\xd8") and p.endswith(b"\xff\xd9") for p in parts)
        assert len(set(parts)) == 3, "each part is a new frame"


def test_a_disconnecting_client_does_not_stop_others(start: Start) -> None:
    service = start()
    leaver = service.connect()
    leaver.request("GET", "/stream.mjpg", headers=credentials())
    read_parts(leaver.getresponse(), 1)
    stayer = service.connect()
    stayer.request("GET", "/stream.mjpg", headers=credentials())
    stayer_resp = stayer.getresponse()
    read_parts(stayer_resp, 1)

    leaver.close()
    deadline = time.monotonic() + 5
    while "Removed streaming client" not in service.stderr() and time.monotonic() < deadline:
        read_parts(stayer_resp, 1)
    assert "Removed streaming client" in service.stderr()
    assert len(read_parts(stayer_resp, 3)) == 3
    stayer.close()


# --- health ------------------------------------------------------------------------------


def test_health_is_200_without_credentials_while_frames_flow(start: Start) -> None:
    service = start()
    assert wait_status(service, "/healthz", 200, timeout=5)
    status, headers, body = service.get("/healthz")
    assert (status, body) == (200, b"ok\n")
    assert headers["content-type"] == "text/plain"


def test_health_is_503_before_any_frame(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "FAKECAM_FRAMES": "0"})
    time.sleep(0.5)
    status, _, body = service.get("/healthz")
    assert (status, body) == (503, b"no recent frame\n")


def test_health_turns_503_when_frames_stop(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "s3cret", "FAKECAM_FRAMES": "3"})
    assert wait_status(service, "/healthz", 200, timeout=5)
    assert wait_status(service, "/healthz", 503, timeout=8)


# --- example mode and shutdown ----------------------------------------------------------


def test_example_mode_needs_no_credentials(start: Start) -> None:
    service = start({}, example=True)
    status, _, body = service.get("/index.html")
    assert status == 200
    assert b"<title>Raspberry Pi - Surveillance Camera</title>" in body
    assert b'width="640" height="480"' in body
    conn = service.connect()
    conn.request("GET", "/stream.mjpg")
    resp = conn.getresponse()
    assert resp.status == 200
    assert len(read_parts(resp, 2)) == 2
    conn.close()


def test_sigterm_exits_0(start: Start) -> None:
    service = start()
    assert wait_status(service, "/healthz", 200, timeout=5)
    assert service.stop() == 0
    assert "received SIGTERM, shutting down" in service.stderr()
    assert "stopped" in service.stderr()


def test_sigterm_with_a_stream_client_connected_exits_0(start: Start) -> None:
    service = start()
    conn = service.connect()
    conn.request("GET", "/stream.mjpg", headers=credentials())
    read_parts(conn.getresponse(), 1)
    assert service.stop() == 0
    conn.close()


def test_bad_port_exits_2(start: Start) -> None:
    service = start({"AUTH_PASSWORD": "x", "PORT": "0"}, wait=False)
    assert service.proc.wait(10) == 2
    assert "error: PORT: expected a port number 1-65535, got '0'" in service.stderr()
