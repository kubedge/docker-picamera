"""The latest camera frame, shared by every streaming client."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class FrameBuffer:
    """Holds the newest JPEG. Readers wait by sequence number, so none misses a wake-up;
    a slow reader skips frames instead of queueing them."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._condition = threading.Condition()
        self._frame = b""
        self._sequence = 0
        self._produced_at: float | None = None
        self._closed = False

    def write(self, frame: bytes) -> int:
        """Publish one complete JPEG frame (the camera's sink)."""
        with self._condition:
            self._frame = frame
            self._sequence += 1
            self._produced_at = self._clock()
            self._condition.notify_all()
        return len(frame)

    def wait_next(self, after: int, timeout: float) -> tuple[int, bytes] | None:
        """Return (sequence, frame) for the first frame newer than `after`, or None on
        timeout or once the buffer is closed."""
        with self._condition:
            ready = self._condition.wait_for(
                lambda: self._closed or self._sequence > after, timeout
            )
            if not ready or self._closed:
                return None
            return self._sequence, self._frame

    def age(self) -> float | None:
        """Seconds since the last frame, or None before the first one."""
        with self._condition:
            if self._produced_at is None:
                return None
            return self._clock() - self._produced_at

    def close(self) -> None:
        """Wake every waiting reader and make later waits return None."""
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed
