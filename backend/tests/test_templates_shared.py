import pytest

from app.models import ServiceTemplate

BODY = {"name": "s1", "display_name": "S1", "image": "img"}


async def _shared(session, name="s1"):
    t = ServiceTemplate(name=name, display_name=name, image="img", shared=True)
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t.id


@pytest.mark.asyncio
async def test_member_cannot_create_shared(member_client):
    r = await member_client.post("/api/templates", json=dict(BODY, shared=True))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_share_own(member_client):
    r = await member_client.post("/api/templates", json=dict(BODY, name="own"))
    assert r.status_code == 201
    r = await member_client.put(f"/api/templates/{r.json()['id']}", json={"shared": True})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_member_cannot_edit_or_delete_shared(member_client, session):
    tid = await _shared(session)
    assert (await member_client.put(f"/api/templates/{tid}", json={"description": "x"})).status_code == 403
    assert (await member_client.delete(f"/api/templates/{tid}")).status_code == 403


@pytest.mark.asyncio
async def test_member_lists_only_shared(member_client, session):
    await _shared(session)
    await member_client.post("/api/templates", json=dict(BODY, name="own"))
    r = await member_client.get("/api/templates?shared=1")
    assert r.status_code == 200
    assert {t["name"] for t in r.json()} == {"s1"}


@pytest.mark.asyncio
async def test_admin_can_create_shared(admin_client):
    r = await admin_client.post("/api/templates", json=dict(BODY, shared=True))
    assert r.status_code == 201
