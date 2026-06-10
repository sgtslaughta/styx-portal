"""In-memory metrics store with time-series ring buffer."""

import shutil
import time
from collections import deque
from threading import Lock

_lock = Lock()
_cpu_history: deque[float] = deque(maxlen=2880)  # 24h at 30s intervals
_ram_history: deque[float] = deque(maxlen=2880)
_timestamps: deque[float] = deque(maxlen=2880)


def record_sample(cpu: float, ram: float):
    with _lock:
        _cpu_history.append(cpu)
        _ram_history.append(ram)
        _timestamps.append(time.time())


def get_history(range_str: str = "1h") -> dict:
    ranges = {"1h": 120, "6h": 720, "24h": 2880}
    count = ranges.get(range_str, 120)

    with _lock:
        cpu = list(_cpu_history)[-count:]
        ram = list(_ram_history)[-count:]

    disk = shutil.disk_usage("/")
    total_gb = disk.total / 1024**3
    free_gb = disk.free / 1024**3

    images_size = 0.0
    volumes_size = 0.0
    try:
        import docker
        from app.config import Settings
        client = docker.DockerClient(base_url=Settings().DOCKER_SOCKET)
        # IMAGES endpoint is permitted by the socket proxy; /system/df is not.
        for img in client.images.list():
            images_size += img.attrs.get("Size", 0)
        images_size /= 1024**3
        # Volume sizes require /system/df (proxy-denied); report 0 rather than
        # bypass the proxy. Disk totals below still reflect real usage.
    except Exception:
        images_size = 0.0
        volumes_size = 0.0

    return {
        "aggregate_cpu": cpu,
        "aggregate_ram": ram,
        "storage": {
            "images_gb": round(images_size, 2),
            "volumes_gb": round(volumes_size, 2),
            "total_gb": round(total_gb, 1),
            "available_gb": round(free_gb, 1),
        },
    }
