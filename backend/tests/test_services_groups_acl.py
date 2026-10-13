"""H: allowed_groups hold group *names*; deleting a group must not leave a dangling grant."""
import pytest

from app.models import ProxiedService, User, UserGroup
from app.routers.services_auth import user_may_open
from tests import test_services_api as _api

docker_mock = _api.docker_mock          # shared fixtures
no_route_write = _api.no_route_write


async def _member(session, name="member"):
    u = User(username=name, password_hash="x", role="member", is_active=True)
    session.add(u)
    await session.commit()
    return u


async def _group(admin_client, name):
    r = await admin_client.post("/api/groups", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_delete_and_recreate_group_does_not_revive_access(admin_client, session):
    media = await _group(admin_client, "media")
    await _group(admin_client, "ops")
    svc = ProxiedService(slug="sonarr", name="S", upstream_url="http://10.0.0.2",
                         allowed_groups=["media", "ops"])
    session.add(svc)
    await session.commit()
    assert (await admin_client.delete(f"/api/groups/{media}")).status_code == 204
    await session.refresh(svc)
    assert svc.allowed_groups == ["ops"] and svc.enabled
    new_media = await _group(admin_client, "media")
    u = await _member(session)
    session.add(UserGroup(user_id=u.id, group_id=new_media))
    await session.commit()
    assert not await user_may_open(session, u, svc)


@pytest.mark.asyncio
async def test_deleting_last_group_disables_service_fail_closed(admin_client, session):
    """[] means 'any logged-in user', so emptying the list must not open the service."""
    media = await _group(admin_client, "media")
    svc = ProxiedService(slug="sonarr", name="S", upstream_url="http://10.0.0.2",
                         allowed_groups=["media"])
    session.add(svc)
    await session.commit()
    assert (await admin_client.delete(f"/api/groups/{media}")).status_code == 204
    await session.refresh(svc)
    assert svc.allowed_groups == [] and svc.enabled is False


@pytest.mark.asyncio
async def test_unknown_allowed_group_rejected(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_api._body(allowed_groups=["ghost"]))
    assert r.status_code == 422
    await _group(admin_client, "media")
    r = await admin_client.post("/api/services", json=_api._body(allowed_groups=["media"]))
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    r = await admin_client.put(f"/api/services/{sid}",
                               json=_api._body(allowed_groups=["media", "ghost"]))
    assert r.status_code == 422
    assert (await admin_client.get("/api/services")).json()[0]["allowed_groups"] == ["media"]

