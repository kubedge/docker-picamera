"""Stand-in for picamera2 (conformance tests only): writes fake JPEGs to the output at the
configured frame rate, so docker-picamera runs as a black box off a Pi."""

import threading
from typing import Any

from _fakeframes import frame_limit, jpeg


class Picamera2:
    def __init__(self) -> None:
        self._fps = 24
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def create_video_configuration(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def configure(self, configuration: dict[str, Any]) -> None:
        self._fps = configuration.get("controls", {}).get("FrameRate", 24)

    def start_recording(self, encoder: Any, output: Any) -> None:
        def produce() -> None:
            n, limit = 0, frame_limit()
            while not self._stop.wait(1 / self._fps):
                if limit is not None and n >= limit:
                    continue
                n += 1
                output.file.write(jpeg(n))

        self._thread = threading.Thread(target=produce, daemon=True)
        self._thread.start()

    def stop_recording(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    def close(self) -> None:
        pass
