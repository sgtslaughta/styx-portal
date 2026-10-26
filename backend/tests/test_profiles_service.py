from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlmodel import select

from app.models import Instance, ServiceTemplate, User, UserProfile
from app.services import profiles
from app.services.k8s_instance_objects import pvc


def _tmpl(**kw):
    base = dict(name="xfce", display_name="XFCE", image="i",
                volumes=[{"name": "{instance_id}-home", "mount": "/config"},
                         {"name": "{instance_id}-data", "mount": "/data"}],
                profile_mount="/config")
    base.update(kw)
    return ServiceTemplate(**base)


def test_name_deterministic_lowercase_short():
    a = profiles.profile_volume_name("U1", "Xfce_Desktop")
    assert a == profiles.profile_volume_name("U1", "Xfce_Desktop")
    assert a == a.lower() and len(a) <= 63 and a.startswith("profile-")
    assert len(profiles.profile_volume_name("u" * 40, "t" * 60)) <= 63


def test_mounts_for_swaps_profile_mount():
    t = _tmpl()
    inst = Instance(id="abc", template_id="t", name="n", subdomain="s", profile_volume="profile-u-xfce")
    assert profiles.mounts_for(t, inst) == [("abc-data", "/data"), ("profile-u-xfce", "/config")]


def test_mounts_for_without_profile_keeps_all():
    t = _tmpl()
    inst = Instance(id="abc", template_id="t", name="n", subdomain="s")
    assert profiles.mounts_for(t, inst) == [("abc-home", "/config"), ("abc-data", "/data")]


async def _seed(session):
    u = User(username="pu", password_hash="x", role="user")
    t = _tmpl()
    session.add_all([u, t])
    await session.commit()
    return u, t


@pytest.mark.asyncio
async def test_ensure_profile_upserts(session):
    u, t = await _seed(session)
    v1 = await profiles.ensure_profile(session, u.id, t)
    v2 = await profiles.ensure_profile(session, u.id, t)
    assert v1 == v2 == profiles.profile_volume_name(u.id, t.name)
    rows = (await session.exec(select(UserProfile))).all()
    assert len(rows) == 1 and rows[0].volume_name == v1


@pytest.mark.asyncio
async def test_in_use_excludes_self_and_stopped(session):
    u, t = await _seed(session)
    vol = await profiles.ensure_profile(session, u.id, t)
    a = Instance(template_id=t.id, owner_id=u.id, name="a", subdomain="a", status="running", profile_volume=vol)
    b = Instance(template_id=t.id, owner_id=u.id, name="b", subdomain="b", status="stopped", profile_volume=vol)
    session.add_all([a, b])
    await session.commit()
    assert (await profiles.profile_in_use(session, vol)).id == a.id
    assert await profiles.profile_in_use(session, vol, exclude_instance_id=a.id) is None


@pytest.mark.asyncio
async def test_delete_profile(session):
    u, t = await _seed(session)
    vol = await profiles.ensure_profile(session, u.id, t)
    rt = MagicMock()
    await profiles.delete_profile(session, rt, u.id, t.id)
    rt.remove_volume.assert_called_once_with(vol)
    assert (await session.exec(select(UserProfile))).first() is None
    with pytest.raises(HTTPException) as e:
        await profiles.delete_profile(session, rt, u.id, t.id)
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_profile_in_use_409_and_missing_volume_ok(session):
    u, t = await _seed(session)
    vol = await profiles.ensure_profile(session, u.id, t)
    session.add(Instance(template_id=t.id, owner_id=u.id, name="a", subdomain="a",
                         status="starting", profile_volume=vol))
    await session.commit()
    with pytest.raises(HTTPException) as e:
        await profiles.delete_profile(session, MagicMock(), u.id, t.id)
    assert e.value.status_code == 409


@pytest.mark.asyncio
async def test_delete_profile_ignores_runtime_not_found(session):
    u, t = await _seed(session)
    await profiles.ensure_profile(session, u.id, t)
    rt = MagicMock()
    rt.remove_volume.side_effect = RuntimeError("gone")
    await profiles.delete_profile(session, rt, u.id, t.id)
    assert (await session.exec(select(UserProfile))).first() is None


def test_pvc_size_override():
    assert pvc("n", "ns", size="5Gi")["spec"]["resources"]["requests"]["storage"] == "5Gi"
    assert pvc("n", "ns")["spec"]["resources"]["requests"]["storage"] == "20Gi"
