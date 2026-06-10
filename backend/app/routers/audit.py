from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import AuditLog, User
from app.security.deps import require_admin

router = APIRouter()


@router.get("")
async def list_audit(
    limit: int = Query(100, le=500),
    offset: int = 0,
    action: str | None = None,
    user_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    stmt = stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    return (await session.exec(stmt)).all()
