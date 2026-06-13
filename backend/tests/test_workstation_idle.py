import hashlib
import pytest
from sqlmodel import select

from app.models import User, Workstation


async def _make_ws(session, *, status="pending", token="agent-tok-1",
                   stream_settings=None) -> Workstation:
    """Create a test workstation with optional stream_settings override."""
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        from app.security.passwords import hash_password
        admin = User(username="adm-x", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()

    settings = stream_settings if stream_settings is not None else {
        "encoder": "auto", "framerate": 60, "bitrate_kbps": 16000
    }
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status=status,
                     agent_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     created_by=admin.id,
                     stream_settings=settings)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


def _auth(token="agent-tok-1"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_idle_past_timeout_triggers_disconnect(client, session):
    """When a workstation is occupied (active_connections > 0) and has been idle
    past the timeout, the heartbeat should set disconnect_clients=True."""
    ws = await _make_ws(session, status="online")
    # Mark workstation as occupied with active connections
    ws.active_connections = 1
    ws.occupied_by = (await session.exec(select(User).where(User.role == "admin"))).first().id
    session.add(ws)
    await session.commit()

    # Send heartbeat with idle_seconds > default timeout (900s)
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online",
                                "health": {"active_connections": 1, "idle_seconds": 10_000}},
                          headers=_auth())
    assert r.status_code == 200
    assert r.json()["disconnect_clients"] is True

    # Verify disconnect_pending was set (and consumed)
    await session.refresh(ws)
    assert ws.disconnect_pending is False  # consumed by heartbeat


@pytest.mark.asyncio
async def test_active_within_timeout_no_disconnect(client, session):
    """When idle_seconds < timeout, should not disconnect."""
    ws = await _make_ws(session, status="online")
    ws.active_connections = 1
    ws.occupied_by = (await session.exec(select(User).where(User.role == "admin"))).first().id
    session.add(ws)
    await session.commit()

    # Send heartbeat with idle_seconds < default timeout (900s)
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online",
                                "health": {"active_connections": 1, "idle_seconds": 60}},
                          headers=_auth())
    assert r.status_code == 200
    assert r.json()["disconnect_clients"] is False

    await session.refresh(ws)
    assert ws.disconnect_pending is False


@pytest.mark.asyncio
async def test_idle_disabled_when_timeout_zero(client, session):
    """When idle_timeout_s=0, idle detection is disabled."""
    ws = await _make_ws(session, status="online",
                        stream_settings={"encoder": "auto", "framerate": 60,
                                        "bitrate_kbps": 16000, "idle_timeout_s": 0})
    ws.active_connections = 1
    ws.occupied_by = (await session.exec(select(User).where(User.role == "admin"))).first().id
    session.add(ws)
    await session.commit()

    # Send heartbeat with huge idle_seconds but timeout=0 should not disconnect
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online",
                                "health": {"active_connections": 1, "idle_seconds": 100_000}},
                          headers=_auth())
    assert r.status_code == 200
    assert r.json()["disconnect_clients"] is False


@pytest.mark.asyncio
async def test_idle_ignored_when_no_connections(client, session):
    """Idle detection only applies when active_connections > 0."""
    ws = await _make_ws(session, status="online")
    # Leave active_connections at 0 (default)
    session.add(ws)
    await session.commit()

    # Send heartbeat with no active connections but high idle_seconds
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online",
                                "health": {"active_connections": 0, "idle_seconds": 10_000}},
                          headers=_auth())
    assert r.status_code == 200
    assert r.json()["disconnect_clients"] is False

    await session.refresh(ws)
    assert ws.disconnect_pending is False
