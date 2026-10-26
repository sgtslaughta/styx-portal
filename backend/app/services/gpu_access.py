"""Who may use a GPU, and the launch-time GPU-or-CPU decision."""
import asyncio

from sqlmodel import select

from app.models import Group, User, UserGroup

NO_GPU_NOTICE = "No GPU free, running on CPU"


async def user_may_use_gpu(session, user) -> bool:
    if user.role == "admin":
        return True
    r = await session.exec(
        select(Group.id).join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user.id, Group.allow_gpu == True))  # noqa: E712
    return r.first() is not None


async def resolve_gpu(session, runtime, template, instance) -> bool:
    """GPU on/off for this launch; sets instance.notice when falling back to CPU.
    Re-checks template support and the owner's permission on every (re)start, so
    revoking a group's allow_gpu or a template's GPU takes effect on next start."""
    owner = await session.get(User, instance.owner_id) if instance.owner_id else None
    want = (template.gpu_enabled and instance.gpu is not False
            and owner is not None and await user_may_use_gpu(session, owner))
    if want and not await asyncio.to_thread(runtime.gpu_free, template.gpu_count):
        instance.notice = NO_GPU_NOTICE
        return False
    instance.notice = None
    return want
