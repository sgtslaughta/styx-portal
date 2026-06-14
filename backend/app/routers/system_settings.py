from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.settings_store import settings, SCHEMA

router = APIRouter()


@router.get("")
async def get_settings(admin: User = Depends(require_admin)):
    return settings.effective()


@router.patch("")
async def patch_settings(body: dict, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No settings provided")
    for key in body:
        if key not in SCHEMA:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {key}")
    try:
        for key, value in body.items():
            await settings.set(session, key, value, actor_id=admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await audit_request(session, request, "settings.update", user_id=admin.id,
                        detail={"keys": sorted(body.keys())})
    await session.commit()
    return settings.effective()


@router.post("/{key}/reset")
async def reset_setting(key: str, request: Request,
                        admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    if key not in SCHEMA:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {key}")
    await settings.reset(session, key, actor_id=admin.id)
    await audit_request(session, request, "settings.reset", user_id=admin.id,
                        detail={"key": key})
    await session.commit()
    return settings.effective()
