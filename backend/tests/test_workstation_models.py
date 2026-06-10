import pytest
from datetime import datetime, timedelta, timezone

from app.models import User, Workstation, WorkstationEnrollmentToken, WorkstationAccess
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_workstation_defaults(session):
    admin = User(username="a", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    ws = Workstation(name="desk", subdomain="desk", created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    assert ws.status == "pending"
    assert ws.display_server == "x11"
    assert ws.protocol == "http"
    assert ws.stream_settings["framerate"] == 60
    assert ws.all_users is False


@pytest.mark.asyncio
async def test_enrollment_token_and_access(session):
    admin = User(username="a", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    tok = WorkstationEnrollmentToken(
        token_hash="h" * 64, created_by=admin.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    ws = Workstation(name="desk", subdomain="desk", created_by=admin.id)
    session.add(tok)
    session.add(ws)
    await session.commit()
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=admin.id))
    await session.commit()
    assert tok.used_at is None
