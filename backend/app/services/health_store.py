"""In-memory ring buffer of diagnostic samples (status + latency per check).

Resets on process restart — acceptable for a single-host portal; not persisted."""
from collections import deque
from threading import Lock

_MAXLEN = 2880  # 24h at 60s
_lock = Lock()
_timestamps: deque[float] = deque(maxlen=_MAXLEN)
_status: dict[str, deque[bool]] = {}
_latency: dict[str, deque[int]] = {}

_RANGES = {"1h": 120, "6h": 720, "24h": 2880}


def reset() -> None:
    with _lock:
        _timestamps.clear()
        _status.clear()
        _latency.clear()


def record(ts: float, status: dict[str, bool], latency: dict[str, int]) -> None:
    with _lock:
        _timestamps.append(ts)
        n = len(_timestamps)
        for key, ok in status.items():
            _status.setdefault(key, deque(maxlen=_MAXLEN))
            while len(_status[key]) < n - 1:
                _status[key].append(ok)
            _status[key].append(ok)
        for key, ms in latency.items():
            _latency.setdefault(key, deque(maxlen=_MAXLEN))
            while len(_latency[key]) < n - 1:
                _latency[key].append(ms)
            _latency[key].append(ms)


def get_history(range_str: str = "1h") -> dict:
    count = _RANGES.get(range_str, 120)
    with _lock:
        ts = list(_timestamps)[-count:]
        status = {k: list(v)[-count:] for k, v in _status.items()}
        latency = {k: list(v)[-count:] for k, v in _latency.items()}
    return {"timestamps": ts, "status": status, "latency_ms": latency}
