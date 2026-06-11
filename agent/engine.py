"""Engine logic for the pixelflux/selkies 2.x agent — pure functions only.

mirror: attach to a live X display (XShm capture), resolution locked to the
        physical screen so selkies never xrandr-resizes the user's monitor.
seat:   pixelflux's own Wayland compositor; host apps join via WAYLAND_DISPLAY.
"""
import glob
import os
import time
from pathlib import Path

HOME = Path.home()
DRI_DIR = "/dev/dri"
INTERNAL_WS_OFFSET = 1     # selkies binds loopback on port+1; gateway owns port
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


def pick_dri_node() -> str:
    nodes = sorted(glob.glob(os.path.join(DRI_DIR, "renderD*")))
    return nodes[0] if nodes else ""


def query_display_geometry(display: str, xauthority: str | None) -> tuple[int, int]:
    """Screen size of a live X display, via the venv's python-xlib."""
    from Xlib import display as xdisplay  # venv dep of selkies
    if xauthority:
        os.environ["XAUTHORITY"] = xauthority
    d = xdisplay.Display(display)
    try:
        s = d.screen()
        return s.width_in_pixels, s.height_in_pixels
    finally:
        d.close()


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
                            timeout: float = 15) -> str | None:
    """The compositor picks the first free wayland-N; detect it by diffing."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        now = {p.name for p in Path(runtime_dir).glob("wayland-*")
               if not p.name.endswith(".lock")}
        new = now - before
        if new:
            return sorted(new)[0]
        time.sleep(0.2)
    return None


def build_selkies_cmd(cfg: dict) -> tuple[list[str], dict]:
    """argv + env for the selkies process (run through selkies_launcher.py,
    which forces a loopback bind). Secrets travel via env, never argv."""
    install = Path(cfg["install_dir"])
    s = cfg.get("stream_settings", {})
    internal_port = cfg["port"] + INTERNAL_WS_OFFSET

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
        f"--control-port={internal_port + 1}",
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
