import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import FileResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session, async_session
from app.models import Instance, ServiceTemplate, SessionEvent, PulledImage, User
from app.schemas import InstanceCreate, InstanceUpdate, SessionConfigUpdate, InstanceStatus
from app.security.deps import get_current_user, require_owner_or_admin
from app.services.docker_manager import DockerManager
from app.services.screenshot import ScreenshotService
from app.services.traefik_labels import generate_traefik_labels
from app.services.audit import audit
from app.middleware.rate_limit import SlidingWindow

logger = logging.getLogger(__name__)

router = APIRouter()
_settings = Settings()

# Parse rate limit config and create instance creation limiter
_limit, _window = _settings.RATE_LIMIT_INSTANCE_CREATE.split("/")
_create_limiter = SlidingWindow(int(_limit), int(_window))

# Field allowlist for instance updates. Only these fields can be modified via PATCH.
_INSTANCE_UPDATE_FIELDS = {"name", "env_overrides", "session_config"}


def _dind_store_volume(instance_id: str) -> str:
    return f"selkies-{instance_id}-dockerstore"


def get_docker_manager() -> DockerManager:
    return DockerManager(network_name=_settings.DOCKER_NETWORK)


def get_screenshot_service() -> ScreenshotService:
    return ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR,
        docker_manager=get_docker_manager(),
    )


async def _refresh_routes(session: AsyncSession):
    from app.services.route_writer import refresh_routes_from_db

    await refresh_routes_from_db(session)


async def _build_and_start_container(instance, template, docker):
    """(Re)create the Docker container for an instance from its template,
    mounting the instance's existing named volumes (data preserved), then start it.
    Sets instance.container_id. Caller commits."""
    volumes = {}
    for vol, vol_name in zip(template.volumes, instance.volume_names):
        await asyncio.to_thread(docker.create_volume, vol_name)
        volumes[vol_name] = {"bind": vol["mount"], "mode": "rw"}

    if template.dind:
        store = _dind_store_volume(instance.id)
        if store not in instance.volume_names:
            instance.volume_names = [*instance.volume_names, store]
        await asyncio.to_thread(docker.create_volume, store)
        volumes[store] = {"bind": "/var/lib/docker", "mode": "rw"}

    env = {**template.env_vars, **(instance.env_overrides or {})}
    labels = generate_traefik_labels(
        instance_id=instance.id,
        subdomain=instance.subdomain,
        domain=_settings.DOMAIN,
        port=template.internal_port,
        template_name=template.name,
    )

    net = None
    if instance.owner_id:
        net = await asyncio.to_thread(docker.ensure_user_network, instance.owner_id)

    container_id = await asyncio.to_thread(
        docker.create_container,
        name=f"selkies-{instance.subdomain}",
        image=template.image,
        labels=labels,
        environment=env,
        volumes=volumes,
        port=template.internal_port,
        gpu_enabled=template.gpu_enabled,
        gpu_count=template.gpu_count,
        memory_limit=template.memory_limit,
        cpu_limit=template.cpu_limit,
        shm_size=template.shm_size,
        dind=template.dind,
        cap_add=template.cap_add,
        security_opt=template.security_opt,
        network=net,
        restart_policy=template.restart_policy,
        read_only_rootfs=template.read_only_rootfs,
        tmpfs=template.tmpfs,
        extra_hosts=template.extra_hosts,
        ulimits=template.ulimits,
        devices=template.devices,
        entrypoint=template.entrypoint,
        command=template.command,
        privileged=template.privileged,
        extra_docker_args=template.extra_docker_args,
    )
    instance.container_id = container_id
    await asyncio.to_thread(docker.start_container, container_id)
    return container_id


@router.get("", response_model=list[Instance])
async def list_instances(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    stmt = select(Instance)
    if user.role != "admin":
        stmt = stmt.where(Instance.owner_id == user.id)
    result = await session.exec(stmt)
    return result.all()


async def _launch_instance_background(instance_id: str, template_id: str):
    """Background task: pull image, create container, start it."""
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    async with async_session() as session:
        instance = await session.get(Instance, instance_id)
        template = await session.get(ServiceTemplate, template_id)
        if not instance or not template:
            return

        try:
            needs_pull = await asyncio.to_thread(docker.image_exists, template.image)
            needs_pull = not needs_pull
            instance.status = "pulling" if needs_pull else "starting"
            session.add(instance)
            await session.commit()

            if needs_pull:
                from app.services import pull_progress

                def _cb(pct, detail, _id=instance.id):
                    pull_progress.set_progress(_id, pct, detail)

                try:
                    await asyncio.to_thread(docker.pull_image_streaming, template.image, _cb)
                finally:
                    pull_progress.clear(instance.id)  # never leave stale progress

            volume_names = []
            for vol in template.volumes:
                vol_name = vol["name"].replace("{instance_id}", instance.id)
                await asyncio.to_thread(docker.create_volume, vol_name)
                volume_names.append(vol_name)
            instance.volume_names = volume_names

            volumes = {}
            for vol, vol_name in zip(template.volumes, volume_names):
                volumes[vol_name] = {"bind": vol["mount"], "mode": "rw"}

            if template.dind:
                store = _dind_store_volume(instance.id)
                if store not in instance.volume_names:
                    instance.volume_names = [*instance.volume_names, store]
                await asyncio.to_thread(docker.create_volume, store)
                volumes[store] = {"bind": "/var/lib/docker", "mode": "rw"}

            env = {**template.env_vars, **(instance.env_overrides or {})}

            labels = generate_traefik_labels(
                instance_id=instance.id,
                subdomain=instance.subdomain,
                domain=_settings.DOMAIN,
                port=template.internal_port,
                template_name=template.name,
            )

            net = None
            if instance.owner_id:
                net = await asyncio.to_thread(docker.ensure_user_network, instance.owner_id)

            container_id = await asyncio.to_thread(
                docker.create_container,
                name=f"selkies-{instance.subdomain}",
                image=template.image,
                labels=labels,
                environment=env,
                volumes=volumes,
                port=template.internal_port,
                gpu_enabled=template.gpu_enabled,
                gpu_count=template.gpu_count,
                memory_limit=template.memory_limit,
                cpu_limit=template.cpu_limit,
                shm_size=template.shm_size,
                dind=template.dind,
                cap_add=template.cap_add,
                security_opt=template.security_opt,
                network=net,
                restart_policy=template.restart_policy,
                read_only_rootfs=template.read_only_rootfs,
                tmpfs=template.tmpfs,
                extra_hosts=template.extra_hosts,
                ulimits=template.ulimits,
                devices=template.devices,
                entrypoint=template.entrypoint,
                command=template.command,
                privileged=template.privileged,
                extra_docker_args=template.extra_docker_args,
            )

            # Track pulled image
            existing_img = await session.exec(
                select(PulledImage).where(PulledImage.image == template.image)
            )
            if not existing_img.first():
                img_info = await asyncio.to_thread(docker.get_image_info, template.image)
                pulled_img = PulledImage(
                    image=template.image,
                    size_mb=img_info["size_mb"] if img_info else None,
                )
                session.add(pulled_img)

            instance.status = "starting"
            instance.container_id = container_id
            session.add(instance)
            await session.commit()

            await asyncio.to_thread(docker.start_container, container_id)

            now = datetime.now(timezone.utc)
            instance.status = "running"
            instance.started_at = now
            instance.last_activity = now
            session.add(instance)

            event = SessionEvent(instance_id=instance.id, event_type="started")
            session.add(event)
            await session.commit()
            await _refresh_routes(session)

        except Exception as e:
            logger.error(f"Instance {instance_id} launch failed: {e}")
            instance.status = "error"
            instance.error_message = str(e)
            session.add(instance)
            event = SessionEvent(
                instance_id=instance.id,
                event_type="error",
                details={"error": str(e)},
            )
            session.add(event)
            await session.commit()


@router.post("", response_model=Instance, status_code=201)
async def create_instance(
    body: InstanceCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    template = await session.get(ServiceTemplate, body.template_id)
    if not template:
        raise HTTPException(404, "Template not found")

    # Rate limit check for non-admin users
    if user.role != "admin":
        if not _create_limiter.allow(user.id):
            raise HTTPException(429, "Too many instances created recently — try again later")

        # Quota check for non-admin users
        quota = _settings.MAX_INSTANCES_PER_USER
        if quota > 0:
            owned = await session.exec(
                select(Instance).where(Instance.owner_id == user.id)
            )
            owned_count = len(owned.all())
            if owned_count >= quota:
                raise HTTPException(
                    429,
                    f"Instance limit reached ({quota}). Delete an instance first."
                )

    result = await session.exec(
        select(Instance).where(Instance.subdomain == body.subdomain)
    )
    existing = result.first()
    if existing:
        raise HTTPException(409, f"Subdomain '{body.subdomain}' already in use")

    instance = Instance(
        template_id=template.id,
        owner_id=user.id,
        name=body.name,
        subdomain=body.subdomain,
        status="starting",
        env_overrides=body.env_overrides,
        session_config=body.session_config or template.session_config,
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)

    # Audit the instance creation
    await audit(
        session,
        "instance.create",
        user_id=user.id,
        resource=instance.id,
        detail={"template": template.name, "subdomain": instance.subdomain}
    )
    await session.commit()

    asyncio.create_task(_launch_instance_background(instance.id, template.id))
    return instance


@router.get("/{instance_id}", response_model=Instance)
async def get_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    return instance


@router.post("/{instance_id}/start", response_model=Instance)
async def start_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if instance.status == "running":
        raise HTTPException(409, "Instance already running")

    container_exists = False
    if instance.container_id:
        status = await asyncio.to_thread(docker.get_container_status, instance.container_id)
        container_exists = status["status"] != "not_found"

    if container_exists:
        # Reattach Traefik to the per-user network before starting. The network
        # membership is only established on the create/build path, so a Traefik
        # restart leaves it off the net and routing 502s until reattached.
        if instance.owner_id:
            await asyncio.to_thread(docker.ensure_user_network, instance.owner_id)
        await asyncio.to_thread(docker.start_container, instance.container_id)
    else:
        template = await session.get(ServiceTemplate, instance.template_id)
        if not template:
            raise HTTPException(400, "Template no longer exists, cannot recreate")

        await _build_and_start_container(instance, template, docker)

    now = datetime.now(timezone.utc)
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    session.add(instance)

    event = SessionEvent(
        instance_id=instance.id,
        event_type="started",
        details={"recreated": not container_exists},
    )
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance


@router.post("/{instance_id}/stop", response_model=Instance)
async def stop_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    if instance.container_id:
        status = await asyncio.to_thread(docker.get_container_status, instance.container_id)
        if status["status"] not in ("not_found", "exited"):
            await asyncio.to_thread(docker.stop_container, instance.container_id)

    instance.status = "stopped"
    instance.stopped_at = datetime.now(timezone.utc)
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="stopped")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance


@router.post("/{instance_id}/restart", response_model=Instance)
async def restart_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if not instance.container_id:
        raise HTTPException(400, "No container to restart")

    # Reattach Traefik to the per-user network (see start_instance) — a Traefik
    # restart drops its membership and routing 502s until reattached.
    if instance.owner_id:
        await asyncio.to_thread(docker.ensure_user_network, instance.owner_id)
    await asyncio.to_thread(docker.restart_container, instance.container_id)

    now = datetime.now(timezone.utc)
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    instance.error_message = None
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="restarted")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.post("/{instance_id}/recreate", response_model=Instance)
async def recreate_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    """Rebuild the instance's container from its (updated) template, reusing the
    instance's named volumes so persistent data is preserved. Same instance id/subdomain."""
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    template = await session.get(ServiceTemplate, instance.template_id)
    if not template:
        raise HTTPException(400, "Template no longer exists, cannot recreate")

    # Remove the old container, keep volumes.
    if instance.container_id:
        status = await asyncio.to_thread(docker.get_container_status, instance.container_id)
        if status["status"] != "not_found":
            if status["status"] not in ("exited",):
                await asyncio.to_thread(docker.stop_container, instance.container_id)
            await asyncio.to_thread(docker.remove_container, instance.container_id)

    # Recompute volume names from the (possibly updated) template. instance.id is stable,
    # so unchanged volume defs yield identical names -> create_volume returns the existing
    # volume -> data preserved. New defs create new volumes; removed defs are left orphaned.
    instance.volume_names = [
        vol["name"].replace("{instance_id}", instance.id) for vol in template.volumes
    ]

    await _build_and_start_container(instance, template, docker)

    now = datetime.now(timezone.utc)
    instance.status = "running"
    instance.started_at = now
    instance.last_activity = now
    instance.error_message = None
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="recreated")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance


@router.post("/{instance_id}/pause", response_model=Instance)
async def pause_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if instance.status != "running" and instance.status != "idle":
        raise HTTPException(409, "Instance not running")

    await asyncio.to_thread(docker.pause_container, instance.container_id)
    instance.status = "paused"
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="paused")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance


@router.post("/{instance_id}/unpause", response_model=Instance)
async def unpause_instance(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if instance.status != "paused":
        raise HTTPException(409, "Instance not paused")

    await asyncio.to_thread(docker.unpause_container, instance.container_id)
    instance.status = "running"
    instance.last_activity = datetime.now(timezone.utc)
    session.add(instance)

    event = SessionEvent(instance_id=instance.id, event_type="unpaused")
    session.add(event)
    await session.commit()
    await session.refresh(instance)
    await _refresh_routes(session)
    return instance


@router.delete("/{instance_id}", status_code=204)
async def delete_instance(
    instance_id: str,
    remove_volumes: bool = Query(False),
    remove_image: bool = Query(False),
    remove_template: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    # Capture subdomain before deletion for audit
    subdomain = instance.subdomain
    owner_id = instance.owner_id

    if instance.container_id:
        status = await asyncio.to_thread(docker.get_container_status, instance.container_id)
        if status["status"] != "not_found":
            await asyncio.to_thread(docker.remove_container, instance.container_id)

    if remove_volumes:
        for vol_name in instance.volume_names:
            await asyncio.to_thread(docker.remove_volume, vol_name)

    # Capture template/image before deleting the instance row.
    template = await session.get(ServiceTemplate, instance.template_id)
    image_tag = template.image if template else None
    template_id = instance.template_id

    event = SessionEvent(instance_id=instance.id, event_type="destroyed")
    session.add(event)
    await session.delete(instance)
    await session.commit()

    # Audit the instance deletion
    await audit(
        session,
        "instance.delete",
        user_id=user.id,
        resource=instance_id,
        detail={"subdomain": subdomain}
    )
    await session.commit()

    # Opt-in image prune — only when requested AND no other instance uses the image.
    if remove_image and image_tag:
        remaining = await session.exec(
            select(Instance).join(
                ServiceTemplate, Instance.template_id == ServiceTemplate.id
            ).where(ServiceTemplate.image == image_tag)
        )
        if not remaining.first():
            pulled_result = await session.exec(
                select(PulledImage).where(PulledImage.image == image_tag)
            )
            pulled = pulled_result.first()
            if pulled:
                try:
                    await asyncio.to_thread(docker.remove_image, image_tag)
                except Exception:
                    pass
                await session.delete(pulled)
                await session.commit()

    # Opt-in template delete — only when requested AND no other instance uses it.
    if remove_template and template is not None:
        remaining_t = await session.exec(
            select(Instance).where(Instance.template_id == template_id)
        )
        if not remaining_t.first():
            await session.delete(template)
            await session.commit()

    # Clean up per-user network if this was the last instance for the user
    if owner_id:
        remaining_user_instances = await session.exec(
            select(Instance).where(Instance.owner_id == owner_id)
        )
        if not remaining_user_instances.first():
            await asyncio.to_thread(docker.remove_user_network, owner_id)

    await _refresh_routes(session)
    return Response(status_code=204)


@router.get("/{instance_id}/status", response_model=InstanceStatus)
async def get_instance_status(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    docker_status = {}
    if instance.container_id:
        docker_status = await asyncio.to_thread(docker.get_container_status, instance.container_id)

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

    from app.services import pull_progress
    pp = pull_progress.get(instance_id)

    return InstanceStatus(
        id=instance.id,
        status=docker_status.get("status", instance.status),
        container_id=instance.container_id,
        uptime_seconds=uptime,
        idle_seconds=idle,
        session_config=instance.session_config,
        pull_percent=pp["percent"] if pp else None,
        pull_detail=pp["detail"] if pp else None,
    )


@router.get("/{instance_id}/stats")
async def get_instance_stats(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if not instance.container_id or instance.status not in ("running", "idle"):
        return {"cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0}

    raw = await asyncio.to_thread(docker.get_container_stats, instance.container_id)
    if not raw:
        return {"cpu_percent": 0, "memory_mb": 0, "memory_limit_mb": 0, "memory_percent": 0}

    cpu_delta = raw.get("cpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0) - \
                raw.get("precpu_stats", {}).get("cpu_usage", {}).get("total_usage", 0)
    system_delta = raw.get("cpu_stats", {}).get("system_cpu_usage", 0) - \
                   raw.get("precpu_stats", {}).get("system_cpu_usage", 0)
    num_cpus = raw.get("cpu_stats", {}).get("online_cpus", 1)
    cpu_percent = (cpu_delta / system_delta * num_cpus * 100) if system_delta > 0 else 0

    mem_usage = raw.get("memory_stats", {}).get("usage", 0)
    mem_limit = raw.get("memory_stats", {}).get("limit", 1)
    memory_mb = mem_usage / (1024 * 1024)
    memory_limit_mb = mem_limit / (1024 * 1024)
    memory_percent = (mem_usage / mem_limit * 100) if mem_limit > 0 else 0

    return {
        "cpu_percent": round(cpu_percent, 1),
        "memory_mb": round(memory_mb),
        "memory_limit_mb": round(memory_limit_mb),
        "memory_percent": round(memory_percent, 1),
    }


@router.post("/{instance_id}/keepalive", response_model=Instance)
async def keepalive(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    instance.last_activity = datetime.now(timezone.utc)
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.patch("/{instance_id}", response_model=Instance)
async def update_instance(
    instance_id: str,
    body: InstanceUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    # Apply only allowlisted fields
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in _INSTANCE_UPDATE_FIELDS:
            setattr(instance, field, value)

    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    return instance


@router.patch("/{instance_id}/session", response_model=Instance)
async def update_session_config(
    instance_id: str,
    body: SessionConfigUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

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
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    path = screenshots.get_path(instance_id)
    if not path:
        raise HTTPException(404, "No screenshot available")

    return FileResponse(path, media_type="image/png")


@router.post("/{instance_id}/screenshot/refresh")
async def refresh_screenshot(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    screenshots: ScreenshotService = Depends(get_screenshot_service),
    user: User = Depends(get_current_user),
):
    """Capture a fresh screenshot on demand (via the Selkies #shared view-only
    mirror — never steals the session). Returns {"ok": bool}."""
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if instance.status not in ("running", "idle") or not instance.container_id:
        return {"ok": False, "reason": "not running"}

    tmpl = await session.get(ServiceTemplate, instance.template_id)
    port = tmpl.internal_port if tmpl else 3001
    protocol = tmpl.internal_protocol if tmpl else "https"
    try:
        ok = await screenshots.capture(instance.id, instance.container_id, port, protocol)
    finally:
        await screenshots.close()
    return {"ok": ok}


@router.get("/{instance_id}/events")
async def get_instance_events(
    instance_id: str,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)

    from sqlmodel import desc
    result = await session.exec(
        select(SessionEvent)
        .where(SessionEvent.instance_id == instance_id)
        .order_by(desc(SessionEvent.id))
        .limit(20)
    )
    events = result.all()
    return [
        {
            "type": ev.event_type,
            "time": "recent",
            "details": ev.details.get("error", "")[:200] if ev.details else None,
        }
        for ev in events
    ]


@router.get("/{instance_id}/logs")
async def get_instance_logs(
    instance_id: str,
    lines: int = Query(default=500, le=2000),
    session: AsyncSession = Depends(get_session),
    docker: DockerManager = Depends(get_docker_manager),
    user: User = Depends(get_current_user),
):
    instance = await session.get(Instance, instance_id)
    if not instance:
        raise HTTPException(404, "Instance not found")
    require_owner_or_admin(instance.owner_id, user)
    if not instance.container_id:
        return []

    try:
        container = docker._client.containers.get(instance.container_id)
        raw_logs = await asyncio.to_thread(
            container.logs, tail=lines, timestamps=True
        )
        text = raw_logs.decode("utf-8", errors="replace")
        return text.strip().split("\n") if text.strip() else []
    except Exception:
        return []
