# backend/app/routers/groups.py
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import Group, User, UserGroup
from app.schemas import GroupCreate, GroupOut, UserGroupsUpdate
from app.security.deps import require_admin
from app.services.audit import audit_request

router = APIRouter()
users_router = APIRouter()


async def user_group_names(session: AsyncSession, user_id: str) -> list[str]:
    result = await session.exec(
        select(Group.name).join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user_id))
    return sorted(result.all())


@router.get("", response_model=list[GroupOut])
async def list_groups(admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    counts = dict((await session.exec(
        select(UserGroup.group_id, func.count()).group_by(UserGroup.group_id))).all())
    groups = (await session.exec(select(Group).order_by(Group.name))).all()
    return [GroupOut(id=g.id, name=g.name, description=g.description,
                     member_count=counts.get(g.id, 0)) for g in groups]


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(body: GroupCreate, request: Request,
                       admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    if (await session.exec(select(Group).where(Group.name == body.name))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Group exists")
    g = Group(name=body.name, description=body.description)
    session.add(g)
    await audit_request(session, request, "group.create", user_id=admin.id,
                        resource=g.id, detail={"name": g.name})
    await session.commit()
    return GroupOut(id=g.id, name=g.name, description=g.description)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: str, request: Request,
                       admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    g = await session.get(Group, group_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    await session.exec(delete(UserGroup).where(UserGroup.group_id == group_id))
    await session.delete(g)
    await audit_request(session, request, "group.delete", user_id=admin.id,
                        resource=group_id, detail={"name": g.name})
    await session.commit()
    return Response(status_code=204)


@users_router.get("/{user_id}/groups", response_model=list[str])
async def get_user_groups(user_id: str, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(UserGroup.group_id).where(UserGroup.user_id == user_id))
    return sorted(result.all())


@users_router.put("/{user_id}/groups", response_model=list[str])
async def set_user_groups(user_id: str, body: UserGroupsUpdate, request: Request,
                          admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    if await session.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    existing = set((await session.exec(select(Group.id).where(Group.id.in_(body.group_ids)))).all())
    if existing != set(body.group_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown group id")
    await session.exec(delete(UserGroup).where(UserGroup.user_id == user_id))
    for gid in existing:
        session.add(UserGroup(user_id=user_id, group_id=gid))
    await audit_request(session, request, "user.groups_set", user_id=admin.id,
                        resource=user_id, detail={"group_ids": sorted(existing)})
    await session.commit()
    return sorted(existing)
