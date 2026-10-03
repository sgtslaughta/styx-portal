"""labwc seat shell + clipboard bridge launchers (seat mode)."""
import os
import shutil
import subprocess
from pathlib import Path

import engine


def start_shell(install_dir: Path, seat_socket: str, runtime_dir: str,
                log) -> subprocess.Popen | None:
    if not (seat_socket and shutil.which("labwc")):
        return None
    engine.write_seat_config(install_dir / "labwc")
    shell_env = {**os.environ, "WAYLAND_DISPLAY": seat_socket,
                 "XDG_RUNTIME_DIR": runtime_dir,
                 # Route seat apps' audio to the captured null sink —
                 # they'd otherwise play to the host's default sink
                 # (physical speakers) and the stream would be silent.
                 "PULSE_SINK": engine.SEAT_SINK,
                 # Seat apps record from the browser-fed virtual mic.
                 "PULSE_SOURCE": engine.MIC_SOURCE}
    # labwc runs the config dir's autostart (wallpaper, panel, terminal)
    # AFTER Xwayland is up, so those children inherit DISPLAY and can
    # launch the machine's X11 apps (Chrome etc.).
    return subprocess.Popen(["labwc", "-C", str(install_dir / "labwc")],
                            env=shell_env, stdout=log, stderr=log)


def start_clipboard_bridge(install_dir: Path, seat_socket: str | None,
                           app_socket: str | None, runtime_dir: str,
                           log_dir: Path) -> subprocess.Popen | None:
    """Start the bidirectional clipboard bridge between pixelflux and labwc.

    Only runs in seat mode when both sockets are known and different.
    The bridge needs to restart if either socket changes (e.g. selkies restart).
    """
    if not seat_socket or not app_socket or seat_socket == app_socket:
        return None
    # Sockets are genuinely different; start the bridge
    clipboard_log = open(log_dir / "clipboard.log", "ab", buffering=0)
    cmd = [
        str(install_dir / "venv/bin/python"),
        str(install_dir / "clipboard_bridge.py"),
        seat_socket,
        app_socket,
        runtime_dir,
    ]
    return subprocess.Popen(cmd, stdout=clipboard_log, stderr=clipboard_log)
