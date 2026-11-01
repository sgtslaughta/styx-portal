"""Host CPU/RAM from /proc (no psutil). Return None when /proc is unavailable."""
from threading import Lock

_lock = Lock()
_last: tuple[int, int] | None = None   # (busy, total) jiffies at the previous reading


def _read_stat() -> tuple[int, int] | None:
    try:
        with open("/proc/stat") as f:
            vals = [int(x) for x in f.readline().split()[1:]]
    except (OSError, ValueError):
        return None
    total = sum(vals[:8])                       # user..steal (guest is already inside user)
    idle = vals[3] + (vals[4] if len(vals) > 4 else 0)   # idle + iowait
    return total - idle, total


def cpu_pct() -> float | None:
    """Host CPU % since the previous call (None on the first call or without /proc)."""
    global _last
    cur = _read_stat()
    if cur is None:
        return None
    with _lock:
        prev, _last = _last, cur
    if prev is None or cur[1] <= prev[1]:
        return None
    return round(100 * (cur[0] - prev[0]) / (cur[1] - prev[1]), 1)


def ram() -> tuple[float, int] | None:
    """(used %, total MB) from MemTotal/MemAvailable, or None."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                if k in ("MemTotal", "MemAvailable"):
                    info[k] = int(v.split()[0])
        total, avail = info["MemTotal"], info["MemAvailable"]
    except (OSError, ValueError, KeyError):
        return None
    if total <= 0:
        return None
    return round(100 * (total - avail) / total, 1), total // 1024
