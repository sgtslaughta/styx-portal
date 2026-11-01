"""Seat thumbnail: grab one frame of the GNOME seat via Mutter ScreenCast and
PipeWire, upload it to the portal as a 1280-wide JPEG (at most once a minute).

The grab needs dbus/GLib, so it runs in a long-lived helper under the system
interpreter (seat_thumb_grab.py; protocol in its docstring); the agent venv has
neither. The helper keeps one ScreenCast session open: ending a session froze
gnome-shell 25-75 s on GNOME 50, so it is never Stopped per grab."""
import os
import select
import struct
import subprocess
import threading
import time
from pathlib import Path

from portal_api import api_post_bytes

INTERVAL_S = 60
TIMEOUT_S = 20
SYS_PYTHON = "/usr/bin/python3"
_last = 0.0
_busy = False


_proc = None
_proc_bus = None
# Every helper start ends with a session teardown (the 25-75 s freeze above), so a
# helper that keeps dying must not be restarted every minute: give up after
# MAX_STARTS per seat bus; a seat restart (new bus) resets the count.
MAX_STARTS = 3
_starts = 0
_gaveup_logged = False   # GaveUp repeats every minute; log it once per seat bus


class GaveUp(RuntimeError):
    pass


def _kill() -> None:
    global _proc
    p, _proc = _proc, None
    if p is not None:
        p.kill()
        p.wait()


def _helper(install: Path, bus_addr: str):
    """The live grabber, (re)started only if dead or the seat bus changed."""
    global _proc, _proc_bus, _starts, _gaveup_logged
    if _proc_bus != bus_addr:
        _starts, _gaveup_logged = 0, False
    if _proc is not None and (_proc.poll() is not None or _proc_bus != bus_addr):
        _kill()
    if _proc is None:
        if _starts >= MAX_STARTS:
            _proc_bus = bus_addr
            raise GaveUp(f"grabber failed {_starts}x on this seat; off until seat restart")
        _starts += 1
        env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=bus_addr)
        _proc = subprocess.Popen([SYS_PYTHON, str(install / "seat_thumb_grab.py"), bus_addr],
                                 env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, bufsize=0)
        _proc_bus = bus_addr
    return _proc


def _read(p, n: int, end: float) -> bytes:
    fd, buf = p.stdout.fileno(), b""
    while len(buf) < n:
        left = end - time.monotonic()
        if left <= 0 or not select.select([fd], [], [], left)[0]:
            raise TimeoutError("grabber timed out")
        chunk = os.read(fd, n - len(buf))
        if not chunk:
            raise EOFError("grabber closed")
        buf += chunk
    return buf


def capture(install: Path, bus_addr: str) -> bytes:
    """One JPEG frame of the seat (b"" on failure). Timeout/short read kills the helper."""
    p = _helper(install, bus_addr)
    try:
        p.stdin.write(b"grab\n")
        end = time.monotonic() + TIMEOUT_S
        (n,) = struct.unpack(">I", _read(p, 4, end))
        jpeg = _read(p, n, end) if n else b""
    except BaseException:
        _kill()
        raise
    return jpeg if jpeg[:3] == b"\xff\xd8\xff" else b""


def upload(cfg: dict, data: bytes) -> None:
    api_post_bytes(cfg, "/api/agent/thumbnail", data, "image/jpeg")


def _run(cfg: dict) -> None:
    global _busy, _gaveup_logged
    try:
        install = Path(cfg["install_dir"])
        jpeg = capture(install, (install / "gnome-bus.addr").read_text().strip())
        if jpeg:
            upload(cfg, jpeg)
    except GaveUp as e:
        if not _gaveup_logged:
            _gaveup_logged = True
            print(f"seat thumbnail off: {e}", flush=True)
    except Exception as e:  # noqa: BLE001 - a thumbnail must never hurt the supervisor
        print(f"seat thumbnail failed: {type(e).__name__}: {e}", flush=True)
    finally:
        _busy = False


def on_heartbeat(cfg: dict) -> None:
    """Supervisor hook: capture+upload in a daemon thread, one at a time."""
    global _last, _busy
    try:
        now = time.monotonic()
        if _busy or now - _last < INTERVAL_S:
            return
        _last, _busy = now, True
        threading.Thread(target=_run, args=(cfg,), daemon=True).start()
    except Exception as e:  # noqa: BLE001
        _busy = False
        print(f"seat thumbnail skipped: {e}", flush=True)
