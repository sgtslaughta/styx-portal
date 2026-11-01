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


_turn_seen = {"total": 0}


def _gw_state(cfg: dict) -> dict:
    try:
        d = json.loads(gw_state_path(cfg).read_text())
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def turn_bytes(cfg: dict, gateway_alive: bool) -> int:
    """TURN-relayed bytes since the previous call (>= 0). The gateway keeps a
    running total; a total below the last one means the gateway restarted."""
    total = _gw_state(cfg).get("turn_bytes_total") if gateway_alive else None
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        return 0
    last, _turn_seen["total"] = _turn_seen["total"], total
    return total - last if total >= last else total


def transport(cfg: dict, gateway_alive: bool) -> str:
    """The transport the running gateway/selkies were launched with."""
    t = _gw_state(cfg).get("transport") if gateway_alive else None
    t = t or (cfg.get("stream_settings") or {}).get("transport")
    return "webrtc" if t == "webrtc" else "websockets"


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
TTM_POOL_PATH = Path("/sys/module/ttm/parameters/page_pool_size")
MODULE_DIR = Path("/sys/module")
TTM_POOL_MAX = 524288   # pages = 2 GiB; kernel default is half of RAM


def seat_advisories(gnome: tuple[bool, str]) -> list[tuple[str, bool, str]]:
    """GNOME seat advisories for doctor (never gating: labwc is the fallback)."""
    ok, why = gnome
    return [("GNOME seat available", ok, "" if ok else f"{why} — falling back to labwc")]


def host_tuning_checks() -> list[tuple[str, bool, str]]:
    """Advisory gaming-performance checks: (label, ok, remedy). Never gates
    doctor's exit status — a powersave governor is a warning, not a fault."""
    rows = []
    if GOVERNOR_PATH.is_file():
        gov = GOVERNOR_PATH.read_text().strip()
        rows.append((f"cpu governor: {gov}", gov == "performance",
                     "" if gov == "performance" else
                     "for gaming: sudo cpupower frequency-set -g performance"))
    # amdgpu/xe cache freed GPU pages in the TTM pool (default ½ RAM); stream
    # buffer churn fills it and pushes the host into swap.
    if TTM_POOL_PATH.is_file() and any(
            (MODULE_DIR / d).is_dir() for d in ("amdgpu", "xe")):
        pool = int(TTM_POOL_PATH.read_text().strip() or 0)
        ok = 0 < pool <= TTM_POOL_MAX
        rows.append((f"ttm page pool: {pool * 4 // 1024} MiB", ok, "" if ok else
                     f"cap at 2 GiB: echo {TTM_POOL_MAX} | sudo tee {TTM_POOL_PATH}; "
                     f"echo 'options ttm page_pool_size={TTM_POOL_MAX}' | sudo tee "
                     "/etc/modprobe.d/ttm.conf && sudo update-initramfs -u"))
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
    if tmp.exists():
        print(f"Stale {tmp} exists (interrupted rollback?) — inspect/remove it first.")
        return 1
    install_dir.rename(tmp)
    prev.rename(install_dir)
    tmp.rename(prev)
    r = subprocess.run(["systemctl", "--user", "restart", "styx-agent"])
    if getattr(r, "returncode", 0):
        print("WARNING: service restart failed — run: systemctl --user restart styx-agent")
    print("Rolled back; current install is the previous version.")
    return 0
