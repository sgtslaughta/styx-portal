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

from health import active_connections
from seat_gnome import TOKEN_PATH

PROC = Path("/proc")
INSTALL_DIR = Path.home() / ".local/share/styx-agent"


def _seat_bus() -> str | None:
    try:
        return (INSTALL_DIR / "gnome-bus.addr").read_text().strip() or None
    except OSError:
        return None


def _set_activation_display(bus: str, display: str) -> None:
    r = subprocess.run(["dbus-update-activation-environment", f"DISPLAY={display}"],
                       env={**os.environ, "DBUS_SESSION_BUS_ADDRESS": bus},
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"dbus-update-activation-environment failed ({r.returncode})")


def _restart_seat_portal(bus: str) -> None:
    """Kill portal backends of the seat bus only, so they re-activate with the
    new env; the physical session's portal is left alone."""
    want = {f"DBUS_SESSION_BUS_ADDRESS={bus}".encode(),
            f"DBUS_STARTER_ADDRESS={bus}".encode()}
    for p in PROC.iterdir():
        if not p.name.isdigit():
            continue
        try:
            if not (p / "comm").read_text().startswith("xdg-desktop-por"):
                continue
            if want & set((p / "environ").read_bytes().split(b"\0")):
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


def _token_mtime() -> int | None:
    try:
        return TOKEN_PATH.stat().st_mtime_ns
    except OSError:
        return None


def _wait_token(timeout_s: float, before: int | None) -> bool:
    """Consent = token newer than the one present before we started."""
    deadline = time.time() + timeout_s
    while True:
        now = _token_mtime()
        if now is not None and (before is None or now > before):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.1)


def grant(cfg: dict, timeout_s: float = 120) -> int:
    display = cfg.get("display") or ":0"
    if not _x_display_alive(display):
        print(f"doctor --grant needs a logged-in desktop on {display}; none found.")
        return 1
    bus = _seat_bus()
    if not bus:
        print("GNOME seat not running — start the agent first.")
        return 1
    if active_connections(cfg, True) > 0:
        print("A viewer is connected to this seat; disconnect first.")
        return 1
    ok = False
    before = _token_mtime()
    try:
        _set_activation_display(bus, display)
        _restart_seat_portal(bus)
        print("Click 'Allow' in the screen-share dialog on this box's screen.")
        threading.Thread(target=_trigger_stream, args=(cfg, timeout_s),
                         daemon=True).start()
        ok = _wait_token(timeout_s, before)
    except (OSError, RuntimeError) as e:
        print(f"Could not set up consent flow: {e}")
    finally:
        for step in (lambda: _set_activation_display(bus, ""),
                     lambda: _restart_seat_portal(bus)):
            try:
                step()
            except Exception as e:  # noqa: BLE001 - restore must continue
                print(f"restore step failed: {e}", flush=True)
    print("Consent granted." if ok else "No consent recorded.")
    return 0 if ok else 1
