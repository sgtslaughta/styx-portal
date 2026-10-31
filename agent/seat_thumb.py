"""Seat thumbnail: grab one frame of the GNOME seat via Mutter ScreenCast and
PipeWire, upload it to the portal as a 640x360 JPEG (at most once a minute)."""
import os
import subprocess
import threading
import time
from pathlib import Path

from portal_api import api_post_bytes

INTERVAL_S = 60
_last = 0.0
_busy = False


# One ScreenCast session for the agent's life: ending a Mutter screencast
# session froze gnome-shell 25-75 s on GNOME 50 (2026-10-31), so it is only
# replaced when the seat bus changes (seat restart) or Mutter closes it.
_cast: dict = {}


def _node(bus_addr: str):
    """PipeWire node of the live seat screencast, creating the session on demand."""
    import dbus
    import dbus.bus
    import dbus.mainloop.glib
    from gi.repository import GLib
    ctx = GLib.MainContext.default()
    while ctx.iteration(False):   # deliver a pending Closed signal
        pass
    if _cast.get("addr") == bus_addr and _cast.get("node") is not None:
        return _cast["node"]
    _cast.clear()
    bus = dbus.bus.BusConnection(bus_addr, mainloop=dbus.mainloop.glib.DBusGMainLoop())
    name, loop = "org.gnome.Mutter.ScreenCast", GLib.MainLoop()
    sc = dbus.Interface(bus.get_object(name, "/org/gnome/Mutter/ScreenCast"), name)
    ses = dbus.Interface(bus.get_object(name, sc.CreateSession({})), name + ".Session")
    stream = bus.get_object(name, ses.RecordMonitor("", {"cursor-mode": dbus.UInt32(0)}))

    def added(node):
        _cast["node"] = node
        loop.quit()
    stream.connect_to_signal("PipeWireStreamAdded", added, dbus_interface=name + ".Stream")
    ses.connect_to_signal("Closed", lambda: _cast.update(node=None))
    _cast.update(addr=bus_addr, bus=bus, ses=ses)
    ses.Start()
    GLib.timeout_add_seconds(10, loop.quit)
    loop.run()
    return _cast.get("node")


def capture(out: Path, bus_addr: str) -> bool:
    """One 640x360 JPEG frame of the seat to `out`."""
    node = _node(bus_addr)
    if node is None:
        return False
    tmp = out.with_name(out.name + ".tmp")
    tmp.unlink(missing_ok=True)
    gst = subprocess.Popen(
        ["gst-launch-1.0", "-q", "pipewiresrc", f"path={node}", "num-buffers=1", "!",
         "videoconvert", "!", "videoscale", "!", "video/x-raw,width=640,height=360", "!",
         "jpegenc", "quality=80", "!", "filesink", f"location={tmp}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:   # pipewiresrc never EOSes: stop as soon as the file has bytes
        end = time.monotonic() + 10
        while time.monotonic() < end and not (tmp.exists() and tmp.stat().st_size > 0):
            time.sleep(0.05)
        time.sleep(0.1)   # let jpegenc finish the write
    finally:
        gst.kill()
        gst.wait()
    if tmp.exists() and tmp.read_bytes()[:3] == b"\xff\xd8\xff":
        os.replace(tmp, out)
        return True
    tmp.unlink(missing_ok=True)
    return False


def upload(cfg: dict, data: bytes) -> None:
    api_post_bytes(cfg, "/api/agent/thumbnail", data, "image/jpeg")


def _run(cfg: dict) -> None:
    global _busy
    try:
        install = Path(cfg["install_dir"])
        out = install / "seat-thumb.jpg"
        if capture(out, (install / "gnome-bus.addr").read_text().strip()):
            upload(cfg, out.read_bytes())
    except Exception as e:  # noqa: BLE001 - a thumbnail must never hurt the supervisor
        print(f"seat thumbnail failed: {e}", flush=True)
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
