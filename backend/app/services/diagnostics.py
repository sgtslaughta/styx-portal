"""Component health checks. Every check is timed and never raises — a failure
becomes {ok: False, detail: <reason>}, not an exception."""
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from app.services.docker_manager import detect_gpu

_settings = Settings()
_DISK_FREE_WARN_PCT = 10.0


async def _timed(fn):
    start = time.monotonic()
    ok, detail = await fn()
    return ok, detail, round((time.monotonic() - start) * 1000)


async def _check_docker(docker) -> tuple[bool, str]:
    if not docker.ping():
        return False, "Docker not reachable (socket-proxy down?)"
    v = docker.version()
    return True, f"Engine {v or 'unknown'} via socket-proxy"


async def _check_database(session) -> tuple[bool, str]:
    try:
        await session.exec(text("SELECT 1"))
        return True, "writable"
    except Exception as e:  # noqa: BLE001
        return False, f"error: {e}"


def _check_traefik_routes() -> tuple[bool, str]:
    d = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    if not d.is_dir():
        return False, f"{d} missing"
    routes = d / "routes.yml"
    try:
        (d / ".w").write_text("x")
        (d / ".w").unlink()
    except Exception:  # noqa: BLE001
        return False, "directory not writable by backend user"
    if routes.exists():
        age = int(time.time() - routes.stat().st_mtime)
        return True, f"writable, routes.yml {age}s old"
    return True, "writable, no routes yet"


def _check_disk() -> tuple[bool, str]:
    du = shutil.disk_usage("/")
    free_pct = du.free / du.total * 100
    used_gb = (du.total - du.free) / 1024**3
    total_gb = du.total / 1024**3
    ok = free_pct >= _DISK_FREE_WARN_PCT
    return ok, f"{free_pct:.0f}% free ({used_gb:.0f}/{total_gb:.0f} GB)"


def _check_gpu() -> tuple[bool, str]:
    info = detect_gpu()
    return True, (f"{info['type']} detected" if info.get("available") else "none")


async def run_diagnostics(session, docker=None) -> dict:
    from app.services.docker_manager import DockerManager
    docker = docker or DockerManager(network_name=_settings.DOCKER_NETWORK)
    checks = []

    ok, detail, ms = await _timed(lambda: _check_docker(docker))
    checks.append({"key": "docker", "ok": ok, "latency_ms": ms, "detail": detail})

    ok, detail, ms = await _timed(lambda: _check_database(session))
    checks.append({"key": "database", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _tr(): return _check_traefik_routes()
    ok, detail, ms = await _timed(_tr)
    checks.append({"key": "traefik_routes", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _dk(): return _check_disk()
    ok, detail, ms = await _timed(_dk)
    checks.append({"key": "disk", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _gp(): return _check_gpu()
    ok, detail, ms = await _timed(_gp)
    checks.append({"key": "gpu", "ok": ok, "latency_ms": ms, "detail": detail})

    overall = all(c["ok"] for c in checks if c["key"] != "gpu")
    return {
        "ok": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
