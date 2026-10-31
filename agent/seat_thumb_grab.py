"""Persistent seat thumbnail grabber (`/usr/bin/python3 seat_thumb_grab.py <bus-addr>`).

Needs dbus-python + PyGObject, which the agent venv lacks, so seat_thumb runs
this under the system interpreter and keeps it alive.

Protocol: one Mutter ScreenCast session is created at start and never Stopped
(ending a session froze gnome-shell 25-75 s on GNOME 50, 2026-10-31; Mutter
cleans up when this process exits). For each stdin line `grab\\n` it writes a
4-byte big-endian length + one 640x360 JPEG to stdout (length 0 = failure).
Exits on stdin EOF, non-zero if Mutter closed the session or the PipeWire node
is gone. Never calls the xdg-desktop-portal Screenshot API (it froze the seat).
"""
import struct
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def _frame(node, tmp: Path) -> bytes:
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
    data = tmp.read_bytes() if tmp.exists() else b""
    return data if data[:3] == b"\xff\xd8\xff" else b""


def _open(bus_addr: str):
    """-> (PipeWire node or None, closed-flag dict)."""
    import dbus
    import dbus.bus
    import dbus.mainloop.glib
    from gi.repository import GLib
    bus = dbus.bus.BusConnection(bus_addr, mainloop=dbus.mainloop.glib.DBusGMainLoop())
    # st holds the bus: a collected BusConnection closes, and Mutter then ends
    # the session ("D-Bus client with active sessions vanished"), node gone.
    name, loop, st = "org.gnome.Mutter.ScreenCast", GLib.MainLoop(), {"bus": bus}
    sc = dbus.Interface(bus.get_object(name, "/org/gnome/Mutter/ScreenCast"), name)
    ses = dbus.Interface(bus.get_object(name, sc.CreateSession({})), name + ".Session")
    stream = bus.get_object(name, ses.RecordMonitor("", {"cursor-mode": dbus.UInt32(0)}))

    def added(node):
        st["node"] = node
        loop.quit()
    stream.connect_to_signal("PipeWireStreamAdded", added, dbus_interface=name + ".Stream")
    ses.connect_to_signal("Closed", lambda: st.update(closed=True))
    ses.Start()
    GLib.timeout_add_seconds(10, loop.quit)
    loop.run()
    return st.get("node"), st


def main(bus_addr: str) -> int:
    from gi.repository import GLib
    node, st = _open(bus_addr)
    if node is None:
        return 1
    out, ctx = sys.stdout.buffer, GLib.MainContext.default()
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "thumb.jpg"
        for line in sys.stdin:
            if line.strip() != "grab":
                continue
            while ctx.iteration(False):   # deliver a pending Closed signal
                pass
            if st.get("closed"):
                return 1
            tmp.unlink(missing_ok=True)
            jpeg = _frame(node, tmp)
            out.write(struct.pack(">I", len(jpeg)) + jpeg)
            out.flush()
            if not jpeg:   # node gone: let the agent restart us
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
