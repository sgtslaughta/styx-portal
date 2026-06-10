import hashlib
import pytest
from sqlmodel import select

from app.models import User, Workstation


async def _make_ws(session, *, status="pending", token="agent-tok-1") -> Workstation:
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        from app.security.passwords import hash_password
        admin = User(username="adm-x", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status=status,
                     agent_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


def _auth(token="agent-tok-1"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_heartbeat_requires_token(client, session):
    await _make_ws(session)
    assert (await client.post("/api/agent/heartbeat", json={})).status_code == 401
    assert (await client.post("/api/agent/heartbeat", json={},
                              headers=_auth("wrong"))).status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_marks_online_and_returns_settings(client, session):
    ws = await _make_ws(session)
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online", "lan_ip": "192.168.1.99"},
                          headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ok"
    assert body["stream_settings"]["framerate"] == 60
    await session.refresh(ws)
    assert ws.status == "online"
    assert ws.lan_ip == "192.168.1.99"
    assert ws.last_heartbeat is not None


@pytest.mark.asyncio
async def test_heartbeat_revoked_workstation(client, session):
    await _make_ws(session, status="revoked")
    r = await client.post("/api/agent/heartbeat", json={}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["state"] == "revoked"


@pytest.mark.asyncio
async def test_deregister_deletes_row(client, session):
    ws = await _make_ws(session)
    r = await client.post("/api/agent/deregister", json={}, headers=_auth())
    assert r.status_code == 200
    assert (await session.get(Workstation, ws.id)) is None
