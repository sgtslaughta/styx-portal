import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security.deps import require_admin
from app.services.turn_usage import usage_report

router = APIRouter()
_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@router.get("")
async def get_turn_usage(month: str | None = None, admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    if month is not None and not _MONTH_RE.fullmatch(month):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "month must be YYYY-MM")
    return await usage_report(session, month)
