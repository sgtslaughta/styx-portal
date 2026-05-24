import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session, select

from app.config import Settings
from app.database import init_db, engine
from app.models import Instance as InstanceModel
from app.routers import templates, instances, registry
from app.services.docker_manager import DockerManager
from app.services.screenshot import ScreenshotService
from app.services.session_monitor import SessionMonitor

_settings = Settings()


async def _session_monitor_loop():
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    monitor = SessionMonitor(docker)
    screenshots = ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR, docker_manager=docker
    )
    tick = 0
    while True:
        await asyncio.sleep(10)
        tick += 1
        try:
            with Session(engine) as session:
                if tick % 6 == 0:
                    monitor.check_all(session)
                if tick % 3 == 0:
                    running = session.exec(
                        select(InstanceModel).where(
                            InstanceModel.status.in_(["running", "idle"])
                        )
                    ).all()
                    for inst in running:
                        if inst.container_id:
                            screenshots.capture(inst.id, inst.container_id, 3001)
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(_session_monitor_loop())
    yield
    task.cancel()


app = FastAPI(title="Selkies Hub", version="0.1.0", lifespan=lifespan)
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(instances.router, prefix="/api/instances", tags=["instances"])
app.include_router(registry.router, prefix="/api/registry/images", tags=["registry"])


@app.get("/api/health")
def health():
    return {"status": "ok"}
