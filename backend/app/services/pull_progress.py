"""In-memory per-instance image-pull progress, surfaced via the instance status
poll (no new transport). Resets on restart."""
from threading import Lock

_lock = Lock()
_progress: dict[str, dict] = {}


def set_progress(instance_id: str, percent: int, detail: str) -> None:
    """Store pull progress for an instance."""
    with _lock:
        _progress[instance_id] = {"percent": percent, "detail": detail}


def get(instance_id: str) -> dict | None:
    """Retrieve pull progress for an instance, or None if not present."""
    with _lock:
        return _progress.get(instance_id)


def clear(instance_id: str) -> None:
    """Clear pull progress for an instance."""
    with _lock:
        _progress.pop(instance_id, None)


def overall_percent(layers: list[dict]) -> int:
    """Rough overall % across layers that report totals."""
    cur = tot = 0
    for ev in layers:
        d = ev.get("progressDetail") or {}
        if d.get("total"):
            cur += d.get("current", 0)
            tot += d["total"]
    return int(cur / tot * 100) if tot else 0
