"""Invite / enrollment tokens are claimed atomically (no check-then-set race)."""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlmodel import select, update

from app.models import Invite, User, WorkstationEnrollmentToken, FederatedIdentity

PW = "correct horse battery staple"


def _race_after_select(session, monkeypatch, table_fragment, model):
    """After the first SELECT touching `table_fragment`, a 'concurrent request' claims the row."""
    real = session.exec
    state = {"done": False}

    async def exec_(stmt, *a, **k):
        res = await real(stmt, *a, **k)
        text = str(stmt)
        if not state["done"] and text.lstrip().upper().startswith("SELECT") and table_fragment in text:
            state["done"] = True
            await real(update(model).values(used_at=datetime.now(timezone.utc))
                       .execution_options(synchronize_session=False))
        return res

    monkeypatch.setattr(session, "exec", exec_)


async def test_accept_invite_loses_race_gets_400_and_no_user(client, session, monkeypatch):
    admin = User(username="adm", password_hash="x", role="admin")
    session.add(admin)
    await session.flush()
    session.add(Invite(token_hash=hashlib.sha256(b"tok").hexdigest(), role="user",
                       created_by=admin.id))
    await session.commit()
    await client.get("/api/auth/csrf")
    _race_after_select(session, monkeypatch, "invites", Invite)
    r = await client.post("/api/auth/accept-invite", json={
        "token": "tok", "username": "newbie", "password": PW},
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")})
    assert r.status_code == 400, r.text
    monkeypatch.undo()
    assert (await session.exec(select(User).where(User.username == "newbie"))).first() is None


async def test_enroll_register_loses_race_gets_401(client, session, monkeypatch):
    admin = User(username="adm", password_hash="x", role="admin")
    session.add(admin)
    await session.flush()
    session.add(WorkstationEnrollmentToken(
        token_hash=hashlib.sha256(b"etok").hexdigest(), created_by=admin.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1)))
    await session.commit()
    _race_after_select(session, monkeypatch, "workstation_enrollment_tokens",
                       WorkstationEnrollmentToken)
    r = await client.post("/api/enroll/register", json={
        "token": "etok", "hostname": "h", "lan_ip": "192.168.1.5"})
    assert r.status_code == 401, r.text


async def test_sso_invite_loses_race_creates_no_account(session, monkeypatch):
    import pytest
    from app.schemas import OAuthIdentity
    from app.services import federation
    session.add(Invite(token_hash="h", email="a@b.c", role="user", created_by="adm"))
    await session.commit()
    _race_after_select(session, monkeypatch, "invites", Invite)
    with pytest.raises(federation.NotAuthorized):
        await federation.resolve_identity(
            session, "google", OAuthIdentity(sub="s1", email="a@b.c", email_verified=True, claims={}))
    monkeypatch.undo()
    assert (await session.exec(select(FederatedIdentity))).all() == []
