import pytest
from sqlmodel import select

from app.models import AuditLog
from app.services.audit import audit


@pytest.mark.asyncio
async def test_audit_writes_row(session):
    await audit(session, "auth.login", user_id="u1", actor_ip="1.2.3.4",
                resource="u1", detail={"ok": True})
    await session.commit()
    rows = (await session.exec(select(AuditLog))).all()
    assert len(rows) == 1
    assert rows[0].action == "auth.login"
    assert rows[0].detail == {"ok": True}
    assert rows[0].user_id == "u1"
    assert rows[0].actor_ip == "1.2.3.4"


@pytest.mark.asyncio
async def test_audit_redacts_secret_keys(session):
    await audit(session, "provider.update", detail={"client_secret": "x", "name": "g"})
    await session.commit()
    row = (await session.exec(select(AuditLog))).first()
    assert row.detail["client_secret"] == "[redacted]"
    assert row.detail["name"] == "g"


@pytest.mark.asyncio
async def test_audit_redacts_password(session):
    await audit(session, "user.create", detail={"password": "secret123", "username": "bob"})
    await session.commit()
    row = (await session.exec(select(AuditLog))).first()
    assert row.detail["password"] == "[redacted]"
    assert row.detail["username"] == "bob"


@pytest.mark.asyncio
async def test_audit_list_requires_admin(member_client):
    r = await member_client.get("/api/audit")
    assert r.status_code in (401, 403)


@pytest.mark.asyncio
async def test_audit_list_admin_ok_with_filters(admin_client, session):
    # Add some audit logs directly
    from app.models import AuditLog
    session.add(AuditLog(action="auth.login", user_id="u1", detail={"ok": True}))
    session.add(AuditLog(action="user.create", user_id="admin", detail={"username": "newuser"}))
    await session.commit()

    r = await admin_client.get("/api/audit?limit=10&action=auth.login")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["action"] == "auth.login"


@pytest.mark.asyncio
async def test_audit_list_filters_by_user_id(admin_client, session):
    # Add some audit logs directly
    from app.models import AuditLog
    session.add(AuditLog(action="auth.login", user_id="u1"))
    session.add(AuditLog(action="auth.login", user_id="u2"))
    session.add(AuditLog(action="user.create", user_id="u1"))
    await session.commit()

    r = await admin_client.get("/api/audit?user_id=u1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    for item in data:
        assert item["user_id"] == "u1"


@pytest.mark.asyncio
async def test_audit_list_respects_limit_and_offset(admin_client, session):
    # Add 5 audit logs
    from app.models import AuditLog
    for i in range(5):
        session.add(AuditLog(action=f"action.{i}"))
    await session.commit()

    r = await admin_client.get("/api/audit?limit=2&offset=0")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2

    r = await admin_client.get("/api/audit?limit=2&offset=2")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_audit_list_returns_ordered_by_id_desc(admin_client, session):
    # Add audit logs
    from app.models import AuditLog
    session.add(AuditLog(action="action.1"))
    await session.commit()
    session.add(AuditLog(action="action.2"))
    await session.commit()
    session.add(AuditLog(action="action.3"))
    await session.commit()

    r = await admin_client.get("/api/audit")
    assert r.status_code == 200
    data = r.json()
    # Newest first
    assert data[0]["action"] == "action.3"
    assert data[1]["action"] == "action.2"
    assert data[2]["action"] == "action.1"


@pytest.mark.asyncio
async def test_setup_audit_logged(client, session):
    """Verify setup endpoint audits the user creation as auth.signup."""
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    admin_id = r.json()["id"]

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.signup"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].detail["role"] == "admin"
    assert rows[0].detail["via"] == "setup"
    # Invite token should NOT appear in audit logs
    assert "token" not in rows[0].detail


@pytest.mark.asyncio
async def test_accept_invite_audit_logged(client, session):
    """Verify accept_invite endpoint audits the user creation as auth.accept_invite."""
    from app.models import User, Invite
    from app.security.passwords import hash_password
    import hashlib

    # Setup admin and create an invite
    admin = User(username="admin", password_hash=hash_password("x"),
                 role="admin", is_active=True)
    session.add(admin)
    await session.commit()

    raw_token = "test-invite-token-123"
    invite = Invite(
        email="user@test.com",
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        role="user",
        created_by=admin.id
    )
    session.add(invite)
    await session.commit()

    # Get CSRF token
    r = await client.get("/api/auth/csrf")
    assert r.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers.update({"X-CSRF-Token": csrf})

    # Accept invite
    r = await client.post("/api/auth/accept-invite", json={
        "username": "newuser",
        "password": "correct horse battery staple",
        "token": raw_token
    })
    assert r.status_code == 201
    user_id = r.json()["id"]

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.accept_invite"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].detail["role"] == "user"
    # Invite token should NOT appear in audit logs
    assert "token" not in rows[0].detail


@pytest.mark.asyncio
async def test_logout_audit_logged(admin_client, session):
    """Verify logout endpoint audits as auth.logout with user_id from token."""
    # Get user ID from /me
    me = (await admin_client.get("/api/auth/me")).json()
    user_id = me["id"]

    # Logout
    r = await admin_client.post("/api/auth/logout")
    assert r.status_code == 200

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.logout"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == user_id


@pytest.mark.asyncio
async def test_create_invite_audit_logged(admin_client, session):
    """Verify create_invite endpoint audits as invite.create."""
    me = (await admin_client.get("/api/auth/me")).json()
    admin_id = me["id"]

    r = await admin_client.post("/api/users/invites", json={
        "email": "newuser@test.com",
        "role": "user"
    })
    assert r.status_code == 201
    invite_token = r.json()["token"]

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "invite.create"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].detail["email"] == "newuser@test.com"
    assert rows[0].detail["role"] == "user"
    # Invite token should NOT appear in audit logs
    assert invite_token not in str(rows[0].detail)


@pytest.mark.asyncio
async def test_disable_user_audit_logged(admin_client, session):
    """Verify disable_user endpoint audits as user.disable."""
    from app.models import User
    from app.security.passwords import hash_password

    # Create a user to disable
    user = User(username="bob", password_hash=hash_password("x"),
                role="user", is_active=True)
    session.add(user)
    await session.commit()
    user_id = user.id

    # Get admin ID
    me = (await admin_client.get("/api/auth/me")).json()
    admin_id = me["id"]

    # Disable the user
    r = await admin_client.patch(f"/api/users/{user_id}/disable")
    assert r.status_code == 200
    assert r.json()["is_active"] is False

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "user.disable"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].resource == user_id


@pytest.mark.asyncio
async def test_role_change_audit_logged(admin_client, session):
    """Verify change_role endpoint audits as user.role_change."""
    from app.models import User
    from app.security.passwords import hash_password

    # Create a user to promote
    user = User(username="bob", password_hash=hash_password("x"),
                role="user", is_active=True)
    session.add(user)
    await session.commit()
    user_id = user.id

    # Get admin ID
    me = (await admin_client.get("/api/auth/me")).json()
    admin_id = me["id"]

    # Promote to admin
    r = await admin_client.patch(f"/api/users/{user_id}/role?role=admin")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    rows = (await session.exec(select(AuditLog).where(
        AuditLog.action == "user.role_change"))).all()
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].resource == user_id
    assert rows[0].detail["new_role"] == "admin"
    assert rows[0].detail["via"] == "manual"
