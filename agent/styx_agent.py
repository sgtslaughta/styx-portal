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
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path

AGENT_VERSION = "0.4.1"
HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/styx-agent"
CONFIG_PATH = HOME / ".config/styx-agent/config.json"
LOG_DIR = INSTALL_DIR / "logs"
STATE_PATH = INSTALL_DIR / "state.json"   # last heartbeat result, for status/doctor


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text())


sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402  (installed next to this file by enroll.sh)


# --- TLS pinning -----------------------------------------------------------
# Enrollment verified the server certificate's SHA256 fingerprint against the
# pin embedded in the minted command and saved the cert to server_cert (PEM).
# We use that cert as the ONLY trusted CA — full chain verification against
# the pinned cert, never an unverified connection. Hostname check is off
# because self-signed LAN certs rarely carry the LAN IP in their SAN; trust
# comes from the pin, not the name.
def _ssl_context(cfg: dict) -> ssl.SSLContext:
    cert_file = cfg.get("server_cert", "")
    if cert_file and Path(cert_file).is_file():
        ctx = ssl.create_default_context(cafile=cert_file)
        ctx.check_hostname = False
        return ctx
    return ssl.create_default_context()


def check_pin(cert_file: str, ca_pin: str) -> bool:
    """Doctor check: pinned cert file still matches the fingerprint."""
    if not ca_pin or not cert_file:
        return True
    expected = ca_pin.split(":", 1)[1].replace(":", "").lower()
    pem = Path(cert_file).read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    return sha256(der).hexdigest() == expected


def api(cfg: dict, path: str, payload: dict | None = None) -> dict:
    url = cfg["server"].rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Authorization": f"Bearer {cfg['agent_token']}",
                 "Content-Type": "application/json"})
    ctx = _ssl_context(cfg) if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode() or "{}")


def gw_state_path(cfg: dict) -> Path:
    return Path(cfg["install_dir"]) / "gw_state.json"


def build_gateway_cmd(cfg: dict, upstream_port: int) -> tuple[list[str], dict]:
    install = Path(cfg["install_dir"])
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "STYX_GW_USER": cfg["selkies_user"],
        "STYX_GW_PASSWORD": cfg["selkies_password"],
        "STYX_GW_STATE": str(gw_state_path(cfg)),
    }
    cmd = [str(install / "venv/bin/python"), str(install / "gateway.py"),
           str(install / "web"), str(cfg["port"]),
           str(upstream_port)]
    return cmd, env


def active_connections(cfg: dict, gateway_alive: bool) -> int:
    """Live stream-websocket count from the gateway's state file. A dead
    gateway means no viewers regardless of what the file says."""
    if not gateway_alive:
        return 0
    try:
        n = json.loads(gw_state_path(cfg).read_text()).get("active_connections")
        return n if isinstance(n, int) and n >= 0 else 0
    except (OSError, ValueError):
        return 0


def health_payload(cfg: dict, selkies_alive: bool, gateway_alive: bool) -> dict:
    return {
        "mode": cfg.get("mode", "mirror"),
        "engine": "pixelflux",
        "agent_version": AGENT_VERSION,
        "dri_node": engine.pick_dri_node(),
        "selkies_alive": selkies_alive,
        "gateway_alive": gateway_alive,
        "active_connections": active_connections(cfg, gateway_alive),
    }


def _write_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d))


def run(cfg: dict) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    selkies_log = open(LOG_DIR / "selkies.log", "ab", buffering=0)
    gateway_log = open(LOG_DIR / "gateway.log", "ab", buffering=0)
    seat_log = open(LOG_DIR / "seat.log", "ab", buffering=0)

    seat_mode = cfg.get("mode") == "seat"
    runtime_dir = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    if seat_mode:
        # Held (not used) for the agent's lifetime: keeps the compositors off
        # wayland-0, the slot WAYLAND_DISPLAY-less host apps fall back to.
        wayland0_guard = engine.guard_default_socket(runtime_dir)
        if wayland0_guard is None:
            print("wayland-0 owned by another session; seat will use a "
                  "higher slot", flush=True)
    procs: dict[str, subprocess.Popen | None] = {
        "selkies": None, "gateway": None, "shell": None}
    seat_socket: str | None = None
    interval, backoff, stopping = 30, 2, False
    last_error: str | None = None
    internal_port = engine.pick_free_port()
    control_port = engine.pick_free_port()

    def _stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    def start_shell():
        if not (seat_socket and shutil.which("labwc")):
            return None
        engine.write_seat_config(INSTALL_DIR / "labwc")
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
        return subprocess.Popen(["labwc", "-C", str(INSTALL_DIR / "labwc")],
                                env=shell_env, stdout=seat_log, stderr=seat_log)

    def start_selkies():
        nonlocal last_error, seat_socket
        seat_socket = None
        try:
            cmd, env = engine.build_selkies_cmd(cfg, internal_port, control_port)
        except Exception as e:
            last_error = f"engine setup failed: {e}"
            return None
        if seat_mode:
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
        if seat_mode:
            sock = engine.wait_for_wayland_socket(runtime_dir, before, since_ts)
            if sock:
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
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    return None
                procs["shell"] = start_shell()
                if procs["shell"] is None and not shutil.which("labwc"):
                    last_error = ("labwc not installed — seat has no window "
                                  "manager. Install: sudo apt install labwc")
            else:
                last_error = ("compositor socket not found — seat has no "
                              "window manager. See logs/selkies.log")
        return proc

    while not stopping:
        if procs["selkies"] is None or procs["selkies"].poll() is not None:
            if procs["selkies"] is not None:
                print(f"selkies exited rc={procs['selkies'].returncode}; "
                      f"restart in {backoff}s", flush=True)
                time.sleep(min(backoff, 60))
                backoff *= 2
            procs["selkies"] = start_selkies()
        if procs["gateway"] is None or procs["gateway"].poll() is not None:
            cmd, env = build_gateway_cmd(cfg, internal_port)
            procs["gateway"] = subprocess.Popen(cmd, env=env,
                                                stdout=gateway_log,
                                                stderr=gateway_log)
        if (seat_mode and seat_socket
                and procs["selkies"] is not None
                and procs["selkies"].poll() is None
                and (procs["shell"] is None or procs["shell"].poll() is not None)):
            procs["shell"] = start_shell()
        selkies_ok = procs["selkies"] is not None and procs["selkies"].poll() is None
        gateway_ok = procs["gateway"] is not None and procs["gateway"].poll() is None
        if selkies_ok and gateway_ok:
            if last_error and not last_error.startswith("labwc"):
                last_error = None
        elif not selkies_ok and last_error is None:
            last_error = "selkies not running — see logs/selkies.log"

        try:
            hb = api(cfg, "/api/agent/heartbeat", {
                "status": "online" if selkies_ok and gateway_ok else "error",
                "last_error": last_error,
                "health": health_payload(cfg, selkies_ok, gateway_ok),
            })
            _write_state({"ts": time.time(), "ok": True, "state": hb["state"]})
            if hb["state"] == "revoked":
                print("Revoked by server. Stopping. To remove this agent run:\n"
                      f"  python3 {INSTALL_DIR / 'styx_agent.py'} uninstall",
                      flush=True)
                break
            if hb["stream_settings"] != cfg["stream_settings"]:
                cfg["stream_settings"] = hb["stream_settings"]
                CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
                for key in ("selkies", "shell"):
                    p = procs[key]
                    if p is not None and p.poll() is None:
                        p.terminate()
                        p.wait(timeout=10)
                    procs[key] = None
                continue
            interval = hb.get("heartbeat_interval_s", 30)
            backoff = 2
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            _write_state({"ts": time.time(), "ok": False, "error": str(e)})
            print(f"heartbeat failed: {e}", flush=True)
        time.sleep(interval)

    for p in procs.values():
        if p is not None and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
    return 0


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
    ok &= _check("web dist present", (install / "web/index.html").exists())
    ok &= _check("lib shim present", (install / "lib").is_dir(),
                 str(install / "lib"))
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
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
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
    if cfg is None:
        print(f"Config missing at {CONFIG_PATH} — re-run enrollment.")
        return 1
    if cmd == "run":
        return run(cfg)
    if cmd == "doctor":
        return doctor(cfg)
    if cmd == "status":
        return status(cfg)
    print(f"Unknown command: {cmd} (expected run|status|doctor|uninstall)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
