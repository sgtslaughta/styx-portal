"""Child-process supervision and check-printing helpers for the styx agent."""
import json
import os
import subprocess
from pathlib import Path

from health import gw_state_path


def build_gateway_cmd(cfg: dict, upstream_port: int,
                      seat_dir: str = "") -> tuple[list[str], dict]:
    install = Path(cfg["install_dir"])
    # Idle timeout rides in stream_settings (resolved by the backend each
    # heartbeat: per-workstation override else system default). The gateway is
    # the idle authority; these env vars configure it.
    ss = cfg.get("stream_settings") or {}
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "STYX_GW_USER": cfg["selkies_user"],
        "STYX_GW_PASSWORD": cfg["selkies_password"],
        "STYX_GW_STATE": str(gw_state_path(cfg)),
        "STYX_GW_IDLE_TIMEOUT_S": str(ss.get("idle_timeout_s", 0)),
        "STYX_GW_IDLE_WARN_S": str(ss.get("idle_warn_lead_s", 60)),
        "STYX_GW_IDLE_ENABLED": "1" if ss.get("idle_timeout_enabled") else "",
        "STYX_GW_SEAT_DIR": seat_dir,
        "STYX_GW_ICON_DIR": str(install),
    }
    cmd = [str(install / "venv/bin/python"), str(install / "gateway.py"),
           str(cfg["port"]), str(upstream_port)]
    return cmd, env


def _terminate(p, timeout: int = 10) -> None:
    """Graceful stop of a child, escalating to kill on timeout (0 = kill now)."""
    if p is not None and p.poll() is None:
        if timeout <= 0:
            p.kill()
            p.wait()
            return
        p.terminate()
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            p.kill()


def _restart_engine(procs: dict) -> None:
    """Tear down the engine and (seat mode) its shell + clipboard so the
    supervisor loop rebuilds all three fresh. In seat mode selkies IS the
    Wayland compositor: restarting it changes the socket, so labwc/clipboard
    must come back too or they cling to the dead socket. The gateway is left
    running — it's the viewer's link home, and the browser reconnects through it.
    """
    for key in ("selkies", "shell", "clipboard"):
        _terminate(procs.get(key))
        procs[key] = None


def drop_clients(procs: dict) -> None:
    """Force live stream clients to disconnect by restarting the gateway.

    Set None so the supervisor loop respawns it next pass. Browsers reconnect
    through the portal's forward-auth, which fails once the user has logged out
    — so the session genuinely ends rather than silently resuming.
    """
    _terminate(procs.get("gateway"))
    procs["gateway"] = None


# --- stream watchdogs ------------------------------------------------------
# Stream-start watchdog: how long a connected viewer may sit frameless before
# the engine is restarted. Must exceed connect->first-frame time (NVENC init +
# first FullFrame is a few seconds); 15s leaves margin. ponytail: bump if slow
# hosts trip it on legitimately cold starts.
FRAME_START_TIMEOUT_S = 15

SEAT_DEFAULTS = {"seat_shell": "gnome", "seat_width": 2560, "seat_height": 1440}


def settings_restart_keys(old: dict, new: dict) -> tuple[str, ...]:
    """Procs to relaunch on a stream_settings push. The gateway is always in:
    idle-timeout config reaches it only through its launch env (STYX_GW_IDLE_*).
    The GNOME seat restarts only when its shell/geometry/framerate changed."""
    keys = ("selkies", "standby", "shell", "clipboard", "gateway")
    gnome = (new.get("seat_shell") or "gnome") == "gnome"
    # framerate caps the gnome helper's capture (--max-fps); labwc ignores it
    if any((old.get(k) or d) != (new.get(k) or d)
           for k, d in SEAT_DEFAULTS.items()) or (
            gnome and (old.get("framerate") or 60) != (new.get("framerate") or 60)):
        keys += ("seat",)
    return keys


def viewers_connected(state_path) -> bool:
    """True when the gateway state file reports live stream websockets."""
    try:
        n = json.loads(Path(state_path).read_text()).get("active_connections")
    except (OSError, ValueError, AttributeError):
        return False
    return isinstance(n, int) and n > 0


# Security settings never wait for viewers to leave: an admin enabling the
# idle timeout must not be outlasted by the very session it targets.
IMMEDIATE_KEYS = ("idle_timeout_s", "idle_warn_lead_s", "idle_timeout_enabled")


def must_apply_now(old_ss: dict, new_ss: dict) -> bool:
    return any(old_ss.get(k) != new_ss.get(k) for k in IMMEDIATE_KEYS)


def restart_plan(pending: dict | None, apply_now: bool, viewers: bool) -> tuple[tuple, dict | None]:
    """(keys to restart now, pending left over). Nobody connected: everything.
    Viewers but a security change: only the gateway (it alone reads the idle
    config from its launch env); the rest keeps waiting for the last viewer."""
    if not pending:
        return (), None
    if not viewers:
        return tuple(pending["keys"]), None
    if not apply_now:
        return (), pending
    rest = tuple(k for k in pending["keys"] if k != "gateway")
    return ("gateway",), ({"old": pending["old"], "keys": rest} if rest else None)


def merge_pending(pending: dict | None, old_ss: dict, new_ss: dict) -> dict:
    """Fold a settings push into a deferred restart: keep the earliest old
    settings, union the restart keys."""
    keys = settings_restart_keys(old_ss, new_ss)
    if pending is None:
        return {"old": old_ss, "keys": keys}
    return {"old": pending["old"],
            "keys": tuple(dict.fromkeys(pending["keys"] + keys))}


def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return ok
