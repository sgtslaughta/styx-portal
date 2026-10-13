"""GNOME logical scale for the headless seat: pure helpers + apply_scale (Mutter DisplayConfig via dbus-python)."""
import os
from pathlib import Path


def scale_for_dpi(dpi) -> int:
    # ponytail: integer scales only; Mutter offers [1.0, 2.0] without the fractional experimental feature.
    # 168 = midpoint of 96 and 240.
    return 2 if dpi and dpi >= 168 else 1


def read_scale(path) -> int:
    try:
        return 2 if Path(path).read_text().strip() == "2" else 1
    except OSError:
        return 1


def write_scale(path, s) -> None:
    p = Path(path)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(str(int(s)))
    os.replace(tmp, p)


def monitors_config(state, scale):
    """ApplyMonitorsConfig args for GetCurrentState `state` at `scale`, or None
    when the scale is unsupported or already in effect."""
    serial, monitors, logical, _props = state
    modes = {tuple(spec)[0]: ms for spec, ms, _p in monitors}
    out, changed = [], False
    for x, y, cur, transform, primary, specs, _p in logical:
        mons = []
        for spec in specs:
            cur_mode = next((m for m in modes.get(spec[0], ()) if m[6].get("is-current")), None)
            if cur_mode is None or float(scale) not in [float(v) for v in cur_mode[5]]:
                return None
            mons.append((spec[0], cur_mode[0], {}))
        changed = changed or float(cur) != float(scale)
        out.append((x, y, float(scale), transform, bool(primary), mons))
    return (serial, 1, out, {}) if out and changed else None


def apply_scale(bus, scale, log) -> None:
    """Set the logical scale on the live monitor(s); a rejection is logged, never raised."""
    import dbus
    dc = dbus.Interface(bus.get_object("org.gnome.Mutter.DisplayConfig",
                                       "/org/gnome/Mutter/DisplayConfig"),
                        "org.gnome.Mutter.DisplayConfig")
    try:
        cfg = monitors_config(dc.GetCurrentState(), scale)
        if cfg is None:
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
    except dbus.exceptions.DBusException as e:
        log("scale", scale, "rejected:", e.get_dbus_message())
