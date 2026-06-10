import pytest
import hashlib

from app.models import User, Invite
from app.security.passwords import hash_password
from app.security.csrf import CSRF_COOKIE


@pytest.mark.asyncio
async def test_refresh_without_csrf_header_rejected(admin_client, session):
    """POST /api/auth/refresh without X-CSRF-Token header should be rejected."""
    # admin_client is already logged in and has CSRF header
    # Clear the CSRF header to simulate missing it
    admin_client.headers.pop("X-CSRF-Token", None)

    # Attempt refresh without CSRF header
    r = await admin_client.post("/api/auth/refresh")
    assert r.status_code == 403
    assert r.json()["detail"] == "CSRF check failed"


@pytest.mark.asyncio
async def test_refresh_with_csrf_header_ok(admin_client):
    """POST /api/auth/refresh with matching CSRF header should succeed."""
    # admin_client fixture already has CSRF header set
    r = await admin_client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # New CSRF token should be issued
    assert CSRF_COOKIE in admin_client.cookies


@pytest.mark.asyncio
async def test_csrf_bootstrap_sets_cookie(client):
    """GET /api/auth/csrf should issue an anonymous CSRF cookie."""
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert CSRF_COOKIE in client.cookies


@pytest.mark.asyncio
async def test_accept_invite_without_csrf_rejected(client, session):
    """POST /api/auth/accept-invite without X-CSRF-Token header should be rejected."""
    # Create admin user
    admin = User(username="admin", password_hash=hash_password("pwd"), role="admin")
    session.add(admin)
    await session.commit()

    # Create invite with created_by set
    raw_token = "test-invite-token-123"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    invite = Invite(email="user@test.com", token_hash=token_hash, role="member", created_by=admin.id)
    session.add(invite)
    await session.commit()

    # POST accept-invite without CSRF header
    r = await client.post("/api/auth/accept-invite", json={
        "token": raw_token,
        "username": "newuser",
        "password": "correct horse battery staple"
    })
    assert r.status_code == 403
    assert r.json()["detail"] == "CSRF check failed"


@pytest.mark.asyncio
async def test_accept_invite_with_csrf_ok(client, session):
    """POST /api/auth/accept-invite with CSRF token should succeed."""
    # Create admin user
    admin = User(username="admin", password_hash=hash_password("pwd"), role="admin")
    session.add(admin)
    await session.commit()

    # Create invite with created_by set
    raw_token = "test-invite-token-456"
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    invite = Invite(email="user@test.com", token_hash=token_hash, role="member", created_by=admin.id)
    session.add(invite)
    await session.commit()

    # Bootstrap CSRF
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 200
    csrf = client.cookies.get(CSRF_COOKIE)
    assert csrf
    client.headers.update({"X-CSRF-Token": csrf})

    # POST accept-invite with CSRF header
    r = await client.post("/api/auth/accept-invite", json={
        "token": raw_token,
        "username": "newuser",
        "password": "correct horse battery staple"
    })
    assert r.status_code == 201
    data = r.json()
    assert data["username"] == "newuser"
