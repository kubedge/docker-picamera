import threading

from docker_picamera.frames import FrameBuffer


def test_reader_is_woken_by_a_write() -> None:
    frames = FrameBuffer()
    received: list[tuple[int, bytes] | None] = []
    reader = threading.Thread(target=lambda: received.append(frames.wait_next(0, timeout=5)))
    reader.start()
    frames.write(b"jpeg-1")
    reader.join(timeout=5)
    assert received == [(1, b"jpeg-1")]


def test_existing_frame_is_returned_immediately_to_a_new_reader() -> None:
    frames = FrameBuffer()
    frames.write(b"jpeg-1")
    frames.write(b"jpeg-2")
    assert frames.wait_next(0, timeout=0) == (2, b"jpeg-2")


def test_wait_times_out_without_a_newer_frame() -> None:
    frames = FrameBuffer()
    frames.write(b"jpeg-1")
    assert frames.wait_next(1, timeout=0.01) is None


def test_close_wakes_readers_and_ends_waits() -> None:
    frames = FrameBuffer()
    received: list[tuple[int, bytes] | None] = []
    reader = threading.Thread(target=lambda: received.append(frames.wait_next(0, timeout=5)))
    reader.start()
    frames.close()
    reader.join(timeout=5)
    assert received == [None]
    assert frames.closed
    frames.write(b"late")
    assert frames.wait_next(0, timeout=0) is None


def test_age_is_none_before_the_first_frame_then_tracks_the_clock() -> None:
    now = [100.0]
    frames = FrameBuffer(clock=lambda: now[0])
    assert frames.age() is None
    frames.write(b"jpeg")
    now[0] = 103.5
    assert frames.age() == 3.5
