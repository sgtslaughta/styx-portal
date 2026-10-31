import os
import struct
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

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


def _cfg(tmp_path, bus="unix:path=/x/bus"):
    (tmp_path / "gnome-bus.addr").write_text(bus + "\n")
    return {"install_dir": str(tmp_path)}


class _P:
    """Fake helper: stdout is a real pipe preloaded with `replies`."""

    def __init__(self, replies=()):
        r, w = os.pipe()
        for x in replies:
            os.write(w, x)
        self.stdout = os.fdopen(r, "rb", 0)
        self._w = w
        self.stdin = MagicMock()
        self.dead = self.killed = False

    def poll(self):
        return 1 if self.dead else None

    def kill(self):
        self.killed = True

    def wait(self):
        pass


def _reply(jpeg=b"\xff\xd8\xff!"):
    return struct.pack(">I", len(jpeg)) + jpeg


@pytest.fixture(autouse=True)
def _reset():
    seat_thumb._proc = seat_thumb._proc_bus = None
    yield
    seat_thumb._proc = seat_thumb._proc_bus = None


def _popen(*procs):
    return patch.object(seat_thumb.subprocess, "Popen", side_effect=list(procs))


def test_helper_launch_and_reuse(tmp_path):
    p = _P([_reply(), _reply()])
    with _popen(p) as po:
        assert seat_thumb.capture(tmp_path, "b1") == b"\xff\xd8\xff!"
        assert seat_thumb.capture(tmp_path, "b1") == b"\xff\xd8\xff!"
    assert po.call_count == 1
    assert po.call_args.args[0] == ["/usr/bin/python3", str(tmp_path / "seat_thumb_grab.py"), "b1"]
    assert po.call_args.kwargs["env"]["DBUS_SESSION_BUS_ADDRESS"] == "b1"
    assert p.stdin.write.call_args_list == [call(b"grab\n")] * 2


def test_restart_after_death(tmp_path):
    a, b = _P([_reply()]), _P([_reply()])
    with _popen(a, b) as po:
        seat_thumb.capture(tmp_path, "b1")
        a.dead = True
        seat_thumb.capture(tmp_path, "b1")
    assert po.call_count == 2 and a.killed


def test_restart_on_bus_change(tmp_path):
    a, b = _P([_reply()]), _P([_reply()])
    with _popen(a, b) as po:
        seat_thumb.capture(tmp_path, "b1")
        seat_thumb.capture(tmp_path, "b2")
    assert a.killed and po.call_count == 2 and not b.killed


def test_timeout_kills_helper(tmp_path):
    p = _P()   # never replies
    with _popen(p), patch.object(seat_thumb, "TIMEOUT_S", 0.2), pytest.raises(TimeoutError):
        seat_thumb.capture(tmp_path, "b1")
    assert p.killed and seat_thumb._proc is None


def test_short_read_kills_helper(tmp_path):
    p = _P([struct.pack(">I", 100) + b"\xff\xd8"])
    os.close(p._w)   # EOF after a partial frame
    with _popen(p), pytest.raises(EOFError):
        seat_thumb.capture(tmp_path, "b1")
    assert p.killed


def test_run_uploads_on_success(tmp_path):
    with _popen(_P([_reply()])), patch.object(seat_thumb, "api_post_bytes") as up:
        seat_thumb._run(_cfg(tmp_path))
    assert up.call_args.args[2] == b"\xff\xd8\xff!"


def test_length_zero_no_upload(tmp_path):
    p = _P([_reply(b"")])
    with _popen(p), patch.object(seat_thumb, "api_post_bytes") as up:
        seat_thumb._run(_cfg(tmp_path))
    assert not up.called and not p.killed


def test_run_failure_logs_one_line(tmp_path, capsys):
    p = _P()
    with _popen(p), patch.object(seat_thumb, "TIMEOUT_S", 0.1), \
            patch.object(seat_thumb, "api_post_bytes") as up:
        seat_thumb._run(_cfg(tmp_path))
    assert p.killed and not up.called
    assert capsys.readouterr().out.startswith("seat thumbnail failed: TimeoutError")
    assert seat_thumb._busy is False
