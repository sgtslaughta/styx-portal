from unittest.mock import MagicMock, patch

import pytest


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
async def template_id(client):
    resp = await client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_instance(client, template_id):
    resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "My Dev Box", "subdomain": "dev"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Dev Box"
    assert data["subdomain"] == "dev"
    assert data["status"] == "pulling"


@pytest.mark.asyncio
async def test_create_instance_bad_template(client):
    resp = await client.post(
        "/api/instances",
        json={"template_id": "nonexistent", "name": "fail", "subdomain": "fail"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_instances(client, template_id):
    await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "inst1", "subdomain": "inst1"},
    )
    resp = await client.get("/api/instances")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_stop_instance(client, template_id):
    create_resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "s", "subdomain": "s"},
    )
    instance_id = create_resp.json()["id"]
    resp = await client.post(f"/api/instances/{instance_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


@pytest.mark.asyncio
async def test_start_stopped_instance(client, template_id):
    create_resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "r", "subdomain": "r"},
    )
    instance_id = create_resp.json()["id"]
    await client.post(f"/api/instances/{instance_id}/stop")
    resp = await client.post(f"/api/instances/{instance_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


@pytest.mark.asyncio
async def test_delete_instance(client, template_id):
    create_resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "d", "subdomain": "d"},
    )
    instance_id = create_resp.json()["id"]
    resp = await client.delete(f"/api/instances/{instance_id}?remove_volumes=true")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_get_instance_status(client, template_id):
    create_resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "st", "subdomain": "st"},
    )
    instance_id = create_resp.json()["id"]
    resp = await client.get(f"/api/instances/{instance_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pulling"


@pytest.mark.asyncio
async def test_keepalive(client, template_id):
    create_resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "ka", "subdomain": "ka"},
    )
    instance_id = create_resp.json()["id"]
    resp = await client.post(f"/api/instances/{instance_id}/keepalive")
    assert resp.status_code == 200
    assert resp.json()["last_activity"] is not None


@pytest.mark.asyncio
async def test_duplicate_subdomain(client, template_id):
    await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "a", "subdomain": "same"},
    )
    resp = await client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "b", "subdomain": "same"},
    )
    assert resp.status_code == 409
