"""Styx GNOME seat helper (runs with the SYSTEM python3: dbus-python, PyGObject
and GStreamer's pipewiresrc). Only ever run on the seat's private session bus.

1. Portal backend `org.freedesktop.impl.portal.desktop.styx`: ScreenCast and
   RemoteDesktop implemented on Mutter's own D-Bus APIs, so there is no consent
   dialog. The cursor travels as metadata and the browser draws it (no lag).
2. Holds the seat's virtual monitor at WxH (argv[1]) via Mutter RecordVirtual
   plus a fakesink consumer whose caps fix the size. A new size means a new
   process: renegotiating caps in place stalls frames.
3. Once Mutter reports that monitor current, starts xdg-desktop-portal
   --replace (it reads XDG_DESKTOP_PORTAL_DIR) and writes WxH to
   $STYX_PORTAL_READY.
4. Serves the seat's clipboard (all flavours) to selkies via seat_clipboard.py
   on the RemoteDesktop session (Mutter has no wlr/ext data-control)."""
import os
import signal
import subprocess
import sys
import time

import dbus
import dbus.bus
import dbus.service
import gi
from dbus.mainloop.glib import DBusGMainLoop

gi.require_version("Gst", "1.0")
from gi.repository import GLib, Gst  # noqa: E402

from seat_clipboard import ClipboardServer  # noqa: E402
from seat_scale import apply_scale, read_scale  # noqa: E402
import seat_systemd  # noqa: E402
from seat_systemd import SD_NAME, SystemdStub, snap_scope_props  # noqa: E402, F401

BUS_NAME = "org.freedesktop.impl.portal.desktop.styx"
PATH = "/org/freedesktop/portal/desktop"
SC_IFACE = "org.freedesktop.impl.portal.ScreenCast"
RD_IFACE = "org.freedesktop.impl.portal.RemoteDesktop"
SESS_IFACE = "org.freedesktop.impl.portal.Session"
M = "org.gnome.Mutter."
CURSOR_MODE = 2         # Mutter cursor-mode: 0 hidden, 1 embedded, 2 metadata (client draws it: no round-trip lag)
FRONTENDS = ("/usr/libexec/xdg-desktop-portal", "/usr/lib/xdg-desktop-portal")
LIVE_TRIES = 50         # x 200 ms = 10 s for the monitor to come up

bus = None              # set in main(); classes only touch it at call time
sessions = {}


def log(*a):
    print("[seat-portal]", time.strftime("%H:%M:%S") + f".{int(time.time()*1000)%1000:03d}", *a, flush=True)


def parse_size(arg: str) -> tuple[int, int]:
    w, h = (int(v) for v in arg.lower().split("x"))
    if w <= 0 or h <= 0:
        raise ValueError(arg)
    return w, h


def _mutter(name, path, iface):
    return dbus.Interface(bus.get_object(M + name, path), M + iface)


class Session(dbus.service.Object):
    def __init__(self, handle):
        super().__init__(bus, handle)
        self.handle = str(handle)
        self.rd = self.rd_path = self.stream_path = self.clip = self.sc = None
        self.devices = 3
        self.want_screen = True

    @dbus.service.method(SESS_IFACE)
    def Close(self):
        log("Close", self.handle)
        if self.clip is not None:
            self.clip.stop()
        try:
            if self.rd is not None:
                self.rd.Stop()
        except dbus.DBusException as e:
            log("stop failed:", e)
        sessions.pop(self.handle, None)
        self.remove_from_connection()

    @dbus.service.signal(SESS_IFACE)
    def Closed(self):
        pass

    def lost(self):
        """Mutter ended the session under us: tell the client and forget it."""
        if self.handle not in sessions:
            return
        log("session lost (Mutter closed it)", self.handle)
        if self.clip is not None:
            self.clip.stop()
        for m in (self.sc, self.rd):      # tear the Mutter side down: its PipeWire
            try:                          # node must die, not just pause
                if m is not None:
                    m.Stop()
            except dbus.DBusException as e:
                log("stop failed:", e)
        self.sc = self.rd = None
        sessions.pop(self.handle, None)
        self.Closed()
        self.remove_from_connection()


class Portal(dbus.service.Object):
    def __init__(self):
        super().__init__(bus, PATH)

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, iface, prop):
        return self.GetAll(iface)[prop]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        if iface == SC_IFACE:
            return {"AvailableSourceTypes": dbus.UInt32(1),
                    "AvailableCursorModes": dbus.UInt32(7), "version": dbus.UInt32(5)}
        if iface == RD_IFACE:
            return {"AvailableDeviceTypes": dbus.UInt32(3), "version": dbus.UInt32(2)}
        return {}

    def _start(self, s, ok):
        try:
            if s.rd is None:
                s.rd_path = _mutter("RemoteDesktop", "/org/gnome/Mutter/RemoteDesktop",
                                    "RemoteDesktop").CreateSession()
                s.rd = _mutter("RemoteDesktop", s.rd_path, "RemoteDesktop.Session")
                # Mutter closes the monitor stream (and with it this session) when
                # the monitor changes resolution. Relay that to the portal client so
                # pixelflux drops the dead stream and re-creates its session.
                bus.add_signal_receiver(lambda: s.lost(), "Closed",
                                        M + "RemoteDesktop.Session", path=s.rd_path)
            if s.want_screen:
                sid = dbus.Interface(bus.get_object(M + "RemoteDesktop", s.rd_path),
                                     dbus.PROPERTIES_IFACE).Get(
                    M + "RemoteDesktop.Session", "SessionId")
                scp = _mutter("ScreenCast", "/org/gnome/Mutter/ScreenCast",
                              "ScreenCast").CreateSession({"remote-desktop-session-id": sid})
                sc = s.sc = _mutter("ScreenCast", scp, "ScreenCast.Session")
                bus.add_signal_receiver(lambda: s.lost(), "Closed",
                                        M + "ScreenCast.Session", path=scp)
                s.stream_path = sc.RecordMonitor("", {"cursor-mode": dbus.UInt32(CURSOR_MODE)})
                sobj = bus.get_object(M + "ScreenCast", s.stream_path)

                def added(node):
                    params = dbus.Interface(sobj, dbus.PROPERTIES_IFACE).Get(
                        M + "ScreenCast.Stream", "Parameters")
                    log("stream node", int(node))
                    stream = (dbus.UInt32(int(node)), dbus.Dictionary({
                        "position": params.get("position", dbus.Struct((0, 0), signature="ii")),
                        "size": params.get("size", dbus.Struct((0, 0), signature="ii")),
                        "source_type": dbus.UInt32(1)}, signature="sv"))
                    ok(dbus.UInt32(0), dbus.Dictionary({
                        "streams": dbus.Array([stream], signature="(ua{sv})"),
                        "devices": dbus.UInt32(s.devices),
                        "clipboard_enabled": dbus.Boolean(s.clip is not None)},
                        signature="sv"))
                bus.add_signal_receiver(added, "PipeWireStreamAdded",
                                        M + "ScreenCast.Stream", path=s.stream_path)
            s.rd.Start()
            if s.clip is None:
                try:
                    s.clip = ClipboardServer(s.rd, lambda fn, member, p=s.rd_path:
                                             bus.add_signal_receiver(
                                                 fn, member, M + "RemoteDesktop.Session",
                                                 path=p))
                except (RuntimeError, OSError, dbus.DBusException) as e:
                    log("clipboard off:", e)   # streaming still works
            if not s.want_screen:
                ok(dbus.UInt32(0), dbus.Dictionary({"devices": dbus.UInt32(s.devices)},
                                                   signature="sv"))
        except dbus.DBusException as e:
            log("start failed:", e)
            ok(dbus.UInt32(2), dbus.Dictionary({}, signature="sv"))


def _m(iface, member, sig, out="ua{sv}", **kw):
    def deco(fn):
        fn.__name__ = member
        return dbus.service.method(iface, in_signature=sig, out_signature=out, **kw)(fn)
    return deco


def _create(self, handle, session_handle, app_id, options):
    log("CreateSession", session_handle, app_id)
    sessions[str(session_handle)] = Session(session_handle)
    return dbus.UInt32(0), dbus.Dictionary({"session_id": str(session_handle)}, signature="sv")


def sc_create(self, handle, session_handle, app_id, options):
    return _create(self, handle, session_handle, app_id, options)


def rd_create(self, handle, session_handle, app_id, options):
    return _create(self, handle, session_handle, app_id, options)


def sc_start(self, handle, session_handle, app_id, parent_window, options, ok, err):
    self._start(sessions[str(session_handle)], ok)


def rd_start(self, handle, session_handle, app_id, parent_window, options, ok, err):
    self._start(sessions[str(session_handle)], ok)


def sc_select(self, handle, session_handle, app_id, options):
    sessions[str(session_handle)].want_screen = True   # cursor_mode ignored: always metadata
    return dbus.UInt32(0), dbus.Dictionary({}, signature="sv")


def rd_select(self, handle, session_handle, app_id, options):
    sessions[str(session_handle)].devices = int(options.get("types", 3))
    return dbus.UInt32(0), dbus.Dictionary({}, signature="sv")


def rd_eis(self, session_handle, app_id, options):
    return sessions[str(session_handle)].rd.ConnectToEIS(dbus.Dictionary({}, signature="sv"))


def _forward(name, conv):
    """Notify* passthrough with the fixed arity dbus-python needs."""
    def fn2(self, sh, o, a1, a2):
        s = sessions[str(sh)]
        getattr(s.rd, name)(*conv(s, o, a1, a2))

    def fn3(self, sh, o, a1, a2, a3):
        s = sessions[str(sh)]
        getattr(s.rd, name)(*conv(s, o, a1, a2, a3))
    return fn3 if name == "NotifyPointerMotionAbsolute" else fn2


def _motion(s, o, dx, dy):
    return dx, dy


def _abs(s, o, stream, x, y):
    return s.stream_path, x, y


def _button(s, o, b, st):
    return b, bool(st)


def _axis(s, o, dx, dy):
    return dx, dy, dbus.UInt32(1 if o.get("finish") else 0)


def _discrete(s, o, axis, n):
    return axis, n


def _key(s, o, k, st):
    return dbus.UInt32(k), bool(st)


SC_METHODS = {
    "CreateSession": _m(SC_IFACE, "CreateSession", "oosa{sv}")(sc_create),
    "SelectSources": _m(SC_IFACE, "SelectSources", "oosa{sv}")(sc_select),
    "Start": _m(SC_IFACE, "Start", "oossa{sv}", async_callbacks=("ok", "err"))(sc_start),
}
RD_METHODS = {
    "CreateSession": _m(RD_IFACE, "CreateSession", "oosa{sv}")(rd_create),
    "SelectDevices": _m(RD_IFACE, "SelectDevices", "oosa{sv}")(rd_select),
    "Start": _m(RD_IFACE, "Start", "oossa{sv}", async_callbacks=("ok", "err"))(rd_start),
    "ConnectToEIS": _m(RD_IFACE, "ConnectToEIS", "osa{sv}", out="h")(rd_eis),
    "NotifyPointerMotion": _m(RD_IFACE, "NotifyPointerMotion", "oa{sv}dd", out="")(
        _forward("NotifyPointerMotionRelative", _motion)),
    "NotifyPointerMotionAbsolute": _m(RD_IFACE, "NotifyPointerMotionAbsolute", "oa{sv}udd",
                                      out="")(_forward("NotifyPointerMotionAbsolute", _abs)),
    "NotifyPointerButton": _m(RD_IFACE, "NotifyPointerButton", "oa{sv}iu", out="")(
        _forward("NotifyPointerButton", _button)),
    "NotifyPointerAxis": _m(RD_IFACE, "NotifyPointerAxis", "oa{sv}dd", out="")(
        _forward("NotifyPointerAxis", _axis)),
    "NotifyPointerAxisDiscrete": _m(RD_IFACE, "NotifyPointerAxisDiscrete", "oa{sv}ui", out="")(
        _forward("NotifyPointerAxisDiscrete", _discrete)),
    "NotifyKeyboardKeycode": _m(RD_IFACE, "NotifyKeyboardKeycode", "oa{sv}iu", out="")(
        _forward("NotifyKeyboardKeycode", _key)),
    "NotifyKeyboardKeysym": _m(RD_IFACE, "NotifyKeyboardKeysym", "oa{sv}iu", out="")(
        _forward("NotifyKeyboardKeysym", _key)),
}
# ScreenCast and RemoteDesktop share member names: one class level each (see docstring).
ScreenCastLevel = type("ScreenCastLevel", (Portal,), SC_METHODS)
Seat = type("Seat", (ScreenCastLevel,), RD_METHODS)


class Monitor:
    """Mutter virtual monitor held at w x h by a fakesink consumer.
    ponytail: always-copy costs one copy per painted frame (unmeasurable in the
    spike at 1440p60); drop it if a box's CPU budget ever says otherwise."""
    def __init__(self, w, h, on_closed):
        self.w, self.h, self.pipe, self.playing = w, h, None, False
        path = _mutter("ScreenCast", "/org/gnome/Mutter/ScreenCast",
                       "ScreenCast").CreateSession(dbus.Dictionary({}, signature="sv"))
        self.sess = _mutter("ScreenCast", path, "ScreenCast.Session")
        # GNOME's screen-share "Stop" closes this session: the monitor is gone,
        # so exit and let the agent restart us (seat_gnome heal path).
        bus.add_signal_receiver(lambda *a: on_closed(), "Closed",
                                M + "ScreenCast.Session", path=path)
        stream = self.sess.RecordVirtual(dbus.Dictionary(
            {"cursor-mode": dbus.UInt32(CURSOR_MODE), "is-platform": dbus.Boolean(True)},
            signature="sv"))
        bus.add_signal_receiver(self._added, "PipeWireStreamAdded",
                                M + "ScreenCast.Stream", path=stream)
        self.sess.Start()

    def _added(self, node):
        self.node = int(node)
        self.pipe = Gst.parse_launch(
            f"pipewiresrc path={int(node)} always-copy=true ! "
            f"capsfilter name=cf caps=video/x-raw,width={self.w},height={self.h},max-framerate=60/1 ! "
            "fakesink sync=false")
        self.pipe.set_state(Gst.State.PLAYING)
        self.playing = True
        log("virtual monitor stream", int(node), f"{self.w}x{self.h}")

    def resize(self, w, h):
        """In-place resize: pipewiresrc negotiates its format only at connect, so
        a fresh consumer on the same node makes Mutter renegotiate
        (notify_params_updated -> meta_virtual_monitor_set_mode) and resize the
        SAME virtual monitor (~100 ms, windows reflow, no monitor removal).
        Mutter then closes every RecordMonitor stream of the old size, which
        pixelflux never recovers from: the agent restarts selkies."""
        self.w, self.h = w, h
        self.pipe.set_state(Gst.State.NULL)
        self.pipe = Gst.parse_launch(
            f"pipewiresrc path={self.node} always-copy=true ! "
            f"capsfilter name=cf caps=video/x-raw,width={w},height={h},max-framerate=60/1 ! "
            "fakesink sync=false")
        self.pipe.set_state(Gst.State.PLAYING)
        log("resize: reconnected consumer at", f"{w}x{h}")

    def is_current(self) -> bool:
        dc = _mutter("DisplayConfig", "/org/gnome/Mutter/DisplayConfig", "DisplayConfig")
        _serial, monitors, _logical, _props = dc.GetCurrentState()
        return any(mode[6].get("is-current") and (int(mode[1]), int(mode[2])) == (self.w, self.h)
                   for _spec, modes, _mprops in monitors for mode in modes)

    def stop(self):
        if self.pipe is not None:
            self.pipe.set_state(Gst.State.NULL)
        try:
            self.sess.Stop()
        except dbus.DBusException:
            pass


def _write_ready(path: str, text: str) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


def selftest() -> int:
    sc, rd = ScreenCastLevel.__dict__, Seat.__dict__
    assert sc["CreateSession"]._dbus_interface == SC_IFACE
    assert sc["Start"]._dbus_interface == SC_IFACE
    assert rd["CreateSession"]._dbus_interface == RD_IFACE
    assert rd["Start"]._dbus_interface == RD_IFACE
    assert rd["NotifyPointerMotionAbsolute"]._dbus_in_signature == "oa{sv}udd"
    assert rd["ConnectToEIS"]._dbus_out_signature == "h"
    assert parse_size("2552x1294") == (2552, 1294)
    assert SystemdStub.__dict__["StartUnit"]._dbus_out_signature == "o"
    print("selftest ok", flush=True)
    return 0


def main(argv) -> int:
    global bus
    if argv[1:] == ["--selftest"]:
        return selftest()
    w, h = parse_size(argv[1])
    DBusGMainLoop(set_as_default=True)
    Gst.init(None)
    bus = dbus.SessionBus()
    seat_systemd.bus, seat_systemd.log = bus, log
    name = dbus.service.BusName(BUS_NAME, bus)  # noqa: F841 — held for life
    Seat()
    sd_name = dbus.service.BusName(SD_NAME, bus)  # noqa: F841 — private bus only
    SystemdStub()
    ready = os.environ.get("STYX_PORTAL_READY", "")
    loop = GLib.MainLoop()
    st = {"rc": 0, "tries": 0, "frontend": None}

    def on_closed():
        log("virtual monitor session closed (screen-share Stop?); exiting")
        st["rc"] = 1
        loop.quit()

    mon = Monitor(w, h, on_closed)

    def poll():
        if mon.playing and mon.is_current():
            exe = next((p for p in FRONTENDS if os.path.exists(p)), None)
            if exe is None:
                log("xdg-desktop-portal not found")
                st["rc"] = 1
                loop.quit()
                return False
            st["frontend"] = subprocess.Popen([exe, "--replace"])
            if ready:
                _write_ready(ready, f"{w}x{h}")
            log("ready", f"{w}x{h}")
            GLib.timeout_add(25, watch_resize)
            GLib.timeout_add(250, watch_scale)
            return False
        st["tries"] += 1
        if st["tries"] >= LIVE_TRIES:
            log(f"virtual monitor {w}x{h} never became current")
            st["rc"] = 1
            loop.quit()
            return False
        return True

    rq = {"path": os.path.join(os.path.dirname(ready), "seat-resize-request") if ready else "",
          "pending": None, "tries": 0}

    sc = {"path": os.environ.get("STYX_SEAT_SCALE_FILE", ""), "mtime": None, "first": True}

    def watch_scale():
        """<install>/seat-scale = 1|2 -> logical scale; applied at startup, on
        file change and after each resize."""
        try:
            m = os.stat(sc["path"]).st_mtime_ns if sc["path"] else -1
        except OSError:
            m = -1
        if m != sc["mtime"] or sc["first"]:
            sc["mtime"], sc["first"] = m, False
            apply_scale(bus, read_scale(sc["path"]) if sc["path"] else 1, log)
        return True

    def watch_resize():
        """<runtime>/seat-resize-request = WxH -> in-place resize; the ready
        file follows once Mutter reports the new mode current (seat_gnome
        resize_live waits on it)."""
        if rq["pending"] is None:
            try:
                size = parse_size(open(rq["path"]).read().strip())
            except (OSError, ValueError, IndexError):
                return True
            os.unlink(rq["path"])
            rq["pending"], rq["tries"] = size, 0
            mon.resize(*size)
            return True
        rq["tries"] += 1
        if mon.is_current():
            # A resize can reset the scale: re-apply BEFORE ready, so the
            # selkies started on ready opens its stream at the final scale
            # (Mutter maps pointer input with the scale the stream was made at).
            sc["mtime"] = None
            watch_scale()
            _write_ready(ready, f"{mon.w}x{mon.h}")
            log("resized live", f"{mon.w}x{mon.h}", f"after {rq['tries']*25} ms")
            rq["pending"] = None
        elif rq["tries"] >= LIVE_TRIES * 8:        # 10 s at 25 ms
            log("resize never became current", f"{mon.w}x{mon.h}")
            rq["pending"] = None
        return True

    def on_term():
        loop.quit()
        return False

    GLib.timeout_add(200, poll)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, on_term)
    loop.run()
    if st["frontend"] is not None:
        st["frontend"].terminate()
        try:
            st["frontend"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            st["frontend"].kill()
    for s in list(sessions.values()):
        if s.clip is not None:
            s.clip.stop()
    mon.stop()
    if ready:
        try:
            os.unlink(ready)
        except OSError:
            pass
    return st["rc"]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
