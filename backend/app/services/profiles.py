"""Persistent per-user profile volumes (one per user + template)."""
import asyncio
import logging

from fastapi import HTTPException
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Instance, UserProfile
from app.services.k8s_routes import k8s_name
from app.services.template_validation import resolve_volume_name

logger = logging.getLogger(__name__)

ACTIVE = ("running", "starting", "pulling")


def profile_volume_name(user_id: str, template_name: str) -> str:
    return k8s_name(f"profile-{user_id}-{template_name}")


async def ensure_profile(session: AsyncSession, user_id: str, template) -> str:
    vol = profile_volume_name(user_id, template.name)
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
    prof = instance.profile_volume
    out = []
    for vol in template.volumes:
        if prof and vol["mount"] == template.profile_mount:
            continue
        out.append((resolve_volume_name(vol["name"], instance.id), vol["mount"]))
    if prof:
        out.append((prof, template.profile_mount))
    return out
