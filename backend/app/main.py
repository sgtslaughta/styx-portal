import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import select

from app.config import Settings
from app.database import init_db, async_session
from app.models import Instance as InstanceModel
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
                    select(InstanceModel).where(
                        InstanceModel.status.in_(["running", "idle"])
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
            select(InstanceModel).where(
                InstanceModel.status.in_(["running", "idle", "paused", "pulling", "starting"])
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
            select(InstanceModel).where(InstanceModel.status.in_(["running", "idle"]))
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
    yield
    task.cancel()


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
