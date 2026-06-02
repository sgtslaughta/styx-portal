
from unittest.mock import AsyncMock

import pytest

from app.main import app
from app.models import Instance
from app.routers.instances import get_screenshot_service


TEMPLATE_PAYLOAD = {
    "name": "test-tmpl",
    "display_name": "Test Template",
    "image": "test:latest",
    "internal_port": 3001,
    "env_vars": {"PUID": "1000"},
    "volumes": [{"name": "{instance_id}-home", "mount": "/config"}],
    "session_config": {
        "idle_timeout": "30m",
        "grace_period": "5m",
        "timeout_action": "stop",
        "never_timeout": False,
        "max_session_duration": None,
    },
}


@pytest.fixture
async def template_id(admin_client):
    resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_instance(admin_client, template_id):
    resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "My Dev Box", "subdomain": "dev"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Dev Box"
    assert data["subdomain"] == "dev"
    assert data["status"] == "starting"


@pytest.mark.asyncio
async def test_create_instance_bad_template(admin_client):
    resp = await admin_client.post(
        "/api/instances",
        json={"template_id": "nonexistent", "name": "fail", "subdomain": "fail"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_instances(admin_client, template_id):
    await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "inst1", "subdomain": "inst1"},
    )
    resp = await admin_client.get("/api/instances")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_stop_instance(admin_client, template_id):
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "s", "subdomain": "s"},
    )
    instance_id = create_resp.json()["id"]
    resp = await admin_client.post(f"/api/instances/{instance_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_start_stopped_instance(admin_client, template_id):
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "r", "subdomain": "r"},
    )
    instance_id = create_resp.json()["id"]
    await admin_client.post(f"/api/instances/{instance_id}/stop")
    resp = await admin_client.post(f"/api/instances/{instance_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_delete_instance(admin_client, template_id):
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "d", "subdomain": "d"},
    )
    instance_id = create_resp.json()["id"]
    resp = await admin_client.delete(f"/api/instances/{instance_id}?remove_volumes=true")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_instance_status(admin_client, template_id):
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "st", "subdomain": "st"},
    )
    instance_id = create_resp.json()["id"]
    resp = await admin_client.get(f"/api/instances/{instance_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "starting"


@pytest.mark.asyncio
async def test_keepalive(admin_client, template_id):
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "ka", "subdomain": "ka"},
    )
    instance_id = create_resp.json()["id"]
    resp = await admin_client.post(f"/api/instances/{instance_id}/keepalive")
    assert resp.status_code == 200
    assert resp.json()["last_activity"] is not None


@pytest.mark.asyncio
async def test_duplicate_subdomain(admin_client, template_id):
    await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "a", "subdomain": "same"},
    )
    resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "b", "subdomain": "same"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_recreate_instance(admin_client, template_id, session):
    from app.models import Instance

    # Create instance
    create_resp = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "rec", "subdomain": "rec"},
    )
    instance_id = create_resp.json()["id"]

    # Get the template to check its volume count
    from app.models import ServiceTemplate
    template = await session.get(ServiceTemplate, template_id)
    expected_volume_count = len(template.volumes) if template else 0

    # Simulate the instance is running with a container
    instance = await session.get(Instance, instance_id)
    instance.status = "running"
    instance.container_id = "container-old-id"
    # Set initial volume_names to empty to simulate pre-setup state
    instance.volume_names = []
    session.add(instance)
    await session.commit()

    # POST to recreate endpoint
    resp = await admin_client.post(f"/api/instances/{instance_id}/recreate")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert len(data["volume_names"]) == expected_volume_count


async def _img_present(admin_client, image):
    resp = await admin_client.get("/api/images")
    return any(i["image"] == image for i in resp.json())


async def _template_present(admin_client, tid):
    resp = await admin_client.get("/api/templates")
    return any(t["id"] == tid for t in resp.json())


@pytest.mark.asyncio
async def test_delete_keeps_image_and_template_by_default(admin_client, session, template_id):
    from app.models import PulledImage

    r = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "k", "subdomain": "k"},
    )
    iid = r.json()["id"]
    session.add(PulledImage(image="test:latest"))
    await session.commit()

    resp = await admin_client.delete(f"/api/instances/{iid}")
    assert resp.status_code == 204
    assert await _img_present(admin_client, "test:latest"), "image must be kept unless remove_image=true"
    assert await _template_present(admin_client, template_id), "template must be kept by default"


@pytest.mark.asyncio
async def test_delete_removes_image_when_requested(admin_client, session, template_id):
    from app.models import PulledImage

    r = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "i", "subdomain": "i"},
    )
    iid = r.json()["id"]
    session.add(PulledImage(image="test:latest"))
    await session.commit()

    resp = await admin_client.delete(f"/api/instances/{iid}?remove_image=true")
    assert resp.status_code == 204
    assert not await _img_present(admin_client, "test:latest"), "image must be pruned when remove_image=true"


@pytest.mark.asyncio
async def test_delete_removes_template_when_requested(admin_client, template_id):
    r = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "t", "subdomain": "t"},
    )
    iid = r.json()["id"]

    resp = await admin_client.delete(f"/api/instances/{iid}?remove_template=true")
    assert resp.status_code == 204
    assert not await _template_present(admin_client, template_id), "template must be deleted when remove_template=true"


@pytest.mark.asyncio
async def test_refresh_screenshot_not_found(admin_client):
    resp = await admin_client.post("/api/instances/nope/screenshot/refresh")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_refresh_screenshot_not_running(admin_client, template_id):
    r = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "i", "subdomain": "ref1"},
    )
    iid = r.json()["id"]  # status "starting", no container

    resp = await admin_client.post(f"/api/instances/{iid}/screenshot/refresh")
    assert resp.status_code == 200
    assert resp.json() == {"ok": False, "reason": "not running"}


@pytest.mark.asyncio
async def test_refresh_screenshot_captures(admin_client, session, template_id):
    r = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "i2", "subdomain": "ref2"},
    )
    iid = r.json()["id"]
    inst = await session.get(Instance, iid)
    inst.status = "running"
    inst.container_id = "cid-1"
    session.add(inst)
    await session.commit()

    svc = AsyncMock()
    svc.capture.return_value = True
    app.dependency_overrides[get_screenshot_service] = lambda: svc
    try:
        resp = await admin_client.post(f"/api/instances/{iid}/screenshot/refresh")
    finally:
        app.dependency_overrides.pop(get_screenshot_service, None)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    svc.capture.assert_awaited_once()
    svc.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_launch_dind_instance_mounts_docker_store(admin_client, session):
    """Test that launching a dind=true template adds a dockerstore volume.
    Uses the recreate endpoint to trigger _build_and_start_container synchronously."""
    dind_template = {
        "name": "dind-desk",
        "display_name": "DinD Desk",
        "image": "selkies-desktop:latest",
        "internal_port": 3001,
        "dind": True,
    }
    tr = await admin_client.post("/api/templates", json=dind_template)
    assert tr.status_code == 201, tr.text
    template_id = tr.json()["id"]

    # Create instance (synchronously, just to set up DB state)
    from app.models import Instance
    instance = Instance(
        template_id=template_id,
        owner_id="test-user",
        name="dind-inst",
        subdomain="dind-inst",
        status="stopped",
        volume_names=[],  # Start empty; recreate will recompute them
    )
    session.add(instance)
    await session.commit()
    await session.refresh(instance)
    instance_id = instance.id

    # Call recreate endpoint, which synchronously calls _build_and_start_container
    # and should add the dockerstore volume
    resp = await admin_client.post(f"/api/instances/{instance_id}/recreate")
    assert resp.status_code == 200, resp.text

    # Verify dockerstore volume was added to instance.volume_names
    inst = await session.get(Instance, instance_id)
    assert inst.volume_names is not None
    assert any(v.endswith("-dockerstore") for v in inst.volume_names), \
        f"Expected dockerstore volume in {inst.volume_names}"
