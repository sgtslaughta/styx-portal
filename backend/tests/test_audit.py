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
