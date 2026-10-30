"""Host-side probes for the stream harness: once a second, the live selkies
process's CPU and memory and the GPU's busy / video-encoder busy and memory
(amdgpu sysfs). Summaries go into each A/B row; the soak keeps the raw series.
ponytail: amdgpu card0 only; an NVENC host reports CPU/RSS and None for GPU.
"""
import glob
import os
import statistics
import threading
import time
from pathlib import Path

INSTALL = Path.home() / ".local/share/styx-agent"
HZ = os.sysconf("SC_CLK_TCK")


def stat_ticks(stat: str) -> int:
    """utime + stime from a /proc/<pid>/stat line (fields 14 and 15)."""
    fields = stat[stat.rindex(")") + 2:].split()
    return int(fields[11]) + int(fields[12])


def cpu_percent(prev: int, cur: int, dt: float, hz: int = HZ) -> float:
    return 100.0 * (cur - prev) / hz / dt if dt > 0 else 0.0


def live_selkies_pid() -> int | None:
    """The selkies the gateway points at (<install>/selkies-port); the standby idles."""
    try:
        port = (INSTALL / "selkies-port").read_text().strip()
    except OSError:
        return None
    for d in glob.glob("/proc/[0-9]*/cmdline"):
        try:
            cmd = Path(d).read_bytes().replace(b"\0", b" ")
        except OSError:
            continue
        if b"engine.py" in cmd and f"--port={port}".encode() in cmd:
            return int(d.split("/")[2])
    return None


def _read(path: str) -> float | None:
    try:
        return float(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def gpu_sample() -> dict:
    dev = "/sys/class/drm/card0/device/"
    mb = 1024 * 1024
    vram, gtt = _read(dev + "mem_info_vram_used"), _read(dev + "mem_info_gtt_used")
    return {"gpu": _read(dev + "gpu_busy_percent"), "vcn": _read(dev + "vcn_busy_percent"),
            "vram_mb": vram / mb if vram is not None else None,
            "gtt_mb": gtt / mb if gtt is not None else None}


def summarize(samples: list) -> dict:
    """Mean and max per series, plus growth (last - first) for memory."""
    out = {}
    if not samples:
        return out
    for key in samples[0]:
        vals = [s[key] for s in samples if s.get(key) is not None]
        if not vals:
            continue
        out[f"{key}_mean"] = round(statistics.mean(vals), 1)
        out[f"{key}_max"] = round(max(vals), 1)
        if key.endswith("_mb"):
            out[f"{key}_growth"] = round(vals[-1] - vals[0], 1)
    return out


class Sampler(threading.Thread):
    """Samples every `every` seconds until stop(); `samples` holds the series."""

    def __init__(self, every: float = 1.0):
        super().__init__(daemon=True)
        self.every, self.samples, self._stop = every, [], threading.Event()

    def run(self):
        prev = None
        while not self._stop.wait(self.every):
            pid, now = live_selkies_pid(), time.monotonic()
            row = {"t": round(time.time(), 1), "cpu": None, "rss_mb": None, **gpu_sample()}
            try:
                stat = Path(f"/proc/{pid}/stat").read_text() if pid else ""
                ticks = stat_ticks(stat) if stat else None
                if ticks is not None and prev and prev[0] == pid:
                    row["cpu"] = round(cpu_percent(prev[1], ticks, now - prev[2]), 1)
                prev = (pid, ticks, now) if ticks is not None else None
                rss = [ln for ln in Path(f"/proc/{pid}/status").read_text().splitlines()
                       if ln.startswith("VmRSS:")] if pid else []
                row["rss_mb"] = int(rss[0].split()[1]) / 1024 if rss else None
            except OSError:
                prev = None
            self.samples.append(row)

    def stop(self) -> dict:
        self._stop.set()
        self.join(timeout=5)
        return summarize([{k: v for k, v in s.items() if k != "t"} for s in self.samples])
