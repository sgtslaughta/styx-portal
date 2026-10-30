"""GNOME logical scale for the headless seat: pure helpers + apply_scale (Mutter DisplayConfig via dbus-python)."""
import os
from pathlib import Path


# Scales GNOME (scale-monitor-framebuffer) and selkies both take: selkies snaps
# its DPI to 24-dpi stops, Mutter offers 1, 1.33, 1.5, 2, 2.67, 3 at most modes.
# They must agree: pixelflux maps libei pointer input with selkies' scale.
SCALES = (1.0, 1.5, 2.0, 3.0)


def scale_for_dpi(dpi) -> float:
    """Shared seat scale nearest dpi/96 (ties round up: 125% -> 1.5)."""
    try:
        want = float(dpi) / 96.0 if dpi else 1.0
    except (TypeError, ValueError):
        want = 1.0
    return min(SCALES, key=lambda v: (abs(v - want), -v))


def dpi_for_scale(scale) -> int:
    return round(float(scale) * 96)


def read_scale(path) -> float:
    try:
        return max(1.0, float(Path(path).read_text().strip()))
    except (OSError, ValueError):
        return 1.0


def write_scale(path, s) -> None:
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(f"{float(s):g}")
    os.replace(tmp, p)


def monitors_config(state, scale):
    """ApplyMonitorsConfig args for GetCurrentState `state` at the supported
    scale nearest `scale`, or None when none is offered or it is in effect."""
    serial, monitors, logical, _props = state
    modes = {tuple(spec)[0]: ms for spec, ms, _p in monitors}
    out, changed = [], False
    for x, y, cur, transform, primary, specs, _p in logical:
        mons, offered = [], None
        for spec in specs:
            cur_mode = next((m for m in modes.get(spec[0], ()) if m[6].get("is-current")), None)
            if cur_mode is None or not cur_mode[5]:
                return None
            offered = [float(v) for v in cur_mode[5]]
            mons.append((spec[0], cur_mode[0], {}))
        pick = min(offered, key=lambda v: abs(v - float(scale)))
        if abs(pick - float(scale)) > 0.5:          # e.g. 2.0 wanted, only 1.0 offered
            return None
        changed = changed or float(cur) != pick
        out.append((x, y, pick, transform, bool(primary), mons))
    return (serial, 1, out, {}) if out and changed else None


def _at_scale(state, scale) -> bool:
    return all(abs(float(lm[2]) - float(scale)) <= 0.5 for lm in state[2])


def apply_scale(bus, scale, log) -> None:
    """Set the logical scale on the live monitor(s). Never raises: it runs as a
    GLib timeout callback, and a raising callback would remove its source."""
    try:
        import dbus
        dc = dbus.Interface(bus.get_object("org.gnome.Mutter.DisplayConfig",
                                           "/org/gnome/Mutter/DisplayConfig"),
                            "org.gnome.Mutter.DisplayConfig")
        state = dc.GetCurrentState()
        cfg = monitors_config(state, scale)
        if cfg is None:
            if not _at_scale(state, scale):
                log("scale", scale, "unsupported by the current monitor mode")
            return
        serial, method, lms, props = cfg
        lm = dbus.Array([dbus.Struct((dbus.Int32(x), dbus.Int32(y), dbus.Double(sc),
                                      dbus.UInt32(t), dbus.Boolean(pr),
                                      dbus.Array([dbus.Struct((c, m, dbus.Dictionary({}, signature="sv")),
                                                              signature="ssa{sv}") for c, m, _ in mons],
                                                 signature="(ssa{sv})")), signature="iiduba(ssa{sv})")
                         for x, y, sc, t, pr, mons in lms], signature="(iiduba(ssa{sv}))")
        dc.ApplyMonitorsConfig(dbus.UInt32(serial), dbus.UInt32(method), lm,
                               dbus.Dictionary({}, signature="sv"))
        log("scale", scale, "applied")
    except Exception as e:
        get = getattr(e, "get_dbus_message", None)
        log("scale", scale, "failed:", get() if get else e)
