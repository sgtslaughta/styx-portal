import asyncio
import re
import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import Settings
from app.database import init_db, async_session, get_session
from app.middleware.rate_limit import RateLimitMiddleware
from app.security.same_origin import svc_cookie_guard
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.models import Instance, SessionEvent, User
from app.services.screenshot_url import service_thumbnail_loop
from app.routers import templates, instances, registry, images, instance_thumbs
from app.routers import auth as auth_router
from app.routers import users as users_router
from app.routers import matrix as matrix_router
from app.routers import oauth as oauth_router
from app.routers import oauth_admin as oauth_admin_router
from app.routers import audit as audit_router
from app.routers import workstations as workstations_router
from app.routers import instance_auth as instance_auth_router
from app.routers import enroll as enroll_router
from app.routers import agent as agent_router
from app.routers import system_settings as system_settings_router
from app.routers import turn_usage as turn_usage_router
from app.routers import groups as groups_router
from app.routers import profiles as profiles_router
from app.routers import services as services_router
from app.routers import service_mounts as service_mounts_router
from app.routers import service_icons as service_icons_router
from app.routers import services_auth as services_auth_router
from app.security.deps import get_current_user, require_admin
from app.services.docker_manager import DockerManager
from app.services.k8s_runtime import instance_runtime
from app.services.k8s_prepull import prepull_loop
from app.services.background_loops import (  # noqa: F401 - re-exported for tests
    _capture_running_instances, _health_sample_loop, _log_portal_instances,
    _metrics_collection_loop, _monitor_tick, _reconcile_instances_at_boot,
    _run_monitor_pass, _screenshot_capture_loop, _service_health_loop,
    _session_monitor_loop)
from app.services.mount_jobs import sweep_interrupted
from app.security.csrf import csrf_valid, CSRF_COOKIE, CSRF_HEADER, UNSAFE_METHODS

logger = logging.getLogger("styx-portal")
_settings = Settings()

_CSRF_EXEMPT = {"/api/auth/login", "/api/auth/login/matrix", "/api/auth/setup"}
_CSRF_EXEMPT_PREFIXES = ("/api/enroll/", "/api/agent/")


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if (request.method in UNSAFE_METHODS
                and request.url.path not in _CSRF_EXEMPT
                and not request.url.path.startswith(_CSRF_EXEMPT_PREFIXES)):
            if not csrf_valid(request.cookies.get(CSRF_COOKIE),
                              request.headers.get(CSRF_HEADER)):
                return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail fast at boot if the auth secret is misconfigured, rather than
    # returning an opaque 500 the first time a token is minted (e.g. /auth/setup).
    try:
        _settings.jwt_secret_or_raise()
    except RuntimeError as e:
        logger.critical("FATAL: %s", e)
        raise

    # Before anything that can join another docker network (screenshots): see rate_limit.
    from app.middleware.rate_limit import _tunnel_pod_ips, snapshot_own_networks
    snapshot_own_networks()
    _tunnel_pod_ips()   # k8s: start the first cloudflared pod lookup (no-op in compose)

    await init_db()

    async with async_session() as _s:
        from app.security import setup_token
        from app.security.setup_gate import users_exist
        setup_token.announce(not await users_exist(_s))

    async with async_session() as _s:
        _n = await sweep_interrupted(_s)
        if _n:
            logger.warning("Marked %d interrupted mount job(s) failed", _n)

    from app.services.settings_store import settings as _settings_store
    async with async_session() as _s:
        await _settings_store.reload(_s)

    if _settings.ROUTE_BACKEND != "k8s":  # no Docker on k8s, so no probe containers either
        try:
            _p = await asyncio.to_thread(DockerManager(network_name=_settings.DOCKER_NETWORK).remove_probe_containers)
            if _p:
                logger.warning("Removed %d leftover probe container(s)", _p)
        except Exception:  # noqa: BLE001 - docker may be unavailable at boot
            logger.warning("Probe container cleanup skipped", exc_info=True)

    # Sync instance states — mark stale instances as stopped
    docker = instance_runtime()
    async with async_session() as session:
        await _reconcile_instances_at_boot(session, docker)
        await _log_portal_instances(docker)

    # Write initial Traefik routes on startup
    from app.services.route_writer import refresh_routes_from_db
    async with async_session() as session:
        await refresh_routes_from_db(session)

    task = asyncio.create_task(_session_monitor_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    screenshot_task = asyncio.create_task(_screenshot_capture_loop())
    svc_thumb_task = asyncio.create_task(service_thumbnail_loop(async_session, _settings.SCREENSHOT_CACHE_DIR))
    health_task = asyncio.create_task(_health_sample_loop())
    svc_health_task = asyncio.create_task(_service_health_loop())
    prepull_task = asyncio.create_task(prepull_loop()) if _settings.ROUTE_BACKEND == "k8s" else None
    yield
    task.cancel()
    metrics_task.cancel()
    screenshot_task.cancel()
    svc_thumb_task.cancel()
    health_task.cancel()
    svc_health_task.cancel()
    if prepull_task:
        prepull_task.cancel()
    await asyncio.gather(svc_health_task, return_exceptions=True)


try:
    # Version is stamped into pyproject.toml by scripts/stamp-version.sh at release
    # build time (semantic-release is the source of truth). Falls back in dev/editable.
    _APP_VERSION = _pkg_version("styx-portal-backend")
except PackageNotFoundError:  # pragma: no cover
    _APP_VERSION = "0.0.0"


def docs_kwargs(s: Settings) -> dict:
    """API docs are an unauthenticated map of every route: off unless explicitly enabled."""
    return {} if s.ENABLE_DOCS else {"docs_url": None, "redoc_url": None, "openapi_url": None}


app = FastAPI(title="Styx Portal", version=_APP_VERSION, lifespan=lifespan,
              **docs_kwargs(_settings),
              dependencies=[Depends(svc_cookie_guard)])

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(RateLimitMiddleware)
def cors_origins(s: Settings) -> list[str]:
    origins = [f"https://{s.DOMAIN}"]
    if s.DEV_CORS and not s.COOKIE_SECURE:   # explicit dev opt-in only
        origins.append("http://localhost:5173")
    return origins


_cors_origins = cors_origins(_settings)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Styx-Client"],
)

app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(instance_thumbs.router, prefix="/api/instances", tags=["instances"])
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])
app.include_router(registry.router, prefix="/api/registry/images", tags=["registry"])
app.include_router(images.router, prefix="/api/images", tags=["images"])
app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(matrix_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])
app.include_router(oauth_router.router, prefix="/api/auth/oauth", tags=["oauth"])
app.include_router(oauth_admin_router.router, prefix="/api/oauth-providers", tags=["oauth-admin"])
app.include_router(audit_router.router, prefix="/api/audit", tags=["audit"])
app.include_router(workstations_router.router, prefix="/api/workstations", tags=["workstations"])
app.include_router(workstations_router.internal_router, prefix="/internal/workstations",
                   tags=["workstations"])
app.include_router(enroll_router.router, prefix="/api/enroll", tags=["enroll"])
app.include_router(agent_router.router, prefix="/api/agent", tags=["agent"])
app.include_router(system_settings_router.router, prefix="/api/system-settings", tags=["system-settings"])
app.include_router(turn_usage_router.router, prefix="/api/admin/turn-usage", tags=["turn-usage"])
app.include_router(groups_router.router, prefix="/api/groups", tags=["groups"])
app.include_router(groups_router.users_router, prefix="/api/users", tags=["groups"])
app.include_router(profiles_router.router, prefix="/api/profiles", tags=["profiles"])
app.include_router(profiles_router.users_router, prefix="/api/users", tags=["profiles"])
app.include_router(service_mounts_router.router, prefix="/api/services", tags=["services"])
app.include_router(service_icons_router.router, prefix="/api/services", tags=["services"])
app.include_router(services_router.router, prefix="/api/services", tags=["services"])
app.include_router(services_auth_router.router, prefix="/api/services", tags=["services"])
app.include_router(services_auth_router.internal_router, prefix="/internal", tags=["services"])
app.include_router(instance_auth_router.internal_router, prefix="/internal/instances",
                   tags=["instances"])
app.include_router(services_auth_router.exit_router, prefix="/_styx", tags=["services"])
app.include_router(services_auth_router.pages_router, prefix="/api", tags=["services"])


@app.get("/api/health")
async def health():
    return {"status": "ok"}


_INSTANCE_UNAVAILABLE_HTML = """<!doctype html>
<meta charset="utf-8">
<title>Starting your desktop</title>
<meta http-equiv="refresh" content="3">
<p>Your desktop is starting&hellip; this page reloads automatically.
<a href="/">My desktops</a></p>
"""


_INSTANCE_STOPPED_HTML = r"""<!doctype html>
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
async def instance_unavailable(request: Request, session: AsyncSession = Depends(get_session)):
    # Traefik replacePath keeps the original path in X-Replaced-Path.
    m = re.match(r"^/i/([a-z0-9-]+)", request.headers.get("x-replaced-path", ""))
    inst = None
    if m:
        inst = (await session.exec(select(Instance).where(Instance.subdomain == m[1]))).first()
    if inst and inst.status in ("starting", "pulling", "running"):
        # X-Replaced-Path is client-settable on a direct call: reveal status only to
        # the instance's owner or an admin, everyone else sees the stopped page.
        from app.security.deps import get_current_user
        try:
            user = await get_current_user(request, session)
        except HTTPException:
            user = None
        if user and (user.role == "admin" or user.id == inst.owner_id):
            return HTMLResponse(content=_INSTANCE_UNAVAILABLE_HTML)
    return HTMLResponse(content=_INSTANCE_STOPPED_HTML)


@app.get("/api/system/runtime")
async def system_runtime(user: User = Depends(get_current_user)):
    return {"runtime": "kubernetes" if _settings.ROUTE_BACKEND == "k8s" else "docker"}


@app.get("/api/system/gpu")
async def system_gpu(user: User = Depends(get_current_user)):
    from app.services.docker_manager import detect_gpu
    return detect_gpu()


@app.get("/api/system/metrics")
async def system_metrics(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    import shutil
    from app.services.docker_manager import detect_gpu
    from app.services.k8s_runtime import instance_runtime

    docker = instance_runtime()

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
            u = await asyncio.to_thread(docker.instance_usage, inst.container_id)
            aggregate_cpu += u["cpu_percent"]
            aggregate_ram_mb += u["memory_mb"]
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
async def system_metrics_history(
    range: str = "1h",
    admin: User = Depends(require_admin),
):
    from app.services.metrics_store import get_history
    return get_history(range)


@app.get("/api/system/diagnostics")
async def system_diagnostics(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    from app.services.diagnostics import run_diagnostics
    return await run_diagnostics(session)


@app.get("/api/system/diagnostics/history")
async def system_diagnostics_history(
    range: str = "1h",
    admin: User = Depends(require_admin),
):
    from app.services.health_store import get_history
    return get_history(range)
