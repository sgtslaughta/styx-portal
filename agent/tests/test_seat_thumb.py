import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import seat_thumb  # noqa: E402


def _run(cfg, now):
    started = []

    class T:
        def __init__(self, target, args, daemon):
            self.target = target

        def start(self):
            started.append(1)

    with patch.object(seat_thumb.threading, "Thread", T), \
            patch.object(seat_thumb.time, "monotonic", return_value=now):
        seat_thumb.on_heartbeat(cfg)
    return started


def test_on_heartbeat_throttles_to_60s():
    seat_thumb._last = 0.0
    seat_thumb._busy = False
    assert _run({}, 1000.0) == [1]
    seat_thumb._busy = False   # capture finished
    assert _run({}, 1030.0) == []
    assert _run({}, 1061.0) == [1]
    seat_thumb._busy = False


def test_on_heartbeat_skips_while_busy():
    seat_thumb._last = 0.0
    seat_thumb._busy = True
    assert _run({}, 5000.0) == []
    seat_thumb._busy = False


def test_upload_posts_jpeg_bytes():
    with patch.object(seat_thumb, "api_post_bytes") as p:
        seat_thumb.upload({"a": 1}, b"\xff\xd8\xff")
    p.assert_called_once_with({"a": 1}, "/api/agent/thumbnail", b"\xff\xd8\xff", "image/jpeg")


def test_on_heartbeat_never_raises():
    seat_thumb._last = 0.0
    with patch.object(seat_thumb.threading, "Thread", side_effect=RuntimeError):
        seat_thumb.on_heartbeat({})
    seat_thumb._busy = False
