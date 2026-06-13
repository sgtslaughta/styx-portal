from unittest.mock import MagicMock, patch
import pytest
import docker
import docker.errors
from app.services.docker_manager import DockerManager


@pytest.fixture
def mock_docker():
    with patch("app.services.docker_manager.docker.DockerClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        manager = DockerManager(network_name="styx-portal")
        yield manager, client


def test_restart_policy_and_flags_passed(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "cid"
    client.images.get.return_value = True
    client.containers.get.side_effect = docker.errors.NotFound("x")
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="selkies-x",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        restart_policy="unless-stopped",
        read_only_rootfs=True,
        tmpfs=["/tmp"],
        extra_hosts={"db": "10.0.0.2"},
        ulimits=[{"name": "nofile", "soft": 1024, "hard": 2048}],
        devices=["/dev/ttyUSB0:/dev/ttyUSB0"],
        entrypoint=["/bin/sh"],
        command=["-c", "sleep 1"],
        extra_docker_args={"hostname": "box"},
    )

    created = client.containers.create.call_args.kwargs
    assert created["restart_policy"] == {"Name": "unless-stopped", "MaximumRetryCount": 0}
    assert created["read_only"] is True
    assert created["tmpfs"] == {"/tmp": ""}
    assert created["extra_hosts"] == {"db": "10.0.0.2"}
    assert "/dev/ttyUSB0:/dev/ttyUSB0" in created["devices"]
    assert created["entrypoint"] == ["/bin/sh"]
    assert created["command"] == ["-c", "sleep 1"]
    assert created["hostname"] == "box"
    assert len(created["ulimits"]) == 1


def test_restart_policy_no_is_omitted(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "cid"
    client.images.get.return_value = True
    client.containers.get.side_effect = docker.errors.NotFound("x")
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="selkies-x",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        restart_policy="no",
    )

    created = client.containers.create.call_args.kwargs
    assert "restart_policy" not in created


def test_privileged_flag_passed(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "cid"
    client.images.get.return_value = True
    client.containers.get.side_effect = docker.errors.NotFound("x")
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="selkies-x",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        privileged=True,
    )

    created = client.containers.create.call_args.kwargs
    assert created["privileged"] is True


def test_devices_merged_with_gpu(mock_docker):
    """GPU devices should be merged with custom devices, not overwritten."""
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "cid"
    client.images.get.return_value = True
    client.containers.get.side_effect = docker.errors.NotFound("x")
    client.containers.create.return_value = mock_container

    with patch("app.services.docker_manager.detect_gpu",
               return_value={"available": True, "type": "intel/amd", "devices": ["/dev/dri/renderD128"]}):
        with patch("app.services.docker_manager.Path") as mock_path:
            mock_path.return_value.exists.return_value = True
            manager.create_container(
                name="selkies-x",
                image="img",
                labels={},
                environment={},
                volumes={},
                port=3001,
                gpu_enabled=True,
                devices=["/dev/ttyUSB0:/dev/ttyUSB0"],
            )

    created = client.containers.create.call_args.kwargs
    assert "/dev/dri:/dev/dri" in created["devices"]
    assert "/dev/ttyUSB0:/dev/ttyUSB0" in created["devices"]
    assert len(created["devices"]) == 2
