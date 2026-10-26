"""Background loops and boot reconcile (moved out of main.py, unchanged)."""
import asyncio
import logging
from datetime import datetime, timezone

from sqlmodel import select

from app.config import Settings
from app.database import async_session
from app.models import Instance
from app.services.docker_manager import DockerManager
from app.services.k8s_runtime import instance_runtime
from app.services.session_monitor import SessionMonitor

logger = logging.getLogger("styx-portal")
_settings = Settings()


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


async def _monitor_tick(session, monitor, docker) -> None:
    """One monitor tick. The Docker pass may fail (no Docker on k8s); that must
    not stop workstation offline-marking or route refresh."""
    from app.services.route_writer import refresh_routes_from_db
    from app.services.workstations import mark_stale_offline

    try:
        changed = await _run_monitor_pass(session, monitor, docker)
    except Exception:  # noqa: BLE001 - docker may be absent (k8s); keep ticking
        logger.debug("docker monitor pass skipped", exc_info=True)
        changed = False
    ws_changed = await mark_stale_offline(session)
    await session.commit()
    if changed or ws_changed:
        await refresh_routes_from_db(session)


async def _session_monitor_loop():
    docker = instance_runtime()
    monitor = SessionMonitor(docker)
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                await _monitor_tick(session, monitor, docker)
        except Exception:
            pass


async def _log_portal_instances(docker) -> None:
    """Read-only: legacy instance containers may still sit on styx-portal next to the backend."""
    try:
        names = await asyncio.to_thread(docker.on_portal_network)
    except Exception:  # noqa: BLE001 - docker may be unavailable at boot
        logger.warning("portal network inspection skipped", exc_info=True)
        return
    for name in names:
        logger.error("instance container %s is on the portal network; "
                     "starting it again will isolate it", name)


async def _reconcile_instances_at_boot(session, docker) -> None:
    """Mark instances whose container is gone as stopped. If Docker is
    unreachable (k8s), nothing can be running: stop them all, warn once."""
    result = await session.exec(
        select(Instance).where(
            Instance.status.in_(["running", "idle", "paused", "pulling", "starting"])
        )
    )
    docker_down = False
    for inst in result.all():
        if inst.container_id:
            try:
                status = await asyncio.to_thread(docker.get_container_status, inst.container_id)
            except Exception:  # noqa: BLE001 - no docker socket
                if not docker_down:
                    docker_down = True
                    logger.warning("Docker unreachable at boot; marking active instances stopped", exc_info=True)
                inst.status = "stopped"
                session.add(inst)
                continue
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


async def _service_health_loop():
    from app.services.service_health import health_loop
    await health_loop(async_session)


async def _metrics_collection_loop():
    """Collect aggregate CPU/RAM every 30s for time-series."""
    from app.services.metrics_store import record_sample

    docker = instance_runtime()
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
                    u = await asyncio.to_thread(docker.instance_usage, inst.container_id)
                    total_cpu += u["cpu_percent"]
                    total_ram_pct += u["memory_percent"]
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

    if _settings.ROUTE_BACKEND == "k8s":
        return  # screenshots need the Docker socket (phase 4)
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


async def _health_sample_loop():
    """Sample diagnostics every 60s and record status + latency."""
    from app.services.diagnostics import run_diagnostics
    from app.services.health_store import record
    import time as _t

    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                result = await run_diagnostics(session)
            status = {c["key"]: c["ok"] for c in result["checks"]}
            latency = {c["key"]: c["latency_ms"] for c in result["checks"]}
            record(_t.time(), status, latency)
        except Exception:
            pass
