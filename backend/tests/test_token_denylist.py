"""Hard kill-on-logout: access-token jti denylist.

Stateless access tokens stay valid until exp even after logout; the denylist
lets logout invalidate the token immediately (closes the workstation-reconnect
replay window). Unit-level so it doesn't depend on the CSRF/login fixtures.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.security import tokens
from app.security.deps import get_current_user
from app.services import token_denylist


def _now():
    return datetime.now(timezone.utc)


def _req(cookies=None, headers=None):
    raw = []
    if cookies:
        raw.append((b"cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()).encode()))
    for k, v in (headers or {}).items():
        raw.append((k.lower().encode(), v.encode()))
    return Request({"type": "http", "method": "GET", "path": "/",
                    "query_string": b"", "headers": raw,
                    "client": ("127.0.0.1", 12345)})


async def _mkuser(session):
    from app.models import User
    from app.security.passwords import hash_password
    u = User(username="deny-" + uuid.uuid4().hex[:6],
             password_hash=hash_password("x"), role="member")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    return u


def test_access_token_carries_unique_jti():
    a = tokens.decode_token(tokens.create_access_token("u1", "member"))
    b = tokens.decode_token(tokens.create_access_token("u1", "member"))
    assert a.get("jti") and b.get("jti") and a["jti"] != b["jti"]


@pytest.mark.asyncio
async def test_revoke_and_is_revoked_roundtrip(session):
    jti = str(uuid.uuid4())
    assert await token_denylist.is_access_revoked(session, jti) is False
    assert await token_denylist.is_access_revoked(session, None) is False
    await token_denylist.revoke_access(session, jti, _now() + timedelta(minutes=15))
    await session.commit()
    assert await token_denylist.is_access_revoked(session, jti) is True


@pytest.mark.asyncio
async def test_revoke_purges_expired_entries(session):
    stale = str(uuid.uuid4())
    await token_denylist.revoke_access(session, stale, _now() - timedelta(seconds=1))
    await session.commit()
    fresh = str(uuid.uuid4())
    await token_denylist.revoke_access(session, fresh, _now() + timedelta(minutes=15))
    await session.commit()
    # the already-expired entry is purged; it can't outlive the token anyway
    assert await token_denylist.is_access_revoked(session, stale) is False
    assert await token_denylist.is_access_revoked(session, fresh) is True


@pytest.mark.asyncio
async def test_get_current_user_rejects_revoked_token(session):
    u = await _mkuser(session)
    tok = tokens.create_access_token(u.id, u.role)
    claims = tokens.decode_token(tok)
    # valid before revoke
    got = await get_current_user(_req(cookies={"access_token": tok}), session)
    assert got.id == u.id
    # revoke -> immediately rejected, even though exp is still in the future
    await token_denylist.revoke_access(
        session, claims["jti"], datetime.fromtimestamp(claims["exp"], tz=timezone.utc))
    await session.commit()
    with pytest.raises(HTTPException) as e:
        await get_current_user(_req(cookies={"access_token": tok}), session)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_current_access_token(session):
    """End-to-end wiring: logging out denylists the caller's access-token jti,
    so it can no longer pass forward-auth (the workstation reconnect gate)."""
    from starlette.responses import Response

    from app.routers.auth import logout
    from app.routers.workstations import auth_check
    u = await _mkuser(session)
    access = tokens.create_access_token(u.id, u.role)
    claims = tokens.decode_token(access)

    await logout(_req(cookies={"access_token": access}), Response(),
                 end_session=False, session=session)

    assert await token_denylist.is_access_revoked(session, claims["jti"]) is True
    # the revoked token is now rejected at the stream reconnect gate
    with pytest.raises(HTTPException) as e:
        await auth_check(_req(cookies={"access_token": access},
                              headers={"x-forwarded-uri": "/w/desk/websocket"}), session)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_check_rejects_revoked_token(session):
    """The workstation forward-auth (stream reconnect gate) honors the denylist."""
    from app.routers.workstations import auth_check
    u = await _mkuser(session)
    tok = tokens.create_access_token(u.id, u.role)
    claims = tokens.decode_token(tok)
    await token_denylist.revoke_access(
        session, claims["jti"], datetime.fromtimestamp(claims["exp"], tz=timezone.utc))
    await session.commit()
    req = _req(cookies={"access_token": tok},
               headers={"x-forwarded-uri": "/w/desk/websocket"})
    with pytest.raises(HTTPException) as e:
        await auth_check(req, session)
    assert e.value.status_code == 401
