import hashlib

import pytest
from sqlmodel import select

from app.models import User, Workstation, WorkstationAccess
from app.services import ws_thumb

JPG = b"\xff\xd8\xff\xe0" + b"0" * 20
H = {"Authorization": "Bearer thumb-tok", "Content-Type": "image/jpeg"}


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(ws_thumb._settings, "SCREENSHOT_CACHE_DIR", str(tmp_path))
    return tmp_path


async def _ws(session, **kw) -> Workstation:
    from app.security.passwords import hash_password
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        admin = User(username="adm-t", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk", status="online",
                     agent_token_hash=hashlib.sha256(b"thumb-tok").hexdigest(),
                     created_by=admin.id, **kw)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


@pytest.mark.asyncio
async def test_upload_then_user_fetch(client, admin_client, session, _cache):
    ws = await _ws(session)
    r = await client.post("/api/agent/thumbnail", content=JPG, headers=H)
    assert r.status_code == 204
    assert (_cache / f"ws-{ws.id}.jpg").read_bytes() == JPG
    assert not list(_cache.glob("*.tmp"))
    g = await admin_client.get(f"/api/workstations/{ws.id}/thumbnail")
    assert g.status_code == 200 and g.content == JPG
    assert g.headers["content-type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_upload_rejects_bad_magic_and_oversize_and_auth(client, session):
    await _ws(session)
    r = await client.post("/api/agent/thumbnail", content=b"PNGDATA", headers=H)
    assert r.status_code == 400
    r = await client.post("/api/agent/thumbnail",
                          content=JPG + b"0" * (512 * 1024), headers=H)
    assert r.status_code == 413
    r = await client.post("/api/agent/thumbnail", content=JPG,
                          headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_fetch_404_when_none(admin_client, session):
    ws = await _ws(session)
    assert (await admin_client.get(f"/api/workstations/{ws.id}/thumbnail")).status_code == 404
    assert (await admin_client.get("/api/workstations/nope/thumbnail")).status_code == 404


@pytest.mark.asyncio
async def test_fetch_denied_without_access(member_client, session, _cache):
    ws = await _ws(session)
    (_cache / f"ws-{ws.id}.jpg").write_bytes(JPG)
    assert (await member_client.get(f"/api/workstations/{ws.id}/thumbnail")).status_code == 403
    member = (await session.exec(select(User).where(User.username == "member"))).first()
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=member.id))
    await session.commit()
    assert (await member_client.get(f"/api/workstations/{ws.id}/thumbnail")).status_code == 200


@pytest.mark.asyncio
async def test_hidden_while_someone_else_is_connected(member_client, session, _cache):
    ws = await _ws(session, all_users=True, active_connections=1)
    member = (await session.exec(select(User).where(User.username == "member"))).first()
    ws.occupied_by = ws.created_by        # the admin's session
    session.add(ws)
    await session.commit()
    (_cache / f"ws-{ws.id}.jpg").write_bytes(JPG)
    url = f"/api/workstations/{ws.id}/thumbnail"
    assert (await member_client.get(url)).status_code == 404
    ws.occupied_by = member.id
    session.add(ws)
    await session.commit()
    assert (await member_client.get(url)).status_code == 200      # own session
    ws.active_connections, ws.occupied_by, ws.status = 0, None, "revoked"
    session.add(ws)
    await session.commit()
    assert (await member_client.get(url)).status_code == 404      # revoked


@pytest.mark.asyncio
async def test_purge_and_deregister_delete_file(client, admin_client, session, _cache):
    ws = await _ws(session)
    f = _cache / f"ws-{ws.id}.jpg"
    f.write_bytes(JPG)
    assert (await admin_client.delete(f"/api/workstations/{ws.id}?purge=true")).status_code == 200
    assert not f.exists()
    ws2 = await _ws(session)
    f2 = _cache / f"ws-{ws2.id}.jpg"
    f2.write_bytes(JPG)
    assert (await client.post("/api/agent/deregister", headers=H)).status_code == 200
    assert not f2.exists()
