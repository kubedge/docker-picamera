"""Fixtures for the conformance suite; see service.py."""

from __future__ import annotations

import os
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from service import FIXTURES, RUST_BIN, SCRUBBED, Service, Start, command, free_port


@pytest.fixture(params=["python", "rust"])
def impl(request: pytest.FixtureRequest) -> str:
    if request.param == "rust" and not RUST_BIN.exists():
        if os.environ.get("REQUIRE_RUST") == "1":
            pytest.fail(f"REQUIRE_RUST=1 but {RUST_BIN} is not built")
        pytest.skip("rust binary not built (cargo build in rust/)")
    return str(request.param)


@pytest.fixture
def start(impl: str, tmp_path: Path) -> Iterator[Start]:
    services: list[Service] = []

    def _start(
        env: dict[str, str] | None = None, *, example: bool = False, wait: bool = True
    ) -> Service:
        port = free_port()
        full = {k: v for k, v in os.environ.items() if k not in SCRUBBED}
        full.update(
            PORT=str(port),
            PYTHONPATH=os.pathsep.join([str(FIXTURES / "fakecam"), full.get("PYTHONPATH", "")]),
            RPICAM_VID=str(FIXTURES / "fake-rpicam-vid"),
            PYTHONUNBUFFERED="1",
        )
        full.update({"AUTH_PASSWORD": "s3cret"} if env is None else env)
        log = tmp_path / f"service-{len(services)}.log"
        with log.open("wb") as sink:
            proc = subprocess.Popen(
                command(impl, example), env=full, stdout=sink, stderr=subprocess.STDOUT
            )
        service = Service(proc, port, log)
        services.append(service)
        if wait:
            deadline = time.monotonic() + 10
            while True:
                if proc.poll() is not None:
                    raise AssertionError(f"service exited {proc.returncode}:\n{service.stderr()}")
                try:
                    socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                    break
                except OSError:
                    if time.monotonic() > deadline:
                        raise AssertionError(f"not listening:\n{service.stderr()}") from None
                    time.sleep(0.05)
        return service

    yield _start
    for service in services:
        if service.proc.poll() is None:
            service.proc.kill()
            service.proc.wait(5)
