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


def live_path(path) -> str:
    """Where the seat helper records the scale it applied (selkies must run at it)."""
    return f"{path}-live"


def pick_scale(offered, want) -> float:
    """Largest scale Mutter offers that selkies also takes (SCALES), at most `want`:
    a scale only Mutter takes (2.67) would leave the two disagreeing."""
    ok = [o for o in offered if o <= float(want) + 0.01 and any(abs(o - s) < 0.01 for s in SCALES)]
    return max(ok, default=1.0)


def monitors_config(state, scale):
    """(ApplyMonitorsConfig args or None when already in effect, scale picked)
    for GetCurrentState `state` and the wanted `scale`."""
    serial, monitors, logical, _props = state
    modes = {tuple(spec)[0]: ms for spec, ms, _p in monitors}
    out, changed, pick = [], False, 1.0
    for x, y, cur, transform, primary, specs, _p in logical:
        mons, offered = [], [1.0]
        for spec in specs:
            cur_mode = next((m for m in modes.get(spec[0], ()) if m[6].get("is-current")), None)
            if cur_mode is None:
                return None, 1.0
            offered = [float(v) for v in cur_mode[5]] or [1.0]
            mons.append((spec[0], cur_mode[0], {}))
        pick = pick_scale(offered, scale)
        changed = changed or abs(float(cur) - pick) > 0.01
        out.append((x, y, pick, transform, bool(primary), mons))
    return ((serial, 1, out, {}) if out and changed else None), pick


def apply_scale(bus, scale, log, live_file="") -> None:
    """Set the logical scale on the live monitor(s) and record it in `live_file`.
    Never raises: it runs as a GLib timeout callback, and a raising callback
    would remove its source."""
    try:
        import dbus
        dc = dbus.Interface(bus.get_object("org.gnome.Mutter.DisplayConfig",
                                           "/org/gnome/Mutter/DisplayConfig"),
                            "org.gnome.Mutter.DisplayConfig")
        state = dc.GetCurrentState()
        cfg, pick = monitors_config(state, scale)
        if abs(pick - float(scale)) > 0.01:
            log("scale", scale, "unsupported by the current monitor mode, using", pick)
        if cfg is not None:
            _apply(dbus, dc, cfg)
            log("scale", pick, "applied")
        if live_file:
            write_scale(live_file, pick)
    except Exception as e:
        get = getattr(e, "get_dbus_message", None)
        log("scale", scale, "failed:", get() if get else e)


def _apply(dbus, dc, cfg) -> None:
    serial, method, lms, props = cfg
    lm = dbus.Array([dbus.Struct((dbus.Int32(x), dbus.Int32(y), dbus.Double(sc),
                                  dbus.UInt32(t), dbus.Boolean(pr),
                                  dbus.Array([dbus.Struct((c, m, dbus.Dictionary({}, signature="sv")),
                                                          signature="ssa{sv}") for c, m, _ in mons],
                                             signature="(ssa{sv})")), signature="iiduba(ssa{sv})")
                     for x, y, sc, t, pr, mons in lms], signature="(iiduba(ssa{sv}))")
    dc.ApplyMonitorsConfig(dbus.UInt32(serial), dbus.UInt32(method), lm,
                           dbus.Dictionary({}, signature="sv"))
