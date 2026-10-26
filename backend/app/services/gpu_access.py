"""Who may use a GPU, and the launch-time GPU-or-CPU decision."""
import asyncio

from sqlmodel import select

from app.models import Group, UserGroup

NO_GPU_NOTICE = "No GPU free, running on CPU"


async def user_may_use_gpu(session, user) -> bool:
    if user.role == "admin":
        return True
    r = await session.exec(
        select(Group.id).join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user.id, Group.allow_gpu == True))  # noqa: E712
    return r.first() is not None


async def resolve_gpu(runtime, template, instance) -> bool:
    """GPU on/off for this launch; sets instance.notice when falling back to CPU."""
    want = instance.gpu if instance.gpu is not None else template.gpu_enabled
    if want and not await asyncio.to_thread(runtime.gpu_free, template.gpu_count):
        instance.notice = NO_GPU_NOTICE
        return False
    instance.notice = None
    return want
