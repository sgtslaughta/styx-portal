from fastapi import APIRouter, Depends, Request, Response
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ServiceTemplate, User, UserProfile
from app.routers.instances import get_docker_manager
from app.security.deps import get_current_user, require_admin
from app.services import profiles
from app.services.audit import audit_request

router = APIRouter()
users_router = APIRouter()


async def _list(session: AsyncSession, user_id: str) -> list[dict]:
    rows = (await session.exec(
        select(UserProfile, ServiceTemplate)
        .join(ServiceTemplate, ServiceTemplate.id == UserProfile.template_id)
        .where(UserProfile.user_id == user_id))).all()
    return [{"template_id": t.id, "template_name": t.name, "display_name": t.display_name,
             "volume_name": p.volume_name,
             "in_use": await profiles.profile_in_use(session, p.volume_name) is not None}
            for p, t in rows]


async def _delete(session, docker, request, actor: User, user_id: str, template_id: str):
    await profiles.delete_profile(session, docker, user_id, template_id)
    await audit_request(session, request, "profile.delete", user_id=actor.id,
                        resource=template_id, detail={"profile_owner": user_id})
    await session.commit()
    return Response(status_code=204)


@router.get("")
async def my_profiles(session: AsyncSession = Depends(get_session),
                      user: User = Depends(get_current_user)):
    return await _list(session, user.id)


@router.delete("/{template_id}", status_code=204)
async def reset_my_profile(template_id: str, request: Request,
                           session: AsyncSession = Depends(get_session),
                           docker=Depends(get_docker_manager),
                           user: User = Depends(get_current_user)):
    return await _delete(session, docker, request, user, user.id, template_id)


@users_router.get("/{user_id}/profiles")
async def user_profiles(user_id: str, admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    return await _list(session, user_id)


@users_router.delete("/{user_id}/profiles/{template_id}", status_code=204)
async def delete_user_profile(user_id: str, template_id: str, request: Request,
                              admin: User = Depends(require_admin),
                              session: AsyncSession = Depends(get_session),
                              docker=Depends(get_docker_manager)):
    return await _delete(session, docker, request, admin, user_id, template_id)
