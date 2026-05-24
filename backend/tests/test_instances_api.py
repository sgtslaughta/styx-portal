from unittest.mock import MagicMock

import pytest

from app.main import app
from app.routers.instances import get_docker_manager


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


@pytest.fixture(autouse=True)
def mock_docker_manager():
    manager = MagicMock()
    manager.create_volume.side_effect = lambda name: name
    manager.create_container.return_value = "container-abc123"
    app.dependency_overrides[get_docker_manager] = lambda: manager
    yield manager
    app.dependency_overrides.pop(get_docker_manager, None)


@pytest.fixture
def template_id(client):
    resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    return resp.json()["id"]


def test_create_instance(client, template_id, mock_docker_manager):
    resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "My Dev Box", "subdomain": "dev"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Dev Box"
    assert data["subdomain"] == "dev"
    assert data["status"] == "running"
    assert data["container_id"] == "container-abc123"
    mock_docker_manager.create_container.assert_called_once()
    mock_docker_manager.start_container.assert_called_once_with("container-abc123")


def test_create_instance_bad_template(client):
    resp = client.post(
        "/api/instances",
        json={"template_id": "nonexistent", "name": "fail", "subdomain": "fail"},
    )
    assert resp.status_code == 404


def test_list_instances(client, template_id):
    client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "inst1", "subdomain": "inst1"},
    )
    resp = client.get("/api/instances")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_stop_instance(client, template_id, mock_docker_manager):
    create_resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "s", "subdomain": "s"},
    )
    instance_id = create_resp.json()["id"]
    resp = client.post(f"/api/instances/{instance_id}/stop")
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"
    mock_docker_manager.stop_container.assert_called_once()


def test_start_stopped_instance(client, template_id, mock_docker_manager):
    create_resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "r", "subdomain": "r"},
    )
    instance_id = create_resp.json()["id"]
    client.post(f"/api/instances/{instance_id}/stop")
    resp = client.post(f"/api/instances/{instance_id}/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_delete_instance(client, template_id, mock_docker_manager):
    create_resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "d", "subdomain": "d"},
    )
    instance_id = create_resp.json()["id"]
    resp = client.delete(f"/api/instances/{instance_id}?remove_volumes=true")
    assert resp.status_code == 204
    mock_docker_manager.remove_container.assert_called_once()
    mock_docker_manager.remove_volume.assert_called()


def test_get_instance_status(client, template_id, mock_docker_manager):
    mock_docker_manager.get_container_status.return_value = {
        "status": "running",
        "started_at": "2026-05-24T10:00:00Z",
    }
    create_resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "st", "subdomain": "st"},
    )
    instance_id = create_resp.json()["id"]
    resp = client.get(f"/api/instances/{instance_id}/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_keepalive(client, template_id):
    create_resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "ka", "subdomain": "ka"},
    )
    instance_id = create_resp.json()["id"]
    resp = client.post(f"/api/instances/{instance_id}/keepalive")
    assert resp.status_code == 200
    assert resp.json()["last_activity"] is not None


def test_duplicate_subdomain(client, template_id):
    client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "a", "subdomain": "same"},
    )
    resp = client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "b", "subdomain": "same"},
    )
    assert resp.status_code == 409
