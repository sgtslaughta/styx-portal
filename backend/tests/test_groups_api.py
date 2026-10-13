# backend/tests/test_groups_api.py
import pytest
from sqlmodel import select

from app.models import User


@pytest.mark.asyncio
async def test_group_crud_and_membership(admin_client, session):
    r = await admin_client.post("/api/groups", json={"name": "media", "description": "Jellyfin"})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r = await admin_client.post("/api/groups", json={"name": "media"})
    assert r.status_code == 409
    r = await admin_client.get("/api/groups")
    assert [g["name"] for g in r.json()] == ["media"]

    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    r = await admin_client.put(f"/api/users/{admin.id}/groups", json={"group_ids": [gid]})
    assert r.status_code == 200
    r = await admin_client.get(f"/api/users/{admin.id}/groups")
    assert r.json() == [gid]
    r = await admin_client.get("/api/groups")
    assert r.json()[0]["member_count"] == 1

    r = await admin_client.delete(f"/api/groups/{gid}")
    assert r.status_code == 204
    r = await admin_client.get(f"/api/users/{admin.id}/groups")
    assert r.json() == []


@pytest.mark.asyncio
async def test_groups_admin_only(member_client):
    r = await member_client.get("/api/groups")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_group_name_rejects_comma(admin_client):
    r = await admin_client.post("/api/groups", json={"name": "ops,dev"})
    assert r.status_code == 422
