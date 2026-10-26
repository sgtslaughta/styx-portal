"""Persistent per-user profile volumes (one per user + template)."""
import asyncio
import hashlib
import logging

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import Instance, ServiceTemplate, UserProfile
from app.services.template_validation import resolve_volume_name, validate_volumes

logger = logging.getLogger(__name__)

ACTIVE = ("running", "starting", "pulling")


def profile_volume_name(user_id: str, template_id: str) -> str:
    # immutable ids: a re-created template with the same name must not inherit an old profile
    return "profile-" + hashlib.sha256(f"{user_id}:{template_id}".encode()).hexdigest()[:40]


async def ensure_profile(session: AsyncSession, user_id: str, template) -> str:
    vol = profile_volume_name(user_id, template.id)
    row = await session.get(UserProfile, (user_id, template.id))
    if row is None:
        session.add(UserProfile(user_id=user_id, template_id=template.id, volume_name=vol))
        await session.commit()
    return vol


async def profile_in_use(session: AsyncSession, volume: str,
                         exclude_instance_id: str | None = None) -> Instance | None:
    stmt = select(Instance).where(Instance.profile_volume == volume,
                                  Instance.status.in_(ACTIVE))
    if exclude_instance_id:
        stmt = stmt.where(Instance.id != exclude_instance_id)
    return (await session.exec(stmt)).first()


async def delete_profile(session: AsyncSession, runtime, user_id: str, template_id: str) -> None:
    row = await session.get(UserProfile, (user_id, template_id))
    if row is None:
        raise HTTPException(404, "Profile not found")
    other = await profile_in_use(session, row.volume_name)
    if other:
        raise HTTPException(409, f"Profile is in use by {other.name}")
    try:
        await asyncio.to_thread(runtime.remove_volume, row.volume_name)
    except Exception:  # noqa: BLE001  volume may already be gone
        logger.warning("profile volume %s not removed", row.volume_name, exc_info=True)
    await session.delete(row)
    await session.commit()


def mounts_for(template, instance) -> list[tuple[str, str]]:
    """[(volume_name, mount)]: template volumes, profile volume replacing the one at profile_mount."""
    prof = instance.profile_volume if template.profile_mount else None
    out = []
    for vol in template.volumes:
        if prof and vol["mount"] == template.profile_mount:
            continue
        out.append((resolve_volume_name(vol["name"], instance.id), vol["mount"]))
    if prof:
        out.append((prof, template.profile_mount))
    return out


async def _ensure_free(session, volume, template, exclude_instance_id=None) -> None:
    other = await profile_in_use(session, volume, exclude_instance_id)
    if other:
        raise HTTPException(409, f"Your {template.display_name} profile is in use by {other.name}")


async def claim_profile(session, user_id: str, template) -> str:
    """Profile volume for a new instance; 422 if the template has none, 409 if in use."""
    if not template.profile_mount:
        raise HTTPException(422, "Template does not offer persistent profiles")
    vol = await ensure_profile(session, user_id, template)
    await _ensure_free(session, vol, template)
    return vol


async def check_instance_profile(session, instance) -> None:
    """409 if this instance's profile is held by another active instance (start/recreate)."""
    if instance.profile_volume:
        template = await session.get(ServiceTemplate, instance.template_id)
        await _ensure_free(session, instance.profile_volume, template, instance.id)


async def prepare_volumes(docker, template, instance) -> dict:
    """Create the instance's volumes; set instance.volume_names (never the profile).
    Returns the {volume: {bind, mode}} map for create_container."""
    validate_volumes(template.volumes)
    volumes, names = {}, []
    for name, mount in mounts_for(template, instance):
        if name == instance.profile_volume:
            await asyncio.to_thread(docker.create_volume, name, Settings().PROFILE_VOLUME_SIZE)
        else:
            await asyncio.to_thread(docker.create_volume, name)
            names.append(name)
        volumes[name] = {"bind": mount, "mode": "rw"}
    instance.volume_names = names
    return volumes
