#!/usr/bin/env python3
"""Styx workstation agent — supervises Selkies and heartbeats to the portal.

Stdlib only. Installed by enroll.sh to ~/.local/share/styx-agent/.
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

AGENT_VERSION = "0.2.0"
HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/styx-agent"
CONFIG_PATH = HOME / ".config/styx-agent/config.json"
LOG_DIR = INSTALL_DIR / "logs"
STATE_PATH = INSTALL_DIR / "state.json"   # last heartbeat result, for status/doctor


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text())


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


# --- Selkies process -------------------------------------------------------
def detect_encoder() -> str:
    if shutil.which("nvidia-smi") and subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True).returncode == 0:
        return "nvh264enc"
    if shutil.which("vainfo") and subprocess.run(
            ["vainfo"], capture_output=True).returncode == 0:
        return "vah264enc"
    return "x264enc"


XVFB_DISPLAY = ":100"


def display_plan(cfg: dict) -> tuple[bool, str]:
    """Return (start_xvfb, display).

    X11 sessions are captured live (mirror the real desktop on :0). Wayland
    and headless machines get a private Xvfb display — selkies-gstreamer is
    X11-only (ximagesrc), so this is the 'own session' those machines stream.
    """
    if cfg["display_server"] == "x11":
        return False, cfg.get("display") or os.environ.get("DISPLAY") or ":0"
    return True, cfg.get("xvfb_display", XVFB_DISPLAY)


def build_selkies_cmd(cfg: dict, display: str) -> tuple[list[str], dict]:
    """selkies-gstreamer v1.6.x is configured by CLI flags (addr/port/encoder/
    basic auth are flags, NOT env vars). It serves HTTP + WebSocket + WebRTC on
    a single port, so Traefik proxies straight to it.
    """
    s = cfg["stream_settings"]
    encoder = s.get("encoder", "auto")
    if encoder == "auto":
        encoder = detect_encoder()
    env = os.environ.copy()
    env["DISPLAY"] = display
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("PULSE_SERVER", f"unix:{env['XDG_RUNTIME_DIR']}/pulse/native")
    env["SELKIES_ENCODER"] = encoder  # belt-and-suspenders; the flag is authoritative
    launcher = Path(cfg["selkies_dir"]) / "selkies-gstreamer-run"
    cmd = [
        str(launcher),
        "--addr=0.0.0.0",
        f"--port={cfg['port']}",
        f"--encoder={encoder}",
        f"--basic_auth_user={cfg['selkies_user']}",
        f"--basic_auth_password={cfg['selkies_password']}",
    ]
    return cmd, env


def _write_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d))


def _start_xvfb(display: str, log) -> subprocess.Popen | None:
    """Start a private X server for Wayland/headless machines. Returns the
    Xvfb process, or None if Xvfb is missing (caller reports the error)."""
    if not shutil.which("Xvfb"):
        return None
    proc = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"],
        stdout=log, stderr=log)
    time.sleep(1.5)  # let the X socket appear before Selkies connects
    if shutil.which("openbox"):  # bare WM so the session isn't unusable
        subprocess.Popen(["openbox"], env={**os.environ, "DISPLAY": display},
                         stdout=log, stderr=log)
    return proc


def run(cfg: dict) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    selkies_log = open(LOG_DIR / "selkies.log", "ab", buffering=0)
    xvfb_log = open(LOG_DIR / "xvfb.log", "ab", buffering=0)
    start_xvfb, display = display_plan(cfg)
    cmd, env = build_selkies_cmd(cfg, display)
    proc: subprocess.Popen | None = None
    xvfb: subprocess.Popen | None = None
    interval = 30
    backoff = 2
    stopping = False

    def _stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stopping:
        if start_xvfb and (xvfb is None or xvfb.poll() is not None):
            xvfb = _start_xvfb(display, xvfb_log)
        if proc is None or proc.poll() is not None:
            if proc is not None:
                print(f"selkies exited rc={proc.returncode}; restarting in {backoff}s",
                      flush=True)
                time.sleep(min(backoff, 60))
                backoff *= 2
            proc = subprocess.Popen(cmd, env=env, stdout=selkies_log,
                                    stderr=selkies_log)
        if start_xvfb and xvfb is None:
            last_error = ("Xvfb not installed — Wayland/headless needs a virtual "
                          "X display. Run: sudo apt install xvfb openbox")
        elif proc.poll() is not None:
            last_error = f"selkies exited rc={proc.returncode} — see logs/selkies.log"
        else:
            last_error = None
        try:
            hb = api(cfg, "/api/agent/heartbeat", {
                "status": "online", "last_error": last_error,
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
                cmd, env = build_selkies_cmd(cfg, display)
                proc.terminate()
                proc.wait(timeout=10)
                proc = None
                continue
            interval = hb.get("heartbeat_interval_s", 30)
            backoff = 2
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            err = str(e)
            _write_state({"ts": time.time(), "ok": False, "error": err})
            print(f"heartbeat failed: {err}", flush=True)
        time.sleep(interval)

    for p in (proc, xvfb):
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
    launcher = Path(cfg["selkies_dir"]) / "selkies-gstreamer-run"
    ok &= _check("selkies installed", launcher.exists(), str(launcher))
    svc = subprocess.run(["systemctl", "--user", "is-active", "styx-agent"],
                         capture_output=True, text=True)
    ok &= _check("service active", svc.stdout.strip() == "active",
                 svc.stdout.strip())
    port_busy = socket.socket().connect_ex(("127.0.0.1", cfg["port"])) == 0
    ok &= _check(f"selkies listening :{cfg['port']}", port_busy,
                 "" if port_busy else "nothing listening — see logs/selkies.log")
    if cfg.get("ca_pin"):
        ok &= _check("TLS pin matches",
                     check_pin(cfg.get("server_cert", ""), cfg["ca_pin"]))
    try:
        api(cfg, "/api/agent/heartbeat", {"status": "online"})
        ok &= _check("server reachable + token valid", True)
    except Exception as e:
        ok &= _check("server reachable + token valid", False, str(e))
    enc = cfg["stream_settings"].get("encoder", "auto")
    ok &= _check("encoder", True,
                 detect_encoder() if enc == "auto" else enc)
    print("All checks passed." if ok else
          f"Some checks failed. Logs: {LOG_DIR}")
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
