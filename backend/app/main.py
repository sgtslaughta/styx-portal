import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.database import init_db, async_session, get_session
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.models import Instance, SessionEvent
from app.routers import templates, instances, registry, images
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.services.docker_manager import DockerManager
from app.services.session_monitor import SessionMonitor
from app.security.csrf import csrf_valid, CSRF_COOKIE, CSRF_HEADER, UNSAFE_METHODS

logger = logging.getLogger("selkies-hub")
_settings = Settings()

_CSRF_EXEMPT = {"/api/auth/login", "/api/auth/setup", "/api/auth/refresh", "/api/auth/accept-invite"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in UNSAFE_METHODS and request.url.path not in _CSRF_EXEMPT:
            if not csrf_valid(request.cookies.get(CSRF_COOKIE),
                              request.headers.get(CSRF_HEADER)):
                return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
        return await call_next(request)


async def _run_monitor_pass(session, monitor, docker) -> bool:
    """One reconcile pass over running/idle instances. Marks crashed containers
    stopped and applies idle auto-stop. Returns True if any instance stopped."""
    result = await session.exec(
        select(Instance).where(Instance.status.in_(["running", "idle"]))
    )
    instances = result.all()
    changed = False
    for inst in instances:
        if inst.container_id:
            status = await asyncio.to_thread(docker.get_container_status, inst.container_id)
            if status["status"] in ("not_found", "exited"):
                inst.status = "stopped"
                inst.stopped_at = datetime.now(timezone.utc)
                session.add(inst)
                changed = True
                continue
        actions = monitor.check_instance(inst, session)
        if "auto_stopped" in actions:
            changed = True
    return changed


async def _session_monitor_loop():
    from app.services.route_writer import refresh_routes_from_db

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    monitor = SessionMonitor(docker)
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                changed = await _run_monitor_pass(session, monitor, docker)
                await session.commit()
                if changed:
                    await refresh_routes_from_db(session)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Sync instance states — mark stale instances as stopped
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    async with async_session() as session:
        result = await session.exec(
            select(Instance).where(
                Instance.status.in_(["running", "idle", "paused", "pulling", "starting"])
            )
        )
        active = result.all()
        for inst in active:
            if inst.container_id:
                status = await asyncio.to_thread(docker.get_container_status, inst.container_id)
                if status["status"] == "paused" and inst.status == "paused":
                    pass
                elif status["status"] in ("not_found", "exited"):
                    logger.info(f"Instance {inst.name} container gone, marking stopped")
                    inst.status = "stopped"
                    session.add(inst)
            else:
                inst.status = "stopped"
                session.add(inst)
        await session.commit()

    # Write initial Traefik routes on startup
    from app.services.route_writer import refresh_routes_from_db
    async with async_session() as session:
        await refresh_routes_from_db(session)

    task = asyncio.create_task(_session_monitor_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    screenshot_task = asyncio.create_task(_screenshot_capture_loop())
    yield
    task.cancel()
    metrics_task.cancel()
    screenshot_task.cancel()


async def _metrics_collection_loop():
    """Collect aggregate CPU/RAM every 30s for time-series."""
    from app.services.metrics_store import record_sample

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as session:
                result = await session.exec(
                    select(Instance).where(Instance.status.in_(["running", "idle"]))
                )
                running = result.all()

            total_cpu = 0.0
            total_ram_pct = 0.0
            for inst in running:
                if not inst.container_id:
                    continue
                try:
                    raw = await asyncio.to_thread(docker.get_container_stats, inst.container_id)
                    cpu_d = raw.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - \
                            raw.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
                    sys_d = raw.get("cpu_stats", {}).get("system_cpu_usage", 0) - \
                            raw.get("precpu_stats", {}).get("system_cpu_usage", 0)
                    ncpu = raw.get("cpu_stats", {}).get("online_cpus", 1)
                    if sys_d > 0:
                        total_cpu += cpu_d / sys_d * ncpu * 100
                    mem = raw.get("memory_stats", {})
                    limit = mem.get("limit", 1)
                    usage = mem.get("usage", 0)
                    if limit > 0:
                        total_ram_pct += usage / limit * 100
                except Exception:
                    pass

            record_sample(round(total_cpu, 1), round(total_ram_pct, 1))
        except Exception:
            pass


async def _capture_running_instances(screenshots, targets):
    for inst, port, protocol in targets:
        if inst.status not in ("running", "idle") or not inst.container_id:
            continue
        try:
            await screenshots.capture(inst.id, inst.container_id, port, protocol)
        except Exception:
            pass


async def _screenshot_capture_loop():
    from app.services.screenshot import ScreenshotService
    from app.models import ServiceTemplate

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    screenshots = ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR, docker_manager=docker,
    )
    try:
        while True:
            await asyncio.sleep(_settings.SCREENSHOT_INTERVAL_SECONDS)
            try:
                async with async_session() as session:
                    result = await session.exec(
                        select(Instance).where(Instance.status.in_(["running", "idle"]))
                    )
                    rows = result.all()
                    targets = []
                    for inst in rows:
                        tmpl = await session.get(ServiceTemplate, inst.template_id)
                        port = tmpl.internal_port if tmpl else 3001
                        protocol = tmpl.internal_protocol if tmpl else "https"
                        targets.append((inst, port, protocol))
                await _capture_running_instances(screenshots, targets)
            except Exception:
                pass
    finally:
        await screenshots.close()


app = FastAPI(title="Selkies Hub", version="0.1.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    auth_spec=_settings.RATE_LIMIT_AUTH,
    default_spec=_settings.RATE_LIMIT_DEFAULT,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", f"https://{_settings.DOMAIN}"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)

app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])
app.include_router(registry.router, prefix="/api/registry/images", tags=["registry"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


_INSTANCE_UNAVAILABLE_HTML = r"""<!doctype html>
<meta charset="utf-8">
<title>Instance unavailable</title>
<meta http-equiv="refresh" content="3;url=/">
<script>
  (function () {
    var m = location.pathname.match(/^\/i\/([^\/]+)/);
    var q = m ? "?stopped=" + encodeURIComponent(m[1]) : "";
    location.replace("/" + q);
  })();
  /* This page handles /i/subdomain routes that are no longer running */
</script>
<p>Instance unavailable. Redirecting&hellip; <a href="/">My Instances</a></p>
"""


@app.get("/api/instance-unavailable", response_class=HTMLResponse)
async def instance_unavailable():
    return HTMLResponse(content=_INSTANCE_UNAVAILABLE_HTML)


@app.get("/api/system/gpu")
async def system_gpu():
    from app.services.docker_manager import detect_gpu
    return detect_gpu()


@app.get("/api/system/metrics")
async def system_metrics(session: AsyncSession = Depends(get_session)):
    import shutil
    from app.services.docker_manager import DockerManager, detect_gpu

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)

    result = await session.exec(
        select(Instance).where(Instance.status.in_(["running", "idle"]))
    )
    running = result.all()

    aggregate_cpu = 0.0
    aggregate_ram_mb = 0.0
    for inst in running:
        if not inst.container_id:
            continue
        try:
            raw = await asyncio.to_thread(docker.get_container_stats, inst.container_id)
            cpu_delta = raw.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - \
                        raw.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
            system_delta = raw.get("cpu_stats", {}).get("system_cpu_usage", 0) - \
                           raw.get("precpu_stats", {}).get("system_cpu_usage", 0)
            num_cpus = raw.get("cpu_stats", {}).get("online_cpus", 1)
            if system_delta > 0:
                aggregate_cpu += cpu_delta / system_delta * num_cpus * 100
            aggregate_ram_mb += raw.get("memory_stats", {}).get("usage", 0) / 1024 / 1024
        except Exception:
            pass

    disk = shutil.disk_usage("/")
    gpu_info = detect_gpu()

    events_result = await session.exec(
        select(SessionEvent).order_by(SessionEvent.id.desc()).limit(20)
    )
    events = events_result.all()

    instances_map = {}
    if events:
        inst_ids = list({e.instance_id for e in events})
        insts_result = await session.exec(select(Instance).where(Instance.id.in_(inst_ids)))
        instances_map = {i.id: i.name for i in insts_result.all()}

    recent_events = []
    for ev in events:
        recent_events.append({
            "type": ev.event_type,
            "instance": instances_map.get(ev.instance_id, ev.instance_id[:8]),
            "time": "now",
            "details": ev.details.get("error", "")[:100] if ev.details else None,
        })

    return {
        "aggregate_cpu": round(aggregate_cpu, 1),
        "aggregate_ram_mb": round(aggregate_ram_mb, 1),
        "disk_used_gb": round((disk.total - disk.free) / 1024**3, 1),
        "disk_total_gb": round(disk.total / 1024**3, 1),
        "recent_events": recent_events,
        "host": {
            "docker_version": "unknown",
            "gpu": gpu_info.get("type") or "None",
            "network": _settings.DOCKER_NETWORK,
        },
    }


@app.get("/api/system/metrics/history")
async def system_metrics_history(range: str = "1h"):
    from app.services.metrics_store import get_history
    return get_history(range)
