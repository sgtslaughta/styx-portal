"""Admin CRUD for proxied services (spec §6, §8)."""
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from docker.errors import DockerException
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Group, ProxiedService, ServicePreset, User
from app.routers.services_auth import user_may_open
from app.schemas import (DiscoveredContainer, ProxiedServiceCreate, ProxiedServiceOut,
                         ProxiedServiceUpdate, ServicePresetOut, ServiceTileOut)
from app.security.deps import get_current_user, require_admin
from app.services import service_favicon, ws_icon
from app.services.audit import audit_request
from app.services.docker_manager import DockerManager

router = APIRouter()
_settings = Settings()
log = logging.getLogger(__name__)


def get_docker_manager() -> DockerManager:
    return DockerManager(network_name=_settings.DOCKER_NETWORK)


def get_thumb_dir() -> Path:
    return Path(_settings.SCREENSHOT_CACHE_DIR)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _needs_setup(s: ProxiedService, presets: dict[str, ServicePreset]) -> bool:
    """Docker app Styx can configure (config_file method) whose base path isn't confirmed yet."""
    p = presets.get(s.preset_id) if s.preset_id else None
    return (s.kind == "docker-local" and s.mount_mode == "path" and not s.mount_managed
            and p is not None
            and any(m.get("type") == "config_file" for m in (p.subpath or {}).get("methods", [])))


async def _preset_map(session: AsyncSession) -> dict[str, ServicePreset]:
    return {p.id: p for p in (await session.exec(select(ServicePreset))).all()}


def _out(s: ProxiedService, presets: dict[str, ServicePreset]) -> ProxiedServiceOut:
    return ProxiedServiceOut(
        id=s.id, slug=s.slug, name=s.name, kind=s.kind,
        icon_kind=ws_icon.icon_kind(s.icon), icon_etag=ws_icon.icon_etag(s.icon, s.name, s.id),
        upstream_url=s.upstream_url, container=s.container, container_port=s.container_port,
        upstream_fallback=s.upstream_fallback, mount_mode=s.mount_mode, auth_mode=s.auth_mode,
        bypass_rules=s.bypass_rules, allowed_groups=s.allowed_groups, verify_tls=s.verify_tls,
        upstream_is_proxy=s.upstream_is_proxy,
        health_path=s.health_path, health_status=s.health_status,
        health_checked_at=_iso(s.health_checked_at), preset_id=s.preset_id, enabled=s.enabled,
        mount_managed=s.mount_managed, needs_setup=_needs_setup(s, presets),
        pass_identity=s.pass_identity, frame_ok=s.frame_ok,
        created_at=_iso(s.created_at) or "", updated_at=_iso(s.updated_at) or "")


async def _refresh(session: AsyncSession) -> None:
    """Rewrite Traefik routes; a failed write is an error the admin must see.

    The DB change is already committed, but Traefik keeps the old routes (e.g.
    a disabled app-native service stays reachable), so never swallow it.
    """
    from app.services import route_writer
    try:
        await route_writer.refresh_routes_from_db(session, strict=True)
    except OSError as e:
        log.error("service change saved but Traefik routes not written: %s", e)
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Saved, but Traefik routes could not be written, so routing still uses the "
            "previous configuration. Make the traefik-dynamic volume writable by the "
            "backend (chown 1000:1000) and retry.") from e


async def _get_or_404(session: AsyncSession, sid: str) -> ProxiedService:
    s = await session.get(ProxiedService, sid)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    return s


async def _attach_docker(s: ProxiedService, docker: DockerManager) -> None:
    """docker-local: join the styx network; fall back to host.docker.internal.

    Only containers the docker manager itself lists (running, non-Styx) may be attached:
    the name from the request is never passed to docker without that lookup.
    """
    if s.kind != "docker-local":
        s.upstream_fallback = None
        return
    known = {c["name"] for c in await asyncio.to_thread(docker.list_containers)}
    if s.container not in known:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Container not found among discoverable containers")
    net = _settings.SERVICES_NETWORK
    try:
        await asyncio.to_thread(docker.ensure_traefik_network, net)
        ok = await asyncio.to_thread(docker.connect_to_network, s.container, net)
    except DockerException:
        log.warning("cannot attach %s to %s", s.container, net, exc_info=True)
        ok = False
    # ponytail: fallback assumes the host published the same port number;
    # SP4 (deploy-from-template) owns ports and removes the guess.
    s.upstream_fallback = None if ok else f"http://host.docker.internal:{s.container_port}"


async def _check_groups(session: AsyncSession, names: list[str]) -> None:
    known = set((await session.exec(select(Group.name).where(Group.name.in_(names)))).all())
    missing = sorted(set(names) - known)
    if missing:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Unknown group(s): {', '.join(missing)}")


async def _release_container(session: AsyncSession, docker: DockerManager,
                             container: str, exclude_id: str) -> None:
    """Leave the services network unless another service row still uses the container."""
    other = (await session.exec(select(ProxiedService.id).where(
        ProxiedService.kind == "docker-local", ProxiedService.container == container,
        ProxiedService.id != exclude_id))).first()
    if other is None:
        await asyncio.to_thread(docker.disconnect_from_network, container,
                                _settings.SERVICES_NETWORK)


@router.get("/presets", response_model=list[ServicePresetOut])
async def list_presets(user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    return (await session.exec(select(ServicePreset).order_by(ServicePreset.name))).all()


@router.get("/discover", response_model=list[DiscoveredContainer])
async def discover(admin: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session),
                   docker: DockerManager = Depends(get_docker_manager)):
    preset_ids = [p.id for p in (await session.exec(select(ServicePreset))).all()]
    out = []
    for c in await asyncio.to_thread(docker.list_containers):
        hay = f"{c['name']} {c['image']}".lower()
        match = next((p for p in preset_ids if p in hay), None)
        out.append(DiscoveredContainer(**c, suggested_preset=match))
    return out


def _tile(s: ProxiedService, presets: dict[str, ServicePreset]) -> ServiceTileOut:
    up = {"healthy": True, "unhealthy": False}.get(s.health_status)
    return ServiceTileOut(id=s.id, slug=s.slug, name=s.name,
                          icon_kind=ws_icon.icon_kind(s.icon),
                          icon_etag=ws_icon.icon_etag(s.icon, s.name, s.id),
                          mount_mode=s.mount_mode, enabled=s.enabled, up=up, frame_ok=s.frame_ok,
                          needs_setup=_needs_setup(s, presets))


@router.get("", response_model=list[ProxiedServiceOut] | list[ServiceTileOut])
async def list_services(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    """Admins get the full model; members get tiles for services they may open."""
    rows = (await session.exec(select(ProxiedService).order_by(ProxiedService.name))).all()
    presets = await _preset_map(session)
    if user.role == "admin":
        return [_out(s, presets) for s in rows]
    # a tile for an unconfigured app would only 404, so members don't get one
    return [_tile(s, presets) for s in rows if s.enabled and not _needs_setup(s, presets)
            and await user_may_open(session, user, s)]


@router.get("/{sid}/thumbnail")
async def service_thumbnail(sid: str, user: User = Depends(get_current_user),
                            session: AsyncSession = Depends(get_session),
                            thumb_dir: Path = Depends(get_thumb_dir)):
    """Same visibility as list_services: admins see all, members only enabled services they may open."""
    s = await session.get(ProxiedService, sid)
    if s is None or (user.role != "admin" and not (s.enabled and await user_may_open(session, user, s))):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")
    path = thumb_dir / f"svc-{s.id}.png"
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No thumbnail")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "private, no-cache"})


@router.post("", response_model=ProxiedServiceOut, status_code=201)
async def create_service(body: ProxiedServiceCreate, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager)):
    if (await session.exec(select(ProxiedService).where(ProxiedService.slug == body.slug))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use")
    await _check_groups(session, body.allowed_groups)
    try:
        icon = service_favicon.normalise_icon(body.icon)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
    s = ProxiedService(**body.model_dump(exclude={"bypass_rules", "icon"}), icon=icon,
                       bypass_rules=[r.model_dump() for r in body.bypass_rules])
    # a preset emoji is only a placeholder until the app's own icon is fetched; an image is a choice
    s.icon_custom = ws_icon.icon_kind(icon) == "image"
    await _attach_docker(s, docker)
    session.add(s)
    await audit_request(session, request, "service.create", user_id=admin.id,
                        resource=s.id, detail={"slug": s.slug, "auth_mode": s.auth_mode,
                                               "mount_mode": s.mount_mode})
    await session.commit()
    await session.refresh(s)
    await _refresh(session)
    if not s.icon_custom:
        service_favicon.schedule_favicon(s.id, docker)
    return _out(s, await _preset_map(session))


@router.put("/{sid}", response_model=ProxiedServiceOut)
async def update_service(sid: str, body: ProxiedServiceUpdate, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager)):
    s = await _get_or_404(session, sid)
    await _check_groups(session, body.allowed_groups)
    prev = s.container if s.kind == "docker-local" and not s.upstream_fallback else None
    if body.icon is not None:     # omitted = keep; icons otherwise change via PUT /{id}/icon
        try:
            s.icon = service_favicon.normalise_icon(body.icon)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e))
        s.icon_custom = True
    for k, v in body.model_dump(exclude={"bypass_rules", "icon"}).items():
        setattr(s, k, v)
    s.bypass_rules = [r.model_dump() for r in body.bypass_rules]
    s.updated_at = datetime.now(timezone.utc)
    await _attach_docker(s, docker)
    session.add(s)
    await audit_request(session, request, "service.update", user_id=admin.id,
                        resource=s.id, detail={"slug": s.slug, "auth_mode": s.auth_mode,
                                               "mount_mode": s.mount_mode})
    await session.commit()
    await session.refresh(s)
    if prev and (s.kind != "docker-local" or s.container != prev):
        await _release_container(session, docker, prev, s.id)
    await _refresh(session)
    return _out(s, await _preset_map(session))


async def _set_enabled(sid, enabled, request, admin, session):
    s = await _get_or_404(session, sid)
    s.enabled = enabled
    s.updated_at = datetime.now(timezone.utc)
    session.add(s)
    await audit_request(session, request, "service.enable" if enabled else "service.disable",
                        user_id=admin.id, resource=s.id, detail={"slug": s.slug})
    await session.commit()
    await session.refresh(s)
    await _refresh(session)
    return _out(s, await _preset_map(session))


@router.post("/{sid}/enable", response_model=ProxiedServiceOut)
async def enable_service(sid: str, request: Request, admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    return await _set_enabled(sid, True, request, admin, session)


@router.post("/{sid}/disable", response_model=ProxiedServiceOut)
async def disable_service(sid: str, request: Request, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    return await _set_enabled(sid, False, request, admin, session)


@router.delete("/{sid}", status_code=204)
async def delete_service(sid: str, request: Request, admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager),
                         thumb_dir: Path = Depends(get_thumb_dir)):
    s = await _get_or_404(session, sid)
    (thumb_dir / f"svc-{s.id}.png").unlink(missing_ok=True)
    if s.kind == "docker-local" and not s.upstream_fallback:
        await _release_container(session, docker, s.container, s.id)
    slug = s.slug
    await session.delete(s)
    await audit_request(session, request, "service.delete", user_id=admin.id,
                        resource=sid, detail={"slug": slug})
    await session.commit()
    await _refresh(session)
    return Response(status_code=204)
