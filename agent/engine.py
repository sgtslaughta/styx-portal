"""Engine logic for the pixelflux/selkies 2.x agent — pure functions only.

mirror: attach to a live X display (XShm capture), resolution locked to the
        physical screen so selkies never xrandr-resizes the user's monitor.
seat:   pixelflux's own Wayland compositor; host apps join via WAYLAND_DISPLAY.
"""
import glob
import os
import socket
import time
from pathlib import Path

HOME = Path.home()
DRI_DIR = "/dev/dri"
SEAT_SINK = "styx-seat"    # null sink so seat audio never hits the speakers


def _find_xauthority(cfg: dict) -> str | None:
    """systemd --user starts with an empty env; resolve the cookie explicitly.
    Location varies by distro/display manager."""
    uid = os.getuid()
    candidates = [
        cfg.get("xauthority"),
        os.environ.get("XAUTHORITY"),
        str(HOME / ".Xauthority"),
        f"/run/user/{uid}/.mutter-Xwaylandauth",      # GNOME Xwayland
        f"/run/user/{uid}/gdm/Xauthority",            # GDM
    ]
    candidates += [str(p) for p in sorted(HOME.glob(".vnc/*Xauthority"))]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def pick_free_port() -> int:
    """A free loopback port for the selkies<->gateway link (race window
    between close and child bind is acceptable on loopback)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pick_dri_node() -> str:
    nodes = sorted(glob.glob(os.path.join(DRI_DIR, "renderD*")))
    return nodes[0] if nodes else ""


def query_display_geometry(display: str, xauthority: str | None) -> tuple[int, int]:
    """Screen size of a live X display, via the venv's python-xlib.

    Xlib reads XAUTHORITY from the process env at connect time; set it only
    for the duration of the query so the supervisor's env stays clean.
    """
    from Xlib import display as xdisplay  # venv dep of selkies
    saved = os.environ.get("XAUTHORITY")
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    try:
        d = xdisplay.Display(display)
        try:
            s = d.screen()
            return s.width_in_pixels, s.height_in_pixels
        finally:
            d.close()
    finally:
        if xauthority:
            if saved is None:
                os.environ.pop("XAUTHORITY", None)
            else:
                os.environ["XAUTHORITY"] = saved


def resolve_monitor_source() -> str:
    """Monitor source of the default sink ('' = no audio server -> disable).
    selkies' baked-in default 'output.monitor' only exists in containers."""
    try:
        import pulsectl
        with pulsectl.Pulse("styx-agent") as p:
            return p.server_info().default_sink_name + ".monitor"
    except Exception:
        return ""


def ensure_seat_sink() -> str:
    """Create (idempotently) a null sink for seat audio; returns its monitor."""
    import pulsectl
    with pulsectl.Pulse("styx-agent") as p:
        if not any(s.name == SEAT_SINK for s in p.sink_list()):
            p.module_load("module-null-sink",
                          f"sink_name={SEAT_SINK} "
                          f"sink_properties=device.description={SEAT_SINK}")
    return f"{SEAT_SINK}.monitor"


def wait_for_wayland_socket(runtime_dir: str, before: set[str],
                            since_ts: float, timeout: float = 15) -> str | None:
    """The compositor picks the first free wayland-N. A socket counts if its
    name is new OR its file was (re)created after `since_ts` — stale socket
    files survive process death, so a pure before/after name diff misses a
    compositor that rebinds the same wayland-N (seen on agent restart)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for p in sorted(Path(runtime_dir).glob("wayland-*")):
            if p.name.endswith(".lock"):
                continue
            if p.name not in before:
                return p.name
            try:
                if p.stat().st_mtime >= since_ts:
                    return p.name
            except FileNotFoundError:
                continue
        time.sleep(0.2)
    return None


def build_selkies_cmd(cfg: dict, internal_port: int, control_port: int) -> tuple[list[str], dict]:
    """argv + env for the selkies process (run through selkies_launcher.py,
    which forces a loopback bind). Secrets travel via env, never argv.

    internal_port: dynamically allocated loopback port for selkies<->gateway.
    control_port: dynamically allocated control port (independent of internal_port).

    Mirror mode queries the live X display and may raise (Xlib connection/
    auth errors) — the supervisor catches and reports via heartbeat.
    """
    install = Path(cfg["install_dir"])
    s = cfg.get("stream_settings", {})

    env = {
        "HOME": str(HOME),
        "XDG_RUNTIME_DIR": os.environ.get("XDG_RUNTIME_DIR",
                                          f"/run/user/{os.getuid()}"),
        "LD_LIBRARY_PATH": str(install / "lib"),   # libva/libwayland shim
        "PYTHONNOUSERSITE": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }

    cmd = [
        str(install / "venv/bin/python"),
        str(install / "selkies_launcher.py"),
        f"--port={internal_port}",
        f"--control-port={control_port}",
        "--encoder=x264enc",          # pixelflux switches to VAAPI/NVENC itself
        f"--framerate={s.get('framerate', 60)}",
        "--mode=websockets",
    ]

    dri = pick_dri_node()
    if dri:
        cmd.append(f"--dri-node={dri}")

    if cfg.get("mode") == "seat":
        env["PIXELFLUX_WAYLAND"] = "true"
        if dri:
            env["DRINODE"] = dri
        monitor = resolve_monitor_source()
    else:  # mirror
        env["DISPLAY"] = cfg["display"]
        xauth = _find_xauthority(cfg)
        if xauth:
            env["XAUTHORITY"] = xauth
        w, h = query_display_geometry(cfg["display"], xauth)
        cmd += ["--is-manual-resolution-mode=true",
                f"--manual-width={w}", f"--manual-height={h}"]
        monitor = resolve_monitor_source()

    if monitor:
        env["SELKIES_AUDIO_ENABLED"] = "true"
        cmd.append(f"--audio-device-name={monitor}")
    else:
        env["SELKIES_AUDIO_ENABLED"] = "false"

    return cmd, env
