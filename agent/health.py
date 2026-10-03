"""Health readers for the Styx agent: gateway state file + host tuning."""
import json
import shutil
import subprocess
import time
from pathlib import Path


def gw_state_path(cfg: dict) -> Path:
    return Path(cfg["install_dir"]) / "gw_state.json"


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


def idle_seconds(cfg: dict, gateway_alive: bool) -> float | None:
    """Seconds since the last client->server input frame (per the gateway
    state file). None when the gateway is down or the state is unreadable.
    Backend only acts on this when active_connections > 0."""
    if not gateway_alive:
        return None
    try:
        data = json.loads(gw_state_path(cfg).read_text())
        ts = data.get("last_input_ts")
        if not isinstance(ts, (int, float)):
            return None
        return max(0.0, time.time() - ts)
    except (OSError, ValueError):
        return None


def stream_starving_seconds(cfg: dict, gateway_alive: bool) -> float | None:
    """Seconds a connected viewer has waited with zero video frames, per the
    gateway state file. None when the gateway is down, no viewer is starving, or
    the state is unreadable.

    The gateway sets `stream_starving` when a viewer connects and clears it on
    the first video frame; it also re-arms mid-session when input arrives with
    no frames behind it (a wedged compositor/encoder). Either way this reports
    only a viewer who is asking for pixels and getting none — never a healthy
    screen that merely went static.
    """
    if not gateway_alive:
        return None
    try:
        d = json.loads(gw_state_path(cfg).read_text())
        if not d.get("stream_starving"):
            return None
        since = d.get("starving_since")
        if not isinstance(since, (int, float)):
            return None
        return max(0.0, time.time() - since)
    except (OSError, ValueError):
        return None


GOVERNOR_PATH = Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")


def host_tuning_checks() -> list[tuple[str, bool, str]]:
    """Advisory gaming-performance checks: (label, ok, remedy). Never gates
    doctor's exit status — a powersave governor is a warning, not a fault."""
    rows = []
    if GOVERNOR_PATH.is_file():
        gov = GOVERNOR_PATH.read_text().strip()
        rows.append((f"cpu governor: {gov}", gov == "performance",
                     "" if gov == "performance" else
                     "for gaming: sudo cpupower frequency-set -g performance"))
    if shutil.which("nvidia-smi"):
        r = subprocess.run(["nvidia-smi", "--query-gpu=persistence_mode",
                            "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=10)
        pm = r.stdout.strip().splitlines()[0].strip() if r.stdout.strip() else "?"
        rows.append((f"nvidia persistence mode: {pm}", pm == "Enabled",
                     "" if pm == "Enabled" else "enable: sudo nvidia-smi -pm 1"))
    return rows


def rollback(install_dir: Path) -> int:
    """Swap install_dir with install_dir.prev (left by enroll --upgrade), restart."""
    prev = install_dir.with_name(install_dir.name + ".prev")
    if not (install_dir.is_dir() and prev.is_dir()):
        print(f"No previous install at {prev}")
        return 1
    tmp = install_dir.with_name(install_dir.name + ".swap")
    install_dir.rename(tmp)
    prev.rename(install_dir)
    tmp.rename(prev)
    subprocess.run(["systemctl", "--user", "restart", "styx-agent"])
    print("Rolled back; current install is the previous version.")
    return 0
