"""Systemd stub for the seat's private bus (answers gnome-shell, relays snap scopes)."""
import os

import dbus
import dbus.bus
import dbus.service
from gi.repository import GLib

bus = None              # set by seat_portal.main() once the session bus exists
log = print             # replaced by seat_portal.log (same set-at-main pattern)


SD_NAME = "org.freedesktop.systemd1"
SD_IFACE = SD_NAME + ".Manager"
SD_PATH = "/org/freedesktop/systemd1"


def snap_scope_props(name, props, aux, caller_pid):
    """Filter StartTransientUnit args from an untrusted seat app down to what
    `snap run` needs: a snap.*.scope holding only the caller's PID (plus a
    Description). Raises ValueError for anything else."""
    if not (name.startswith("snap.") and name.endswith(".scope")):
        raise ValueError("only snap.*.scope units may be started")
    if aux:
        raise ValueError("auxiliary units are not allowed")
    pids = [int(p) for k, v in props if k == "PIDs" for p in v]
    if pids != [caller_pid]:
        raise ValueError("PIDs must be exactly the caller")
    return [(k, v) for k, v in props if k in ("PIDs", "Description")]


class SystemdStub(dbus.service.Object):
    """gnome-shell runs inside the agent's systemd user unit, so before it lets
    Xwayland start it asks the session bus's systemd for
    gnome-session-x11-services-ready.target, and any failure but NOT_SUPPORTED
    aborts X11: X11-only apps (GIMP 2.10, JetBrains IDEs) never open. The
    seat's private bus has no systemd, so answer every job as done.
    ponytail: the X11 services (gsd-xsettings) are not started, so X11 apps
    get toolkit-default theme/scaling; spawn gsd-xsettings here if that matters."""
    def __init__(self):
        super().__init__(bus, SD_PATH)
        self.jobs = 0
        self.real = None
        try:
            self.real = dbus.bus.BusConnection(
                f"unix:path={os.environ.get('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid())}/bus")
            self.real.call_blocking(SD_NAME, SD_PATH, SD_IFACE, "Subscribe", "", [])
            self.real.add_signal_receiver(self._relay, "JobRemoved", SD_IFACE, SD_NAME, SD_PATH)
        except dbus.exceptions.DBusException as e:
            log("systemd stub: no real user systemd, snap apps will not start:", e)

    def _relay(self, id_, job, unit, result):
        if unit.startswith("snap."):
            self.JobRemoved(id_, job, unit, result)

    def _job(self, unit):
        self.jobs += 1
        job = dbus.ObjectPath(f"{SD_PATH}/job/{self.jobs}")
        log("systemd stub: job done for", unit)
        # After the method reply: gnome-shell matches JobRemoved to the returned path.
        n = dbus.UInt32(self.jobs)
        GLib.timeout_add(50, lambda: self.JobRemoved(n, job, unit, "done") and False)
        return job

    @dbus.service.method(SD_IFACE, in_signature="ss", out_signature="o")
    def StartUnit(self, unit, mode):
        return self._job(unit)

    @dbus.service.method(SD_IFACE, in_signature="ss", out_signature="o")
    def StopUnit(self, unit, mode):
        return self._job(unit)

    @dbus.service.method(SD_IFACE, in_signature="ssa(sv)a(sa(sv))", out_signature="o",
                         sender_keyword="sender")
    def StartTransientUnit(self, name, mode, props, aux, sender=None):
        # snap run must land in a real snap.<app>.*.scope or snap-confine aborts
        # ("... is not a snap cgroup"), so forward those to the user's systemd;
        # _relay passes its JobRemoved back. Others keep the old fork fallback.
        # Seat apps reach this stub, so only a snap scope that moves the
        # caller's own PID is forwarded: no ExecStart/Slice/aux units smuggled
        # into the real user systemd.
        if not self.real:
            raise dbus.exceptions.DBusException(
                name, name="org.freedesktop.DBus.Error.UnknownMethod")
        caller = bus.get_object("org.freedesktop.DBus", "/org/freedesktop/DBus").GetConnectionUnixProcessID(
            sender, dbus_interface="org.freedesktop.DBus")
        try:
            safe = snap_scope_props(name, props, aux, int(caller))
        except ValueError as e:
            raise dbus.exceptions.DBusException(
                str(e), name="org.freedesktop.DBus.Error.AccessDenied")
        return self.real.call_blocking(SD_NAME, SD_PATH, SD_IFACE, "StartTransientUnit",
                                       "ssa(sv)a(sa(sv))", [name, mode, safe, []])

    @dbus.service.signal(SD_IFACE, signature="uoss")
    def JobRemoved(self, id_, job, unit, result):
        pass
