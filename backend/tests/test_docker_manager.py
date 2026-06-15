from unittest.mock import MagicMock, patch
import pytest
import docker.errors
from app.services.docker_manager import DockerManager


@pytest.fixture
def mock_docker():
    with patch("app.services.docker_manager.docker.DockerClient") as mock_cls:
        client = MagicMock()
        mock_cls.return_value = client
        manager = DockerManager(network_name="styx-portal")
        yield manager, client


def test_default_network_name():
    with patch("app.services.docker_manager.docker.DockerClient"):
        manager = DockerManager()
        assert manager._network_name == "styx-portal"


def test_manager_uses_configured_socket(monkeypatch):
    """Verify DockerManager respects base_url parameter from DOCKER_SOCKET setting.

    The client is created lazily (on first use), so realize it before asserting
    the configured base_url reached DockerClient."""
    captured = {}

    class FakeClient:
        def __init__(self, base_url=None):
            captured["url"] = base_url

    monkeypatch.setattr("app.services.docker_manager.docker.DockerClient", FakeClient)
    mgr = DockerManager(base_url="tcp://docker-proxy:2375")
    _ = mgr._client  # realize lazy client
    assert captured["url"] == "tcp://docker-proxy:2375"


def test_construction_does_not_connect_eagerly():
    """Regression: __init__ must not open the docker socket. CI runners and
    docker-down hosts have no /var/run/docker.sock; the failure must surface
    lazily via ping()/version() (which degrade gracefully), not as a
    constructor exception (which 500s diagnostics + setup-preflight)."""
    # Real DockerClient pointed at a guaranteed-absent socket. Before the lazy
    # fix this raised docker.errors.DockerException at construction time.
    dm = DockerManager(base_url="unix:///nonexistent/styx-test.sock")
    assert dm.ping() is False
    assert dm.version() is None


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


def test_create_container_dind(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "dind-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="dind-instance",
        image="selkies-desktop:latest",
        labels={},
        environment={"PUID": "1000"},
        volumes={"dind-store": {"bind": "/var/lib/docker", "mode": "rw"}},
        port=3001,
        dind=True,
        memory_limit="4g",
        cpu_limit="2",
    )

    call_kwargs = client.containers.create.call_args[1]
    assert call_kwargs["privileged"] is True
    assert call_kwargs["environment"]["START_DOCKER"] == "true"
    assert call_kwargs["volumes"]["dind-store"]["bind"] == "/var/lib/docker"


def test_default_container_is_confined(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "confined-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="n",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
    )

    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["privileged"] is False
    assert "sysctls" not in kwargs


def test_template_cap_add_and_security_opt_passthrough(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "custom-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="n",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        cap_add=["SYS_NICE"],
        security_opt=["seccomp=unconfined"],
    )

    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["cap_add"] == ["SYS_NICE"]
    assert "seccomp=unconfined" in kwargs["security_opt"]
    assert "no-new-privileges:true" in kwargs["security_opt"]


def test_dind_requires_memory_limit(mock_docker):
    manager, client = mock_docker

    with pytest.raises(ValueError, match="resource limits"):
        manager.create_container(
            name="n",
            image="img",
            labels={},
            environment={},
            volumes={},
            port=3001,
            dind=True,
            memory_limit=None,
        )


def test_dind_still_privileged_with_limits(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "dind-limited"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="n",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        dind=True,
        memory_limit="4g",
        cpu_limit="2",
    )

    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["privileged"] is True
    assert "cap_drop" not in kwargs


def test_cpu_limit_applied(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "cpu-limited"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="n",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        cpu_limit="1.5",
    )

    kwargs = client.containers.create.call_args.kwargs
    assert kwargs["nano_cpus"] == int(1.5e9)


def test_ensure_user_network_creates_and_attaches_traefik(mock_docker):
    manager, client = mock_docker
    mock_network = MagicMock()
    client.networks.get.side_effect = docker.errors.NotFound("x")
    client.networks.create.return_value = mock_network

    name = manager.ensure_user_network("user-1234567890ab-extra")

    assert name == "styx-u-user-1234567"
    client.networks.create.assert_called_once_with(name, driver="bridge")
    mock_network.connect.assert_called_once_with("styx-traefik")


def test_ensure_user_network_idempotent(mock_docker):
    manager, client = mock_docker
    mock_network = MagicMock()
    client.networks.get.return_value = mock_network

    manager.ensure_user_network("u1")

    client.networks.create.assert_not_called()
    # Even when the network already exists, traefik must be (re)attached — it may
    # have been recreated since the network was first made.
    mock_network.connect.assert_called_once_with("styx-traefik")


def test_ensure_user_network_tolerates_redundant_connect(mock_docker):
    manager, client = mock_docker
    mock_network = MagicMock()
    mock_network.connect.side_effect = docker.errors.APIError("already connected")
    client.networks.get.return_value = mock_network
    # must not raise when traefik is already on the network
    assert manager.ensure_user_network("u1") == "styx-u-u1"


def test_create_container_uses_network_override(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "net-override-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="n",
        image="img",
        labels={},
        environment={},
        volumes={},
        port=3001,
        network="styx-u-abc",
    )

    call_kwargs = client.containers.create.call_args.kwargs
    assert call_kwargs["network"] == "styx-u-abc"


def test_remove_user_network_tolerates_missing(mock_docker):
    manager, client = mock_docker
    client.networks.get.side_effect = docker.errors.NotFound("x")

    manager.remove_user_network("u1")

    client.networks.get.assert_called_once()
    client.networks.create.assert_not_called()


def test_ping_returns_true(mock_docker):
    manager, client = mock_docker
    client.ping.return_value = True
    assert manager.ping() is True


def test_ping_false_on_error(mock_docker):
    manager, client = mock_docker
    client.ping.side_effect = Exception("down")
    assert manager.ping() is False


def test_version_returns_string(mock_docker):
    manager, client = mock_docker
    client.version.return_value = {"Version": "29.5.2"}
    assert manager.version() == "29.5.2"


def test_version_none_on_error(mock_docker):
    manager, client = mock_docker
    client.version.side_effect = Exception("x")
    assert manager.version() is None

def test_pull_streaming_parses_tag_and_registry_port(mock_docker):
    manager, client = mock_docker
    client.api.pull.return_value = iter([])
    manager.pull_image_streaming("ghcr.io/foo/bar:debian")
    assert client.api.pull.call_args.args[0] == "ghcr.io/foo/bar"
    assert client.api.pull.call_args.kwargs["tag"] == "debian"

    client.api.pull.return_value = iter([])
    manager.pull_image_streaming("registry:5000/img")  # port, no tag
    assert client.api.pull.call_args.args[0] == "registry:5000/img"
    assert client.api.pull.call_args.kwargs["tag"] == "latest"

def test_create_container_removes_stale_same_name(mock_docker):
    manager, client = mock_docker
    client.images.get.return_value = object()  # image present, no pull
    stale = MagicMock()
    client.containers.get.return_value = stale  # a same-named orphan exists
    manager.create_container(name="selkies-chrome", image="img", labels={},
                             environment={}, volumes={}, port=3001)
    stale.remove.assert_called_once_with(force=True)
    client.containers.create.assert_called_once()


def test_create_container_no_stale_is_fine(mock_docker):
    import docker.errors
    manager, client = mock_docker
    client.images.get.return_value = object()
    client.containers.get.side_effect = docker.errors.NotFound("x")  # none exists
    manager.create_container(name="selkies-new", image="img", labels={},
                             environment={}, volumes={}, port=3001)
    client.containers.create.assert_called_once()
