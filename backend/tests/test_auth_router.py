import pytest


@pytest.mark.asyncio
async def test_setup_required_initially_true(client):
    r = await client.get("/api/auth/setup-required")
    assert r.json()["setup_required"] is True


@pytest.mark.asyncio
async def test_setup_creates_admin_and_locks(client):
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"
    r2 = await client.post("/api/auth/setup", json={
        "username": "user2", "password": "another long password"})
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_me_after_setup(admin_client):
    r = await admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


@pytest.mark.asyncio
async def test_login_bad_credentials(admin_client):
    r = await admin_client.post("/api/auth/login",
                                json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_instances_401(client):
    r = await client.get("/api/instances")
    assert r.status_code == 401


async def _occupy_workstation(session, conns=1):
    """Create a workstation occupied by the admin user with a live connection."""
    from sqlmodel import select
    from app.models import User, Workstation

    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    ws = Workstation(name="d", subdomain="d", hostname="d", status="online",
                     active_connections=conns, occupied_by=admin.id,
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


@pytest.mark.asyncio
async def test_logout_blocked_by_active_session(admin_client, session):
    """Active workstation session blocks a plain logout (409); user stays in."""
    await _occupy_workstation(session)
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "active_session"
    r2 = await admin_client.post("/api/auth/refresh")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_logout_end_session_frees_and_flags(admin_client, session):
    """logout?end_session=true frees occupancy + flags the agent to disconnect."""
    ws = await _occupy_workstation(session)
    r = await admin_client.post("/api/auth/logout?end_session=true")
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.disconnect_pending is True
    assert ws.occupied_by is None
    assert ws.active_connections == 0
    # refresh token revoked too — user is genuinely logged out
    r2 = await admin_client.post("/api/auth/refresh")
    assert r2.status_code != 200


@pytest.mark.asyncio
async def test_logout_revokes_refresh(admin_client):
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200
    # After logout, CSRF cookie is cleared, so bootstrap a new one to reach the auth check
    csrf_r = await admin_client.get("/api/auth/csrf")
    assert csrf_r.status_code == 200
    csrf = admin_client.cookies.get("csrf_token")
    admin_client.headers.update({"X-CSRF-Token": csrf})
    r2 = await admin_client.post("/api/auth/refresh")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_setup_enforces_password_policy(client, session):
    from app.services.settings_store import settings
    await settings.set(session, "PASSWORD_REQUIRE_DIGIT", True, actor_id=None)
    await settings.set(session, "PASSWORD_MIN_LENGTH", 12, actor_id=None)
    await session.commit()
    r = await client.post("/api/auth/setup",
                          json={"username": "admin", "password": "no-digits-here!"})
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_change_password_success(member_client, session):
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "correct horse battery staple",
                                       "new_password": "NewLongEnough123!"})
    assert r.status_code == 200, r.text
    from app.models import User
    from sqlmodel import select
    u = (await session.exec(select(User).where(User.username == "member"))).first()
    assert u.must_change_pw is False


@pytest.mark.asyncio
async def test_change_password_wrong_old(member_client):
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "wrong",
                                       "new_password": "NewLongEnough123!"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_change_password_weak_new(member_client, session):
    from app.services.settings_store import settings
    await settings.set(session, "PASSWORD_REQUIRE_SYMBOL", True, actor_id=None)
    await session.commit()
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "correct horse battery staple",
                                       "new_password": "NoSymbolsHere123"})
    assert r.status_code == 422
