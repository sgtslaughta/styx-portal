from unittest.mock import MagicMock, patch

import httpx
import pytest
from sqlmodel import select

from app.models import Group, Instance, User, UserGroup
from app.routers.instances import _launch_instance_background
from tests.test_k8s_instances import NS, Rec

QUOTA = f"/api/v1/namespaces/{NS}/resourcequotas/instances"


def _quota(hard, used):
    return httpx.Response(200, json={"status": {
        "hard": {"requests.amd.com/gpu": hard}, "used": {"requests.amd.com/gpu": used}}})


@pytest.mark.parametrize("hard,used,n,expect", [("3", "3", 1, False), ("3", "2", 1, True),
                                                ("3", "2", 2, False)])
def test_k8s_gpu_free_math(hard, used, n, expect):
    rec = Rec({("GET", QUOTA): _quota(hard, used)})
    assert rec.runtime().gpu_free(n) is expect


def test_k8s_gpu_free_no_quota_or_key():
    assert Rec({("GET", QUOTA): httpx.Response(404, json={})}).runtime().gpu_free(1) is True
    r = httpx.Response(200, json={"status": {"hard": {"requests.cpu": "1"}, "used": {}}})
    assert Rec({("GET", QUOTA): r}).runtime().gpu_free(1) is True


def test_docker_gpu_free():
    from app.services.docker_manager import DockerManager
    assert DockerManager.gpu_free(MagicMock(), 5) is True


GTMPL = {"name": "gpu-t", "display_name": "G", "image": "i:1", "internal_port": 3001,
         "gpu_enabled": True, "gpu_count": 1}


@pytest.fixture
def shared_docker():
    from app.main import app
    from app.routers.instances import get_docker_manager
    m = MagicMock()
    m.create_volume.side_effect = lambda name, size=None: name
    m.create_container.return_value = "c"
    m.get_container_status.return_value = {"status": "running"}
    m.gpu_free.return_value = True
    app.dependency_overrides[get_docker_manager] = lambda: m
    yield m


async def _mk(c, **kw):
    r = await c.post("/api/templates", json={**GTMPL, **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _inst(c, tid, sub, **kw):
    r = await c.post("/api/instances", json={"template_id": tid, "name": sub, "subdomain": sub, **kw})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.asyncio
async def test_admin_gets_gpu(admin_client, shared_docker):
    tid = await _mk(admin_client)
    assert (await _inst(admin_client, tid, "g1"))["gpu"] is True
    assert (await _inst(admin_client, tid, "g2", use_gpu=False))["gpu"] is False
    tid2 = await _mk(admin_client, name="cpu-t", gpu_enabled=False, gpu_count=0)
    assert (await _inst(admin_client, tid2, "g3"))["gpu"] is False


@pytest.mark.asyncio
async def test_member_needs_allow_gpu_group(member_client, session, shared_docker):
    from app.models import ServiceTemplate
    t = ServiceTemplate(**GTMPL)
    session.add(t)
    await session.commit()
    member = (await session.exec(select(User).where(User.username == "member"))).first()
    assert (await member_client.get("/api/auth/me")).json()["can_use_gpu"] is False
    assert (await _inst(member_client, t.id, "m1"))["gpu"] is False
    g = Group(name="gpu", allow_gpu=True)
    session.add(g)
    await session.commit()
    session.add(UserGroup(user_id=member.id, group_id=g.id))
    await session.commit()
    assert (await _inst(member_client, t.id, "m2"))["gpu"] is True
    assert (await member_client.get("/api/auth/me")).json()["can_use_gpu"] is True


@pytest.mark.asyncio
async def test_group_patch_member_forbidden(member_client, session):
    g = Group(name="g1")
    session.add(g)
    await session.commit()
    assert (await member_client.patch(f"/api/groups/{g.id}", json={"allow_gpu": True})).status_code == 403


@pytest.mark.asyncio
async def test_group_patch_admin(admin_client, session):
    g = Group(name="g2")
    session.add(g)
    await session.commit()
    r = await admin_client.patch(f"/api/groups/{g.id}", json={"allow_gpu": True, "description": "d"})
    assert r.status_code == 200 and r.json()["allow_gpu"] is True and r.json()["description"] == "d"
    assert (await admin_client.patch("/api/groups/nope", json={"allow_gpu": True})).status_code == 404
    assert (await admin_client.get("/api/auth/me")).json()["can_use_gpu"] is True


async def _launch(session, tid, gpu, free, owner="admin"):
    u = (await session.exec(select(User).where(User.username == owner))).first()
    sub = f"l{len((await session.exec(select(Instance))).all())}"
    inst = Instance(template_id=tid, owner_id=u.id if u else None, name=sub, subdomain=sub,
                    status="starting", gpu=gpu)
    session.add(inst)
    await session.commit()
    await session.refresh(inst)
    mgr = MagicMock()
    mgr.create_volume.side_effect = lambda name, size=None: name
    mgr.create_container.return_value = "c1"
    mgr.image_exists.return_value = True
    mgr.get_image_info.return_value = {"size_mb": 1}
    mgr.gpu_free.return_value = free

    class Ctx:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            pass

    with patch("app.routers.instances.instance_runtime", return_value=mgr), \
            patch("app.routers.instances.async_session", lambda: Ctx()):
        await _launch_instance_background(inst.id, tid)
    await session.refresh(inst)
    return mgr, inst


@pytest.mark.asyncio
async def test_launch_falls_back_to_cpu_with_notice(admin_client, session):
    tid = await _mk(admin_client)
    mgr, inst = await _launch(session, tid, True, False)
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is False
    assert inst.notice == "No GPU free, running on CPU"


@pytest.mark.asyncio
async def test_launch_uses_gpu_when_free_and_legacy_none(admin_client, session):
    tid = await _mk(admin_client)
    mgr, inst = await _launch(session, tid, True, True)
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is True
    assert inst.notice is None
    mgr, inst = await _launch(session, tid, None, True)   # legacy -> template.gpu_enabled
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is True
    mgr, inst = await _launch(session, tid, False, True)
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is False


@pytest.mark.asyncio
async def test_gpu_rechecked_at_start(admin_client, member_client, session):
    """A stored gpu=True never outlives the owner's permission or template support."""
    tid = await _mk(admin_client)
    mgr, _ = await _launch(session, tid, True, True, owner="member")   # no allow_gpu group
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is False
    mgr, _ = await _launch(session, tid, True, True, owner="nobody")   # ownerless
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is False
    from app.models import ServiceTemplate
    t = await session.get(ServiceTemplate, tid)
    t.gpu_enabled = False
    session.add(t)
    await session.commit()
    mgr, _ = await _launch(session, tid, True, True)                   # template no longer GPU
    assert mgr.create_container.call_args.kwargs["gpu_enabled"] is False
