
from app.models import User, Workstation, WorkstationAccess
from app.security.passwords import hash_password
from app.services.workstations import kick_unqualified


async def _setup(session, all_users=False, grant=True):
    u = User(username="dave", password_hash=hash_password("x"), role="user")
    session.add(u)
    await session.commit()
    ws = Workstation(name="d", subdomain="d", hostname="d", lan_ip="192.168.1.5",
                     status="online", all_users=all_users, active_connections=1,
                     created_by=u.id)
    session.add(ws)
    await session.commit()
    if grant:
        session.add(WorkstationAccess(workstation_id=ws.id, user_id=u.id))
    ws.occupied_by = u.id
    session.add(ws)
    await session.commit()
    return u, ws


async def test_disabled_user_stream_kicked(admin_client, session):
    u, ws = await _setup(session)
    assert (await admin_client.patch(f"/api/users/{u.id}/disable")).status_code == 200
    await session.refresh(ws)
    assert ws.disconnect_pending is True and ws.occupied_by is None


async def test_access_removed_kicks(admin_client, session):
    u, ws = await _setup(session)
    r = await admin_client.put(f"/api/workstations/{ws.id}/access", json={"user_ids": []})
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.disconnect_pending is True


async def test_access_kept_does_not_kick(admin_client, session):
    u, ws = await _setup(session)
    await admin_client.put(f"/api/workstations/{ws.id}/access", json={"user_ids": [u.id]})
    await session.refresh(ws)
    assert ws.disconnect_pending is False and ws.occupied_by == u.id


async def test_all_users_off_kicks(admin_client, session):
    u, ws = await _setup(session, all_users=True, grant=False)
    await admin_client.patch(f"/api/workstations/{ws.id}", json={"all_users": False})
    await session.refresh(ws)
    assert ws.disconnect_pending is True


async def test_delete_user_kicks_helper(session):
    u, ws = await _setup(session)
    assert await kick_unqualified(session, user_id=u.id, force=True) == 1


async def test_direct_websocket_takeover_denied(client, session):
    u, ws = await _setup(session)
    other = User(username="erin", password_hash=hash_password("x"), role="user")
    session.add(other)
    await session.commit()
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=other.id))
    await session.commit()
    await client.get("/api/auth/csrf")
    assert (await client.post("/api/auth/login",
            json={"username": "erin", "password": "x"})).status_code == 200
    r = await client.get(f"/internal/workstations/{ws.id}/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/websockets"})
    assert r.status_code == 403
    await session.refresh(ws)
    assert ws.occupied_by == u.id
    # explicit takeover via /connect?force=true admits erin
    assert (await client.get(f"/api/workstations/{ws.id}/connect?force=true")).status_code == 200
    r = await client.get(f"/internal/workstations/{ws.id}/auth-check",
                         headers={"X-Forwarded-Uri": f"/w/{ws.subdomain}/websockets"})
    assert r.status_code == 200


async def test_takeover_grant_survives_parallel_websocket(client, session):
    """F13: a second websocket opened with the same grant must not be refused."""
    u, ws = await _setup(session)
    other = User(username="erin", password_hash=hash_password("x"), role="user")
    session.add(other)
    await session.commit()
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=other.id))
    await session.commit()
    await client.get("/api/auth/csrf")
    await client.post("/api/auth/login", json={"username": "erin", "password": "x"})
    await client.get(f"/api/workstations/{ws.id}/connect?force=true")
    hdr = {"X-Forwarded-Uri": f"/w/{ws.subdomain}/websockets"}
    path = f"/internal/workstations/{ws.id}/auth-check"
    assert (await client.get(path, headers=hdr)).status_code == 200
    ws.occupied_by = u.id            # as if the first upgrade's commit had not landed yet
    session.add(ws)
    await session.commit()
    assert (await client.get(path, headers=hdr)).status_code == 200


async def test_auth_check_injects_basic_auth(client, session):
    import base64
    from app.security.crypto import encrypt_secret
    u, ws = await _setup(session)
    ws.selkies_password_enc = encrypt_secret("s3cret")
    session.add(ws)
    await session.commit()
    await client.get("/api/auth/csrf")
    await client.post("/api/auth/login", json={"username": "dave", "password": "x"})
    r = await client.get(f"/internal/workstations/{ws.id}/auth-check")
    assert r.status_code == 200
    assert r.headers["authorization"] == "Basic " + base64.b64encode(b"styx:s3cret").decode()


async def test_auth_check_denied_has_no_authorization(client, session):
    from app.security.crypto import encrypt_secret
    u, ws = await _setup(session, grant=False)
    ws.selkies_password_enc = encrypt_secret("s3cret")
    session.add(ws)
    await session.commit()
    r = await client.get(f"/internal/workstations/{ws.id}/auth-check")
    assert r.status_code != 200 and "authorization" not in r.headers
    await client.get("/api/auth/csrf")
    await client.post("/api/auth/login", json={"username": "dave", "password": "x"})
    r = await client.get(f"/internal/workstations/{ws.id}/auth-check")
    assert r.status_code == 403 and "authorization" not in r.headers
