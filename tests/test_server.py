from __future__ import annotations

import logging
import threading
import time

import pytest
from conftest import StartServer, credentials, read_parts

from docker_picamera.frames import FrameBuffer


def test_no_credentials_get_a_basic_challenge(start_server: StartServer) -> None:
    server = start_server()
    status, headers, _ = server.get("/index.html")
    assert status == 401
    assert headers["WWW-Authenticate"] == 'Basic realm="picamera"'


def test_wrong_credentials_are_refused(start_server: StartServer) -> None:
    server = start_server()
    status, headers, _ = server.get("/index.html", credentials(password="wrong"))
    assert status == 401
    assert headers["WWW-Authenticate"] == 'Basic realm="picamera"'


def test_unknown_path_without_credentials_is_challenged(start_server: StartServer) -> None:
    assert start_server().get("/nope")[0] == 401


def test_root_redirects_to_index(start_server: StartServer) -> None:
    status, headers, _ = start_server().get("/", credentials())
    assert status == 301
    assert headers["Location"] == "/index.html"


def test_index_embeds_the_stream_at_the_configured_size(start_server: StartServer) -> None:
    status, headers, body = start_server(width=1280, height=720).get("/index.html", credentials())
    assert status == 200
    assert headers["Content-Type"] == "text/html"
    assert b'<img src="stream.mjpg" width="1280" height="720" />' in body


def test_unknown_path_is_404(start_server: StartServer) -> None:
    assert start_server().get("/nope", credentials())[0] == 404


def test_two_clients_stream_concurrently(start_server: StartServer) -> None:
    server = start_server()
    results: dict[int, list[bytes]] = {}

    def client(index: int) -> None:
        conn = server.connect()
        conn.request("GET", "/stream.mjpg", headers=credentials())
        resp = conn.getresponse()
        assert resp.status == 200
        assert resp.getheader("Content-Type") == "multipart/x-mixed-replace; boundary=FRAME"
        assert resp.getheader("Cache-Control") == "no-cache, private"
        results[index] = read_parts(resp, 3)
        conn.close()

    threads = [threading.Thread(target=client, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(results) == [0, 1]
    for parts in results.values():
        assert all(p.startswith(b"\xff\xd8") and p.endswith(b"\xff\xd9") for p in parts)
        assert len(set(parts)) == 3, "each part is a new frame"


def test_a_disconnecting_client_does_not_stop_others(
    start_server: StartServer, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="docker_picamera.server")
    server = start_server()

    leaver = server.connect()
    leaver.request("GET", "/stream.mjpg", headers=credentials())
    read_parts(leaver.getresponse(), 1)

    stayer = server.connect()
    stayer.request("GET", "/stream.mjpg", headers=credentials())
    stayer_resp = stayer.getresponse()
    read_parts(stayer_resp, 1)

    leaver.close()
    deadline = time.monotonic() + 5
    while "Removed streaming client" not in caplog.text and time.monotonic() < deadline:
        read_parts(stayer_resp, 1)
    assert "Removed streaming client" in caplog.text
    assert len(read_parts(stayer_resp, 3)) == 3
    stayer.close()


def test_health_is_200_without_credentials_while_frames_flow(start_server: StartServer) -> None:
    server = start_server()
    deadline = time.monotonic() + 5
    while server.frames.age() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    status, _, body = server.get("/healthz")
    assert (status, body) == (200, b"ok\n")


def test_health_is_503_before_any_frame(start_server: StartServer) -> None:
    assert start_server(camera=False).get("/healthz")[0] == 503


def test_health_is_503_when_frames_are_stale(start_server: StartServer) -> None:
    now = [0.0]
    frames = FrameBuffer(clock=lambda: now[0])
    server = start_server(frames=frames, camera=False)
    frames.write(b"\xff\xd8jpeg\xff\xd9")
    now[0] = 4.9
    assert server.get("/healthz")[0] == 200
    now[0] = 5.1
    assert server.get("/healthz")[0] == 503


def test_no_auth_mode_serves_everything_without_credentials(start_server: StartServer) -> None:
    server = start_server(auth=False, title="Raspberry Pi - Surveillance Camera")
    status, _, body = server.get("/index.html")
    assert status == 200
    assert b"<title>Raspberry Pi - Surveillance Camera</title>" in body
    conn = server.connect()
    conn.request("GET", "/stream.mjpg")
    resp = conn.getresponse()
    assert resp.status == 200
    assert len(read_parts(resp, 2)) == 2
    conn.close()
