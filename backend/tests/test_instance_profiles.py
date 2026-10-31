"""Persistent profiles wired into instance create/launch/start/delete and the profiles API."""
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import select

from app.models import Instance, User, UserProfile
from app.routers.instances import _launch_instance_background
from app.services.profiles import profile_volume_name

TMPL = {
    "name": "prof-tmpl", "display_name": "Prof Desktop", "image": "test:latest",
    "internal_port": 3001, "profile_mount": "/config",
    "volumes": [{"name": "{instance_id}-home", "mount": "/config"},
                {"name": "{instance_id}-data", "mount": "/data"}],
}


@pytest.fixture
def shared_docker():
    from app.main import app
    from app.routers.instances import get_docker_manager

    manager = MagicMock()
    manager.create_volume.side_effect = lambda name, size=None: name
    manager.create_container.return_value = "container-abc123"
    manager.get_container_status.return_value = {"status": "running"}
    manager.ensure_user_network.return_value = "styx-u-test"
    app.dependency_overrides[get_docker_manager] = lambda: manager
    yield manager


@pytest.fixture
async def tid(admin_client):
    r = await admin_client.post("/api/templates", json=TMPL)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _create(c, tid, sub, **kw):
    return await c.post("/api/instances", json={
        "template_id": tid, "name": sub, "subdomain": sub, **kw})


async def _admin(session):
    return (await session.exec(select(User).where(User.username == "admin"))).first()


@pytest.mark.asyncio
async def test_use_profile_requires_profile_mount(admin_client, shared_docker):
    t = await admin_client.post("/api/templates", json={**TMPL, "name": "np", "profile_mount": None, "volumes": []})
    r = await _create(admin_client, t.json()["id"], "np", use_profile=True)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_with_profile_records_volume(admin_client, session, tid, shared_docker):
    r = await _create(admin_client, tid, "p1", use_profile=True)
    assert r.status_code == 201, r.text
    admin = await _admin(session)
    assert r.json()["profile_volume"] == profile_volume_name(admin.id, tid)
    assert (await session.exec(select(UserProfile))).first() is not None


@pytest.mark.asyncio
async def test_second_profile_launch_409_then_ok_after_stop(admin_client, tid, shared_docker):
    a = await _create(admin_client, tid, "pa", use_profile=True)
    assert a.status_code == 201
    b = await _create(admin_client, tid, "pb", use_profile=True)
    assert b.status_code == 409
    assert "Your Prof Desktop profile is in use by pa" in b.json()["detail"]
    await admin_client.post(f"/api/instances/{a.json()['id']}/stop")
    assert (await _create(admin_client, tid, "pc", use_profile=True)).status_code == 201


@pytest.mark.asyncio
async def test_start_409_when_profile_in_use(admin_client, tid, shared_docker):
    a = (await _create(admin_client, tid, "sa", use_profile=True)).json()
    await admin_client.post(f"/api/instances/{a['id']}/stop")
    b = (await _create(admin_client, tid, "sb", use_profile=True)).json()
    r = await admin_client.post(f"/api/instances/{a['id']}/start")
    assert r.status_code == 409
    r = await admin_client.post(f"/api/instances/{a['id']}/recreate")
    assert r.status_code == 409
    await admin_client.post(f"/api/instances/{b['id']}/stop")
    assert (await admin_client.post(f"/api/instances/{a['id']}/start")).status_code == 200


@pytest.mark.asyncio
async def test_launch_mounts_profile_instead_of_template_volume(session, tid):
    admin = await _admin(session)
    vol = profile_volume_name(admin.id, tid)
    inst = Instance(template_id=tid, owner_id=admin.id, name="m", subdomain="m",
                    status="starting", profile_volume=vol)
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    mgr = MagicMock()
    mgr.create_volume.side_effect = lambda name, size=None: name
    mgr.create_container.return_value = "c1"
    mgr.image_exists.return_value = True
    mgr.get_image_info.return_value = {"size_mb": 1}

    class Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            pass

    with patch("app.routers.instances.instance_runtime", return_value=mgr), \
            patch("app.routers.instances.async_session", lambda: Ctx()):
        await _launch_instance_background(inst.id, tid)
    vols = mgr.create_container.call_args.kwargs["volumes"]
    assert vols[vol] == {"bind": "/config", "mode": "rw"}
    assert vols[f"{inst.id}-data"]["bind"] == "/data"
    assert f"{inst.id}-home" not in vols
    created = [c.args[0] for c in mgr.create_volume.call_args_list]
    assert f"{inst.id}-home" not in created
    assert vol in created
    await session.refresh(inst)
    assert inst.volume_names == [f"{inst.id}-data"]


@pytest.mark.asyncio
async def test_delete_removes_instance_volumes_not_profile(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    vol = profile_volume_name(admin.id, tid)
    inst = Instance(template_id=tid, owner_id=admin.id, name="d", subdomain="d", status="stopped",
                    volume_names=["d-data"], profile_volume=vol)
    session.add(inst)
    await session.commit()
    shared_docker.remove_volume.side_effect = [RuntimeError("gone")]
    r = await admin_client.delete(f"/api/instances/{inst.id}")
    assert r.status_code == 204
    shared_docker.remove_volume.assert_called_once_with("d-data")


@pytest.mark.asyncio
async def test_profiles_api_list_delete(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    assert (await admin_client.get("/api/profiles")).json() == []
    a = (await _create(admin_client, tid, "la", use_profile=True)).json()
    rows = (await admin_client.get("/api/profiles")).json()
    vol = profile_volume_name(admin.id, tid)
    assert rows == [{"template_id": tid, "template_name": "prof-tmpl",
                     "display_name": "Prof Desktop", "volume_name": vol, "in_use": True}]
    assert (await admin_client.delete(f"/api/profiles/{tid}")).status_code == 409
    await admin_client.post(f"/api/instances/{a['id']}/stop")
    assert (await admin_client.delete(f"/api/profiles/{tid}")).status_code == 409
    assert (await admin_client.delete(f"/api/instances/{a['id']}")).status_code == 204
    assert (await admin_client.delete(f"/api/profiles/{tid}")).status_code == 204
    shared_docker.remove_volume.assert_called_with(vol)
    assert (await admin_client.delete(f"/api/profiles/{tid}")).status_code == 404
    assert (await admin_client.get("/api/profiles")).json() == []


@pytest.mark.asyncio
async def test_admin_profiles_endpoints_admin_only(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    await _create(admin_client, tid, "aa", use_profile=True)
    r = await admin_client.get(f"/api/users/{admin.id}/profiles")
    assert r.status_code == 200 and len(r.json()) == 1
    assert (await admin_client.delete(
        f"/api/users/{admin.id}/profiles/{tid}")).status_code == 409


@pytest.mark.asyncio
async def test_member_cannot_use_admin_profile_endpoints(member_client, session):
    uid = (await session.exec(select(User).where(User.username == "member"))).first().id
    assert (await member_client.get(f"/api/users/{uid}/profiles")).status_code == 403
    assert (await member_client.delete(f"/api/users/{uid}/profiles/x")).status_code == 403
    assert (await member_client.get("/api/profiles")).status_code == 200


async def _profile_row(session, uid, tid):
    vol = profile_volume_name(uid, tid)
    session.add(UserProfile(user_id=uid, template_id=tid, volume_name=vol))
    await session.commit()
    return vol


@pytest.mark.asyncio
async def test_reset_blocked_by_stopped_instance(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    vol = await _profile_row(session, admin.id, tid)
    inst = Instance(template_id=tid, owner_id=admin.id, name="stp", subdomain="stp",
                    status="stopped", profile_volume=vol)
    session.add(inst)
    await session.commit()
    r = await admin_client.delete(f"/api/profiles/{tid}")
    assert r.status_code == 409
    assert "delete that instance first" in r.json()["detail"]
    await session.delete(inst)
    await session.commit()
    assert (await admin_client.delete(f"/api/profiles/{tid}")).status_code == 204


@pytest.mark.asyncio
async def test_template_delete_purges_profiles(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    vol = await _profile_row(session, admin.id, tid)
    assert (await admin_client.delete(f"/api/templates/{tid}")).status_code == 204
    shared_docker.remove_volume.assert_called_once_with(vol)
    assert (await session.exec(select(UserProfile))).all() == []


@pytest.mark.asyncio
async def test_template_delete_409_when_profile_referenced(admin_client, session, tid, shared_docker):
    admin = await _admin(session)
    vol = await _profile_row(session, admin.id, tid)
    session.add(Instance(template_id=tid, owner_id=admin.id, name="ref", subdomain="ref",
                         status="stopped", profile_volume=vol))
    await session.commit()
    r = await admin_client.delete(f"/api/templates/{tid}")
    assert r.status_code == 409
    assert "still used by an instance" in r.json()["detail"] and "ref" not in r.json()["detail"]
    shared_docker.remove_volume.assert_not_called()


@pytest.mark.asyncio
async def test_user_delete_purges_profiles(admin_client, session, tid, shared_docker):
    uid = (await session.exec(select(User).where(User.username == "admin"))).first().id
    other = User(username="victim", email="v@example.com", password_hash="x", role="member")
    session.add(other)
    await session.commit()
    await session.refresh(other)
    vol = await _profile_row(session, other.id, tid)
    r = await admin_client.delete(f"/api/users/{other.id}")
    assert r.status_code == 200, r.text
    shared_docker.remove_volume.assert_called_once_with(vol)
    assert (await session.exec(select(UserProfile))).all() == []
    assert uid


@pytest.mark.asyncio
async def test_member_template_delete_spares_other_users_profiles(member_client, session, shared_docker):
    r = await member_client.post("/api/templates", json={**TMPL, "name": "mine-tmpl"})
    assert r.status_code in (200, 201), r.text
    mtid = r.json()["id"]
    other = User(username="other", email="o@example.com", password_hash="x", role="member")
    session.add(other)
    await session.commit()
    await session.refresh(other)
    await _profile_row(session, other.id, mtid)          # someone else's profile
    r = await member_client.delete(f"/api/templates/{mtid}")
    assert r.status_code == 409 and "ask an admin" in r.json()["detail"]
    shared_docker.remove_volume.assert_not_called()
    assert len((await session.exec(select(UserProfile))).all()) == 1


@pytest.mark.asyncio
async def test_profile_falls_back_to_first_volume(admin_client, shared_docker):
    t = await admin_client.post("/api/templates", json={**TMPL, "name": "fb", "profile_mount": None})
    r = await _create(admin_client, t.json()["id"], "fb", use_profile=True)
    assert r.status_code == 201, r.text
    assert r.json()["profile_volume"]


async def _profiled(session, tid, name):
    admin = await _admin(session)
    vol = profile_volume_name(admin.id, tid)
    session.add(UserProfile(user_id=admin.id, template_id=tid, volume_name=vol))
    inst = Instance(template_id=tid, owner_id=admin.id, name=name, subdomain=name,
                    status="stopped", volume_names=[], profile_volume=vol)
    session.add(inst)
    await session.commit()
    return inst, vol


@pytest.mark.asyncio
async def test_delete_with_flag_removes_profile(admin_client, session, tid, shared_docker):
    inst, vol = await _profiled(session, tid, "dp1")
    r = await admin_client.delete(f"/api/instances/{inst.id}?delete_profile=true")
    assert r.status_code == 204
    shared_docker.remove_volume.assert_called_once_with(vol)
    assert (await session.exec(select(UserProfile))).first() is None


@pytest.mark.asyncio
async def test_delete_with_flag_keeps_profile_if_referenced(admin_client, session, tid, shared_docker):
    inst, vol = await _profiled(session, tid, "dp2")
    admin = await _admin(session)
    session.add(Instance(template_id=tid, owner_id=admin.id, name="dp3", subdomain="dp3",
                         status="stopped", volume_names=[], profile_volume=vol))
    await session.commit()
    r = await admin_client.delete(f"/api/instances/{inst.id}?delete_profile=true")
    assert r.status_code == 204
    assert (await session.exec(select(UserProfile))).first() is not None


@pytest.mark.asyncio
async def test_delete_without_flag_keeps_profile(admin_client, session, tid, shared_docker):
    inst, _ = await _profiled(session, tid, "dp4")
    assert (await admin_client.delete(f"/api/instances/{inst.id}")).status_code == 204
    assert (await session.exec(select(UserProfile))).first() is not None
