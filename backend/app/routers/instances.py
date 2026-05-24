from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Instance, ServiceTemplate, SessionEvent
from app.schemas import InstanceCreate, SessionConfigUpdate, InstanceStatus
from app.services.docker_manager import DockerManager
from app.services.screenshot import ScreenshotService
from app.services.traefik_labels import generate_traefik_labels

router = APIRouter()
_settings = Settings()


def get_docker_manager() -> DockerManager:
    return DockerManager(network_name=_settings.DOCKER_NETWORK)


def get_screenshot_service() -> ScreenshotService:
    return ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR,
        docker_manager=get_docker_manager(),
    )


@router.get("", response_model=list[Instance])
async def list_instances(session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Instance))
    return result.all()


@router.post("", response_model=Instance, status_code=201)
async def create_instance(
    body: InstanceCreate,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    template = await session.get(ServiceTemplate, body.template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    result = await session.exec(
        select(Instance).where(Instance.subdomain == body.subdomain)
    )
    existing = result.first()
    if existing:
        raise HTTPException(409, f"Subdomain '{body.subdomain}' already in use")

    instance = Instance(
        template_id=template.id,
        name=body.name,
        subdomain=body.subdomain,
        status="creating",
        env_overrides=body.env_overrides,
        session_config=body.session_config or template.session_config,
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)

    volume_names = []
    for vol in template.volumes:
        vol_name = vol["name"].replace("{instance_id}", instance.id)
        docker.create_volume(vol_name)
        volume_names.append(vol_name)
    instance.volume_names = volume_names

    volumes = {}
    for vol, vol_name in zip(template.volumes, volume_names):
        volumes[vol_name] = {"bind": vol["mount"], "mode": "rw"}

    env = {**template.env_vars, **body.env_overrides}

    labels = generate_traefik_labels(
        instance_id=instance.id,
        subdomain=body.subdomain,
        domain=_settings.DOMAIN,
        port=template.internal_port,
        template_name=template.name,
    )

    container_id = docker.create_container(
        name=f"selkies-{body.subdomain}",
        image=template.image,
        labels=labels,
        environment=env,
        volumes=volumes,
        port=template.internal_port,
        gpu_enabled=template.gpu_enabled,
        gpu_count=template.gpu_count,
        memory_limit=template.memory_limit,
        shm_size=template.shm_size,
    )

    docker.start_container(container_id)

    now = datetime.now(timezone.utc)
    instance.container_id = container_id
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="started")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.get("/{instance_id}", response_model=Instance)
async def get_instance(instance_id: str, session: AsyncSession = Depends(get_session)):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    return instance


@router.post("/{instance_id}/start", response_model=Instance)
async def start_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    if instance.status == "running":
        raise HTTPException(409, "Instance already running")

    docker.start_container(instance.container_id)

    now = datetime.now(timezone.utc)
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="started")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.post("/{instance_id}/stop", response_model=Instance)
async def stop_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    docker.stop_container(instance.container_id)

    instance.status = "stopped"
    instance.stopped_at = datetime.now(timezone.utc)
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="stopped")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(
    instance_id: str,
    remove_volumes: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    if instance.container_id:
        docker.remove_container(instance.container_id)

    if remove_volumes:
        for vol_name in instance.volume_names:
            docker.remove_volume(vol_name)

    event = SessionEvent(instance_id=instance.id, event_type="destroyed")
    session.add(event)
    await session.delete(instance)
    await session.commit()
    return Response(status_code=204)


@router.get("/{instance_id}/status", response_model=InstanceStatus)
async def get_instance_status(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    docker_status = {}
    if instance.container_id:
        docker_status = docker.get_container_status(instance.container_id)

    now = datetime.now(timezone.utc)
    uptime = None
    if instance.started_at and instance.status == "running":
        started = instance.started_at
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        uptime = (now - started).total_seconds()

    idle = None
    if instance.last_activity and instance.status == "running":
        last_act = instance.last_activity
        if last_act.tzinfo is None:
            last_act = last_act.replace(tzinfo=timezone.utc)
        idle = (now - last_act).total_seconds()

    return InstanceStatus(
        id=instance.id,
        status=docker_status.get("status", instance.status),
        container_id=instance.container_id,
        uptime_seconds=uptime,
        idle_seconds=idle,
        session_config=instance.session_config,
    )


@router.post("/{instance_id}/keepalive", response_model=Instance)
async def keepalive(instance_id: str, session: AsyncSession = Depends(get_session)):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    instance.last_activity = datetime.now(timezone.utc)
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.patch("/{instance_id}/session", response_model=Instance)
async def update_session_config(
    instance_id: str,
    body: SessionConfigUpdate,
    session: AsyncSession = Depends(get_session),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    config = instance.session_config or {}
    for field, value in body.model_dump(exclude_unset=True).items():
        config[field] = value
    instance.session_config = config

    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.get("/{instance_id}/screenshot")
async def get_screenshot(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    screenshots: ScreenshotService = Depends(get_screenshot_service),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")

    path = screenshots.get_path(instance_id)
    if not path:
        raise HTTPException(404, "No screenshot available")

    return FileResponse(path, media_type="image/png")
