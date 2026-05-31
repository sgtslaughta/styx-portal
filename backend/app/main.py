import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import init_db, async_session, get_session
from app.models import Instance, SessionEvent
from app.routers import templates, instances, registry, images
from app.services.docker_manager import DockerManager
from app.services.session_monitor import SessionMonitor

logger = logging.getLogger("selkies-hub")
_settings = Settings()


async def _session_monitor_loop():
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    monitor = SessionMonitor(docker)
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                result = await session.exec(
                    select(Instance).where(
                        Instance.status.in_(["running", "idle"])
                    )
                )
                running_instances = result.all()
                for inst in running_instances:
                    monitor.check_instance(inst, session)
                await session.commit()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    # Generate or load admin token
    token_path = Path(_settings.SCREENSHOT_CACHE_DIR).parent / ".admin_token"
    if token_path.exists():
        admin_token = token_path.read_text().strip()
    else:
        admin_token = secrets.token_urlsafe(32)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(admin_token)
    app.state.admin_token = admin_token
    logger.warning(f"\n{'='*60}\n  ADMIN TOKEN: {admin_token}\n{'='*60}\n")

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
    from app.services.route_writer import write_routes
    from app.models import ServiceTemplate
    async with async_session() as session:
        result = await session.exec(
            select(Instance).where(Instance.status.in_(["running", "idle"]))
        )
        running = result.all()
        instances_data = []
        for i in running:
            tmpl = await session.get(ServiceTemplate, i.template_id)
            instances_data.append({
                "id": i.id, "subdomain": i.subdomain,
                "port": tmpl.internal_port if tmpl else 3001,
                "protocol": tmpl.internal_protocol if tmpl else "https",
            })
        write_routes(instances_data)

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
    for inst, port in targets:
        if inst.status not in ("running", "idle") or not inst.container_id:
            continue
        try:
            await screenshots.capture(inst.id, inst.container_id, port)
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
                        targets.append((inst, port))
                await _capture_running_instances(screenshots, targets)
            except Exception:
                pass
    finally:
        await screenshots.close()


app = FastAPI(title="Selkies Hub", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", f"https://{_settings.DOMAIN}"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])
app.include_router(registry.router, prefix="/api/registry/images", tags=["registry"])
app.include_router(images.router, prefix="/api/images", tags=["images"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


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
