#!/usr/bin/env python3
"""Styx workstation agent — supervises selkies/pixelflux engine + gateway.

Installed by enroll.sh to ~/.local/share/styx-agent/; runs on the agent venv.
Subcommands: run | status | doctor | uninstall
"""
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AGENT_VERSION = "0.6.3"
HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/styx-agent"
CONFIG_PATH = HOME / ".config/styx-agent/config.json"
LOG_DIR = INSTALL_DIR / "logs"
STATE_PATH = INSTALL_DIR / "state.json"   # last heartbeat result, for status/doctor


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text())


sys.path.insert(0, str(Path(__file__).resolve().parent))
import refit  # noqa: E402
import engine  # noqa: E402  (installed next to this file by enroll.sh)
import seat_gnome  # noqa: E402
import seat_labwc  # noqa: E402
from portal_api import api, check_pin  # noqa: E402
from health import (  # noqa: E402
    active_connections, gw_state_path, host_tuning_checks, idle_seconds,
    rollback, seat_advisories, stream_starving_seconds)
from seat_gnome import Escalation, pick_seat_shell  # noqa: E402


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
    }
    cmd = [str(install / "venv/bin/python"), str(install / "gateway.py"),
           str(cfg["port"]), str(upstream_port)]
    return cmd, env


def health_payload(cfg: dict, selkies_alive: bool, gateway_alive: bool,
                   seat_shell: str = "", seat_restarts: int = 0,
                   degraded: bool = False) -> dict:
    return {
        "mode": cfg.get("mode", "mirror"),
        "engine": "pixelflux",
        "agent_version": AGENT_VERSION,
        "dri_node": engine.pick_dri_node(),
        "selkies_alive": selkies_alive,
        "gateway_alive": gateway_alive,
        "active_connections": active_connections(cfg, gateway_alive),
        "idle_seconds": idle_seconds(cfg, gateway_alive),
        "seat_shell": seat_shell or cfg.get("mode", "mirror"),
        "seat_restarts": seat_restarts,
        "degraded": degraded,
    }


def _write_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d))


def _terminate(p, timeout: int = 10) -> None:
    """Graceful stop of a child, escalating to kill on timeout."""
    if p is not None and p.poll() is None:
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
    The GNOME seat restarts only when its shell/geometry changed."""
    keys = ("selkies", "shell", "clipboard", "gateway")
    if any((old.get(k) or d) != (new.get(k) or d)
           for k, d in SEAT_DEFAULTS.items()):
        keys += ("seat",)
    return keys


def run(cfg: dict) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # Server-built binaries the distro lacks (nwg-drawer/nwg-dock) are pulled
    # into INSTALL_DIR/bin at enroll. Put it on PATH so both pick_launcher
    # (this process) and the seat shell_env (derived from os.environ) find them.
    bin_dir = str(INSTALL_DIR / "bin")
    if bin_dir not in os.environ.get("PATH", "").split(os.pathsep):
        os.environ["PATH"] = bin_dir + os.pathsep + os.environ.get("PATH", "")
    selkies_log = open(LOG_DIR / "selkies.log", "ab", buffering=0)
    gateway_log = open(LOG_DIR / "gateway.log", "ab", buffering=0)
    seat_log = open(LOG_DIR / "seat.log", "ab", buffering=0)

    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    shell_kind = pick_seat_shell(cfg)
    labwc = shell_kind == "labwc"
    if labwc:
        # Held (not used) for the agent's lifetime: keeps the compositors off
        # wayland-0, the slot WAYLAND_DISPLAY-less host apps fall back to.
        wayland0_guard = engine.guard_default_socket(runtime_dir)
        if wayland0_guard is None:
            print("wayland-0 owned by another session; seat will use a "
                  "higher slot", flush=True)
    gseat = (seat_gnome.GnomeSeat(INSTALL_DIR, runtime_dir, seat_log)
             if shell_kind == "gnome" else None)
    refit_req = INSTALL_DIR / "refit-request"
    refit.clear_request(refit_req)        # stale request from a previous run
    escalation, degraded = Escalation(), False
    last_engine_restart = float("-inf")   # watchdog grace after a restart
    exit_code = 0
    procs: dict[str, subprocess.Popen | None] = {
        "selkies": None, "gateway": None, "shell": None, "clipboard": None}
    seat_socket: str | None = None
    app_socket: str | None = None
    interval, backoff, stopping = 30, 2, False
    last_error: str | None = None
    internal_port = engine.pick_free_port()

    def _stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    def ensure_gnome_seat() -> bool:
        nonlocal last_error
        if gseat.alive():
            return True
        ss = cfg.get("stream_settings") or {}
        try:
            engine.ensure_seat_sink()   # seat audio -> styx-seat via PULSE_SINK
        except Exception as e:
            print(f"seat sink setup failed: {e}", flush=True)
        size = refit.read_size(gseat.size_file) or (
            int(ss.get("seat_width") or 2560), int(ss.get("seat_height") or 1440))
        gseat.start(*refit.clamp(*size))
        if not gseat.ready():
            last_error = "GNOME seat failed to start — see logs/seat.log"
            gseat.stop()
            return False
        return True

    def start_labwc_shell() -> None:
        """labwc shell on the seat socket, then the clipboard bridge between
        the seat socket and the socket labwc creates for its clients."""
        nonlocal app_socket
        before = {p.name for p in Path(runtime_dir).glob("wayland-*")
                  if not p.name.endswith(".lock")}
        since_ts = time.time() - 1
        procs["shell"] = seat_labwc.start_shell(
            INSTALL_DIR, seat_socket, runtime_dir, seat_log)
        if procs["shell"] is None:
            return
        # Exclude seat_socket: it was just created and matches the mtime
        # slack, so it'd be returned instead of labwc's.
        app_sock = engine.wait_for_wayland_socket(
            runtime_dir, before, since_ts, timeout=10, exclude={seat_socket})
        if app_sock:
            app_socket = app_sock
            print(f"app socket is {app_socket}; starting clipboard bridge",
                  flush=True)
            _terminate(procs.get("clipboard"), 5)
            procs["clipboard"] = seat_labwc.start_clipboard_bridge(
                INSTALL_DIR, seat_socket, app_socket, runtime_dir, LOG_DIR)

    def start_selkies():
        nonlocal last_error, seat_socket, app_socket
        seat_socket = app_socket = None
        # Kill the clipboard bridge since sockets are about to change
        _terminate(procs.get("clipboard"), 5)
        procs["clipboard"] = None
        if gseat and not ensure_gnome_seat():
            return None
        try:
            cmd, env = engine.build_selkies_cmd(
                cfg, internal_port, gseat.info() if gseat else None)
        except Exception as e:
            last_error = f"engine setup failed: {e}"
            return None
        if labwc:
            try:
                monitor = engine.ensure_seat_sink()
                cmd = [a for a in cmd if not a.startswith("--audio-device-name=")]
                cmd.append(f"--audio-device-name={monitor}")
            except Exception:
                pass  # default-sink monitor still works; just leaks to speakers
            try:
                engine.ensure_mic_source()
            except Exception:
                pass  # mic optional; selkies logs the gap if it matters
        before = {p.name for p in Path(runtime_dir).glob("wayland-*")
                  if not p.name.endswith(".lock")}
        since_ts = time.time() - 1  # 1s slack for coarse fs timestamps
        proc = subprocess.Popen(cmd, env=env, stdout=selkies_log,
                                stderr=selkies_log)
        if not labwc:
            return proc
        sock = engine.wait_for_wayland_socket(runtime_dir, before, since_ts)
        if not sock:
            last_error = ("compositor socket not found — seat has no "
                          "window manager. See logs/selkies.log")
            return proc
        seat_socket = sock
        # Clipboard/DPI helpers inside selkies address the seat as
        # wayland-{seat_socket_index}; if the compositor bound a
        # different index, persist it and restart selkies once.
        idx = int(sock.rsplit("-", 1)[1])
        if idx != cfg.get("seat_socket_index", 1):
            cfg["seat_socket_index"] = idx
            CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
            print(f"seat socket is {sock}; restarting selkies with "
                  f"matching index", flush=True)
            _terminate(proc)
            return None
        start_labwc_shell()
        if procs["shell"] is None and not shutil.which("labwc"):
            last_error = ("labwc not installed — seat has no window "
                          "manager. Install: sudo apt install labwc")
        return proc

    while not stopping:
        if gseat and not gseat.alive():
            # Seat died: selkies is captured against a dead portal session.
            # The next branch restarts it, which brings the seat back first.
            _terminate(procs["selkies"])
            procs["selkies"] = None
        if procs["selkies"] is None or procs["selkies"].poll() is not None:
            if procs["selkies"] is not None:
                print(f"selkies exited rc={procs['selkies'].returncode}; "
                      f"restart in {backoff}s", flush=True)
                time.sleep(min(backoff, 60))
                backoff *= 2
            procs["selkies"] = start_selkies()
        if procs["gateway"] is None or procs["gateway"].poll() is not None:
            cmd, env = build_gateway_cmd(
                cfg, internal_port, str(INSTALL_DIR) if gseat else "")
            procs["gateway"] = subprocess.Popen(cmd, env=env,
                                                stdout=gateway_log,
                                                stderr=gateway_log)
        selkies_ok = procs["selkies"] is not None and procs["selkies"].poll() is None
        if (labwc and seat_socket and selkies_ok
                and (procs["shell"] is None or procs["shell"].poll() is not None)):
            start_labwc_shell()   # shell restarts -> new socket -> new bridge
        if (labwc and app_socket and selkies_ok
                and (procs["clipboard"] is None or procs["clipboard"].poll() is not None)):
            # Clipboard bridge respawn (if socket didn't change)
            procs["clipboard"] = seat_labwc.start_clipboard_bridge(
                INSTALL_DIR, seat_socket, app_socket, runtime_dir, LOG_DIR)
        gateway_ok = procs["gateway"] is not None and procs["gateway"].poll() is None
        if selkies_ok and gateway_ok:
            if last_error and not last_error.startswith("labwc"):
                last_error = None
        elif not selkies_ok and last_error is None:
            last_error = "selkies not running — see logs/selkies.log"

        # Stream-start watchdog: a viewer is connected but the engine has
        # delivered no frame -> restart the engine so the fresh session's
        # START_VIDEO takes. Keys on real frames at the gateway.
        starving = stream_starving_seconds(cfg, gateway_ok)
        in_grace = time.monotonic() - last_engine_restart < FRAME_START_TIMEOUT_S
        if (selkies_ok and starving is not None and not in_grace
                and starving >= FRAME_START_TIMEOUT_S):
            print(f"watchdog: viewer frameless {int(starving)}s — restarting "
                  "selkies", flush=True)
            last_engine_restart = time.monotonic()
            if gseat:
                _terminate(procs["selkies"])
                procs["selkies"] = None
                if escalation.record(time.time()):
                    print("watchdog: 3 restarts in 10 min — restarting GNOME "
                          "seat", flush=True)
                    gseat.stop()
                    degraded = True
            else:
                _restart_engine(procs)
            continue

        try:
            hb = api(cfg, "/api/agent/heartbeat", {
                "status": "online" if selkies_ok and gateway_ok else "error",
                "last_error": last_error,
                "health": health_payload(
                    cfg, selkies_ok, gateway_ok, shell_kind,
                    gseat.restarts if gseat else 0, degraded),
            })
            _write_state({"ts": time.time(), "ok": True, "state": hb["state"]})
            if hb["state"] == "revoked":
                print("Revoked by server. Stopping. To remove this agent run:\n"
                      f"  python3 {INSTALL_DIR / 'styx_agent.py'} uninstall",
                      flush=True)
                break
            if hb.get("disconnect_clients"):
                print("server requested client disconnect (logout); "
                      "restarting gateway", flush=True)
                drop_clients(procs)
            if hb["stream_settings"] != cfg["stream_settings"]:
                old_ss = cfg["stream_settings"]
                cfg["stream_settings"] = hb["stream_settings"]
                CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
                new_shell = pick_seat_shell(cfg)
                if new_shell != shell_kind:
                    # Shell is chosen once per process; systemd (Restart=always)
                    # brings the agent back up on the new one.
                    print(f"seat_shell changed to {new_shell}; restarting agent",
                          flush=True)
                    exit_code = 1
                    break
                keys = settings_restart_keys(old_ss, hb["stream_settings"])
                for key in keys:
                    if key in procs:
                        _terminate(procs[key])
                        procs[key] = None
                if "seat" in keys and gseat:
                    gseat.stop()
                continue
            interval = hb.get("heartbeat_interval_s", 30)
            backoff = 2
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            _write_state({"ts": time.time(), "ok": False, "error": str(e)})
            print(f"heartbeat failed: {e}", flush=True)
        # GNOME seat: wake early when the gateway asks for a refit (size-at-connect).
        req = refit.wait_for_request(refit_req, interval) if gseat else time.sleep(interval)
        if req:
            if gseat.alive():
                print(f"refit: rebuilding seat monitor at {req[0]}x{req[1]}", flush=True)
                _terminate(procs["selkies"])
                procs["selkies"] = None
                if not gseat.refit(*req):
                    last_error = f"refit to {req[0]}x{req[1]} failed — kept previous size"
                last_engine_restart = time.monotonic()
            refit.clear_request(refit_req)

    for p in procs.values():
        _terminate(p)
    if gseat:
        gseat.stop()
    return exit_code


# --- Diagnostics -----------------------------------------------------------
def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def doctor(cfg: dict) -> int:
    print("styx-agent doctor:")
    ok = True
    ok &= _check("config readable", True, str(CONFIG_PATH))
    install = Path(cfg["install_dir"])
    ok &= _check("venv present", (install / "venv/bin/python").exists())
    ok &= _check("selkies 2.0 installed", (install / "venv/bin/selkies").exists())
    ok &= _check(f"mode: {cfg.get('mode', 'mirror')}", True)
    if cfg.get("mode") == "mirror":
        xa = engine._find_xauthority(cfg)
        ok &= _check("XAUTHORITY found", xa is not None, xa or "none")
    dri = engine.pick_dri_node()
    _check("GPU render node", bool(dri), dri or "CPU encode")
    mon = engine.resolve_monitor_source()
    ok &= _check("audio monitor source", bool(mon), mon or "no pulse/pipewire")
    svc = subprocess.run(["systemctl", "--user", "is-active", "styx-agent"],
                         capture_output=True, text=True)
    ok &= _check("service active", svc.stdout.strip() == "active",
                 svc.stdout.strip())
    port_busy = socket.socket().connect_ex(("127.0.0.1", cfg["port"])) == 0
    ok &= _check(f"gateway listening :{cfg['port']}", port_busy,
                 "" if port_busy else "nothing listening — see logs/gateway.log")
    if cfg.get("ca_pin"):
        ok &= _check("TLS pin matches",
                     check_pin(cfg.get("server_cert", ""), cfg["ca_pin"]))
    try:
        api(cfg, "/api/agent/heartbeat", {"status": "online"})
        ok &= _check("server reachable + token valid", True)
    except Exception as e:
        ok &= _check("server reachable + token valid", False, str(e))
    seat = cfg.get("mode") == "seat" and seat_advisories(seat_gnome.gnome_available())
    for label, good, detail in host_tuning_checks() + (seat or []):
        _check(label, good, detail)   # advisory: not folded into `ok`
    print("All checks passed." if ok else f"Some checks failed. Logs: {LOG_DIR}")
    return 0 if ok else 1


def status(cfg: dict) -> int:
    try:
        st = json.loads(STATE_PATH.read_text())
        age = int(time.time() - st["ts"])
        print(f"last heartbeat {age}s ago — "
              f"{'ok' if st.get('ok') else 'FAILED: ' + st.get('error', '?')}")
        return 0 if st.get("ok") else 1
    except FileNotFoundError:
        print("no heartbeat recorded yet — is the service running? "
              "(systemctl --user status styx-agent)")
        return 1


def uninstall(cfg: dict | None) -> int:
    subprocess.run(["systemctl", "--user", "disable", "--now", "styx-agent"],
                   capture_output=True)
    if cfg:
        try:
            api(cfg, "/api/agent/deregister", {})
            print("Deregistered from server.")
        except Exception as e:
            print(f"Could not deregister (server unreachable?): {e} — "
                  "remove it from the admin Workstations panel.")
    unit = HOME / ".config/systemd/user/styx-agent.service"
    unit.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    for d in (INSTALL_DIR, INSTALL_DIR.with_name(INSTALL_DIR.name + ".prev")):
        shutil.rmtree(d, ignore_errors=True)  # .prev: ~1.5 GB upgrade backup
    CONFIG_PATH.unlink(missing_ok=True)
    print("Styx agent removed.")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        cfg = load_config()
    except FileNotFoundError:
        cfg = None
    if cmd == "uninstall":
        return uninstall(cfg)
    if cmd == "rollback":
        return rollback(INSTALL_DIR)
    if cfg is None:
        print(f"Config missing at {CONFIG_PATH} — re-run enrollment.")
        return 1
    if cmd == "run":
        return run(cfg)
    if cmd == "doctor":
        return doctor(cfg)
    if cmd == "status":
        return status(cfg)
    print(f"Unknown command: {cmd} (expected run|status|doctor|rollback|uninstall)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
