import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, WorkstationEnrollmentToken
from app.schemas import EnrollTokenOut
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.workstations import build_enroll_command, sha256_hex

router = APIRouter()
_settings = Settings()


@router.post("/enroll-tokens", response_model=EnrollTokenOut, status_code=201)
async def mint_enroll_token(request: Request,
                            admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        hours=_settings.ENROLL_TOKEN_TTL_HOURS)
    session.add(WorkstationEnrollmentToken(
        token_hash=sha256_hex(raw), created_by=admin.id, expires_at=expires))
    await audit_request(session, request, "workstation.enroll_token_create",
                        user_id=admin.id)
    await session.commit()
    return EnrollTokenOut(token=raw, expires_at=expires.isoformat(),
                          command=build_enroll_command(raw))
