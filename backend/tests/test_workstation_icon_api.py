import base64
import hashlib

import pytest
from sqlmodel import select

from app.models import AuditLog, User, Workstation

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20
PNG_URI = "data:image/png;base64," + base64.b64encode(PNG).decode()


async def _ws(session, token="icon-tok", **kw) -> Workstation:
    from app.security.passwords import hash_password
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        admin = User(username="adm-i", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk", status="online",
                     agent_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     created_by=admin.id, **kw)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


@pytest.mark.asyncio
async def test_set_image_and_serve_with_etag(admin_client, session):
    ws = await _ws(session)
    r = await admin_client.put(f"/api/workstations/{ws.id}/icon",
                               json={"kind": "image", "value": PNG_URI})
    assert r.status_code == 200 and r.json()["icon_kind"] == "image"
    etag_v = r.json()["icon_etag"]
    g = await admin_client.get(f"/api/workstations/{ws.id}/icon")
    assert g.status_code == 200 and g.content == PNG
    assert g.headers["content-type"] == "image/png"
    assert g.headers["cache-control"] == "private, max-age=300"
    assert g.headers["x-content-type-options"] == "nosniff"
    assert g.headers["etag"].strip('"') == etag_v
    n = await admin_client.get(f"/api/workstations/{ws.id}/icon",
                               headers={"If-None-Match": g.headers["etag"]})
    assert n.status_code == 304
    log = (await session.exec(select(AuditLog).where(
        AuditLog.action == "workstation.icon_change"))).first()
    assert log is not None and log.resource == ws.id


@pytest.mark.asyncio
async def test_auto_svg_headers_and_reset(admin_client, session):
    ws = await _ws(session, icon="emoji:\U0001F680")
    g = await admin_client.get(f"/api/workstations/{ws.id}/icon")
    assert g.headers["content-type"].startswith("image/svg+xml")
    assert g.headers["content-security-policy"] == (
        "default-src 'none'; style-src 'unsafe-inline'; sandbox")
    r = await admin_client.put(f"/api/workstations/{ws.id}/icon", json={"kind": "auto"})
    assert r.json()["icon_kind"] == "auto"
    await session.refresh(ws)
    assert ws.icon is None
    assert b">D<" in (await admin_client.get(f"/api/workstations/{ws.id}/icon")).content


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"kind": "emoji", "value": "ab"},
    {"kind": "image", "value": "data:image/png;base64," + base64.b64encode(b"nope").decode()},
    {"kind": "image", "value": None},
])
async def test_bad_icon_is_400(admin_client, session, body):
    ws = await _ws(session)
    r = await admin_client.put(f"/api/workstations/{ws.id}/icon", json=body)
    assert r.status_code == 400 and isinstance(r.json()["detail"], str)


@pytest.mark.asyncio
async def test_member_cannot_set_icon(member_client, session):
    ws = await _ws(session)
    r = await member_client.put(f"/api/workstations/{ws.id}/icon", json={"kind": "auto"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_member_icon_access_follows_workstation_visibility(member_client, session):
    ws = await _ws(session)
    assert (await member_client.get(f"/api/workstations/{ws.id}/icon")).status_code == 403
    ws.all_users = True
    session.add(ws)
    await session.commit()
    assert (await member_client.get(f"/api/workstations/{ws.id}/icon")).status_code == 200
    assert (await member_client.get("/api/workstations/nope/icon")).status_code == 404


@pytest.mark.asyncio
async def test_heartbeat_icon_etag_and_agent_fetch(client, session):
    ws = await _ws(session, icon=PNG_URI)
    h = {"Authorization": "Bearer icon-tok"}
    r = await client.post("/api/agent/heartbeat", json={"status": "online"}, headers=h)
    etag = r.json()["icon_etag"]
    assert len(etag) == 16
    g = await client.get("/api/agent/icon", headers=h)
    assert g.status_code == 200 and g.content == PNG
    assert g.headers["etag"].strip('"') == etag
    ws.icon = None
    session.add(ws)
    await session.commit()
    r2 = await client.post("/api/agent/heartbeat", json={"status": "online"}, headers=h)
    assert r2.json()["icon_etag"] != etag


@pytest.mark.asyncio
async def test_agent_icon_requires_agent_token(client, session):
    await _ws(session)
    assert (await client.get("/api/agent/icon")).status_code == 401
    r = await client.get("/api/agent/icon", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["W/{e}", "{e}", '"zz", {e}', "*"])
async def test_if_none_match_variants(admin_client, session, fmt):
    ws = await _ws(session)
    e = (await admin_client.get(f"/api/workstations/{ws.id}/icon")).headers["etag"]
    r = await admin_client.get(f"/api/workstations/{ws.id}/icon",
                               headers={"If-None-Match": fmt.format(e=e)})
    assert r.status_code == 304
