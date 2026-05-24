from unittest.mock import MagicMock, patch
import pytest
import docker.errors
from app.services.docker_manager import DockerManager


@pytest.fixture
def mock_docker():
    with patch("app.services.docker_manager.docker.DockerClient") as mock_cls:
        client = MagicMock()
        mock_cls.from_env.return_value = client
        manager = DockerManager(network_name="selkies-hub")
        yield manager, client


def test_create_container(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "container123"
    mock_container.status = "created"
    client.containers.create.return_value = mock_container

    container_id = manager.create_container(
        name="test-instance",
        image="ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
        labels={"traefik.enable": "true"},
        environment={"PUID": "1000"},
        volumes={"test-home": {"bind": "/config", "mode": "rw"}},
        port=3001,
        gpu_enabled=False,
    )

    assert container_id == "container123"
    client.containers.create.assert_called_once()
    call_kwargs = client.containers.create.call_args[1]
    assert call_kwargs["name"] == "test-instance"
    assert call_kwargs["image"] == "ghcr.io/linuxserver/baseimage-selkies:debiantrixie"
    assert call_kwargs["labels"]["traefik.enable"] == "true"


def test_start_container(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    client.containers.get.return_value = mock_container

    manager.start_container("container123")

    client.containers.get.assert_called_once_with("container123")
    mock_container.start.assert_called_once()


def test_stop_container(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    client.containers.get.return_value = mock_container

    manager.stop_container("container123")

    mock_container.stop.assert_called_once()


def test_remove_container(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    client.containers.get.return_value = mock_container

    manager.remove_container("container123")

    mock_container.remove.assert_called_once_with(force=True)


def test_get_container_status(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.status = "running"
    mock_container.attrs = {"State": {"StartedAt": "2026-05-24T10:00:00Z"}}
    client.containers.get.return_value = mock_container

    status = manager.get_container_status("container123")

    assert status["status"] == "running"
    assert "started_at" in status


def test_get_container_status_not_found(mock_docker):
    manager, client = mock_docker
    client.containers.get.side_effect = docker.errors.NotFound("not found")

    status = manager.get_container_status("missing")

    assert status["status"] == "not_found"


@patch("app.services.docker_manager.detect_gpu", return_value={"available": True, "type": "nvidia", "devices": ["/dev/dri/renderD128"]})
def test_create_container_with_gpu(mock_detect, mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "gpu-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="gpu-instance",
        image="test:latest",
        labels={},
        environment={},
        volumes={},
        port=3001,
        gpu_enabled=True,
        gpu_count=1,
    )

    call_kwargs = client.containers.create.call_args[1]
    device_requests = call_kwargs["device_requests"]
    assert len(device_requests) == 1
    assert device_requests[0].count == 1


def test_create_volume(mock_docker):
    manager, client = mock_docker
    mock_volume = MagicMock()
    mock_volume.name = "my-vol"
    client.volumes.create.return_value = mock_volume

    name = manager.create_volume("my-vol")

    assert name == "my-vol"
    client.volumes.create.assert_called_once_with(name="my-vol")


def test_remove_volume(mock_docker):
    manager, client = mock_docker
    mock_volume = MagicMock()
    client.volumes.get.return_value = mock_volume

    manager.remove_volume("my-vol")

    mock_volume.remove.assert_called_once()
