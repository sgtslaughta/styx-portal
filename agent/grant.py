"""One-time portal consent for the GNOME seat (spec §5.5). Success = pixelflux
wrote its restore token; later sessions start without a prompt. Local flow only:
the consent dialog is shown on the physical desktop and clicked by a human."""
import asyncio
import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path

from seat_gnome import TOKEN_PATH

PROC = Path("/proc")
INSTALL_DIR = Path.home() / ".local/share/styx-agent"


def _seat_bus() -> str | None:
    try:
        return (INSTALL_DIR / "gnome-bus.addr").read_text().strip() or None
    except OSError:
        return None


def _set_activation_display(bus: str, display: str) -> None:
    subprocess.run(["dbus-update-activation-environment", f"DISPLAY={display}"],
                   env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus},
                   capture_output=True)


def _restart_seat_portal(bus: str) -> None:
    """Kill portal backends of the seat bus only, so they re-activate with the
    new env; the physical session's portal is left alone."""
    want = f"DBUS_SESSION_BUS_ADDRESS={bus}".encode()
    for p in PROC.iterdir():
        if not p.name.isdigit():
            continue
        try:
            if not (p / "comm").read_text().startswith("xdg-desktop-por"):
                continue
            if want in (p / "environ").read_bytes().split(b"\0"):
                os.kill(int(p.name), signal.SIGTERM)
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue


def _trigger_stream(cfg: dict, hold_s: float = 120) -> None:
    """Open a viewer on the local gateway so selkies starts its portal session."""
    import aiohttp

    async def go():
        auth = aiohttp.BasicAuth(cfg["selkies_user"], cfg["selkies_password"])
        async with aiohttp.ClientSession(auth=auth) as s, s.ws_connect(
                f"http://127.0.0.1:{cfg['port']}/api/websockets") as ws:
            await ws.send_str("SETTINGS," + json.dumps(
                {"displayId": "primary", "initialClientWidth": 1920,
                 "initialClientHeight": 1080}))
            await ws.send_str("START_VIDEO")
            await asyncio.sleep(hold_s)
    try:
        asyncio.run(go())
    except Exception as e:  # noqa: BLE001 - best effort; poll decides the result
        print(f"stream trigger ended: {e}", flush=True)


def _x_display_alive(display: str) -> bool:
    return bool(display) and subprocess.run(
        ["xset", "-display", display, "q"], capture_output=True).returncode == 0


def _wait_token(timeout_s: float) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if TOKEN_PATH.exists():
            return True
        time.sleep(0.1)
    return TOKEN_PATH.exists()


def grant(cfg: dict, timeout_s: float = 120) -> int:
    display = cfg.get("display") or ":0"
    if not _x_display_alive(display):
        print(f"doctor --grant needs a logged-in desktop on {display}; none found.")
        return 1
    bus = _seat_bus()
    if not bus:
        print("GNOME seat not running — start the agent first.")
        return 1
    ok = False
    try:
        _set_activation_display(bus, display)
        _restart_seat_portal(bus)
        print("Click 'Allow' in the screen-share dialog on this box's screen.")
        threading.Thread(target=_trigger_stream, args=(cfg, timeout_s),
                         daemon=True).start()
        ok = _wait_token(timeout_s)
    finally:
        _set_activation_display(bus, "")
        _restart_seat_portal(bus)
    print("Consent granted." if ok else "No consent recorded.")
    return 0 if ok else 1
