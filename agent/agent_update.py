"""Agent-side hook for remote self-update (the work is done by agent_updater.py)."""
import json
import os
import shutil
import subprocess
from pathlib import Path

INSTALL_DIR = Path(__file__).resolve().parent
STATE = INSTALL_DIR / "update-state.json"
CONFIG_PATH = Path.home() / ".config/styx-agent/config.json"
UNIT = "styx-agent-update"


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, capture_output=True).returncode


def report() -> dict | None:
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return None


def on_heartbeat(cfg: dict, hb: dict) -> None:
    upd = hb.get("update")
    if not upd:
        return
    if _run(["systemctl", "--user", "is-active", "--quiet", UNIT]) == 0:
        return
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or "/tmp")
    copy = runtime / "styx-agent-updater.py"
    shutil.copyfile(INSTALL_DIR / "agent_updater.py", copy)
    _run(["systemd-run", "--user", f"--unit={UNIT}", "--collect", "/usr/bin/python3",
          str(copy), "--install-dir", str(INSTALL_DIR), "--config", str(CONFIG_PATH),
          "--target", str(upd["version"])])
    print(f"agent update to {upd['version']} started", flush=True)


def confirm(version: str) -> None:
    s = report()
    if s and s.get("state") == "updating" and s.get("to") == version:
        s["state"] = "ok"
        tmp = STATE.with_name(STATE.name + ".tmp")
        tmp.write_text(json.dumps(s))
        os.replace(tmp, STATE)
