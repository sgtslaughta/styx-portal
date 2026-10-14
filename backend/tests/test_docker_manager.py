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


def _probe(client, out: bytes = b"  HTTP/1.1 200 OK\n"):
    c = MagicMock()
    c.logs.return_value = out
    client.containers.create.return_value = c
    return c


def test_probe_http_runs_hardened_container_and_parses_status(mock_docker):
    manager, client = mock_docker
    c = _probe(client, b"  HTTP/1.1 200 OK\n")
    assert manager.probe_http("http://sonarr:8989/sonarr/ping", "styx-services",
                              extra_hosts={"h": "host-gateway"}) == 200
    args, kw = client.containers.create.call_args
    assert args[0] == "busybox:1.36"
    assert args[1] == ["wget", "-q", "-S", "-O", "/dev/null", "-T", "5", "http://sonarr:8989/sonarr/ping"]
    assert kw["network"] == "styx-services" and kw["read_only"] is True
    assert kw["cap_drop"] == ["ALL"] and kw["mem_limit"] == "32m"
    assert kw["user"] == "65534:65534"
    assert kw["pids_limit"] == 32 and kw["security_opt"] == ["no-new-privileges"]
    assert kw["labels"] == {"styx.probe": "true"} and kw["extra_hosts"] == {"h": "host-gateway"}
    c.remove.assert_called_once_with(force=True)


def test_probe_http_404_and_failure(mock_docker):
    manager, client = mock_docker
    _probe(client, b"  HTTP/1.1 404 Not Found\n")
    assert manager.probe_http("http://a:1/", "n") == 404
    _probe(client, b"wget: bad address 'a'\n")
    assert manager.probe_http("http://a:1/", "n") == 0


def test_probe_http_removes_container_on_exception(mock_docker):
    manager, client = mock_docker
    c = _probe(client)
    c.wait.side_effect = RuntimeError("timeout")
    assert manager.probe_http("http://a:1/", "n") == 0
    c.remove.assert_called_once_with(force=True)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "http://a;rm -rf /", "http://a b/", "http://a`x`/"])
def test_probe_http_rejects_bad_urls(mock_docker, url):
    with pytest.raises(ValueError):
        mock_docker[0].probe_http(url, "n")


def test_probe_http_redirect_counts_by_first_status(mock_docker):
    manager, client = mock_docker
    _probe(client, b"  HTTP/1.1 302 Found\n  HTTP/1.1 500 Oops\n")
    assert manager.probe_http("http://a:1/", "n") == 302


def test_probe_http_pull_failure_returns_minus_one(mock_docker):
    manager, client = mock_docker
    client.images.get.side_effect = docker.errors.ImageNotFound("nope")
    client.images.pull.side_effect = docker.errors.APIError("registry down")
    assert manager.probe_http("http://a:1/", "n") == -1
    client.containers.create.assert_not_called()


def test_probe_http_start_failure_returns_minus_one_and_removes(mock_docker):
    manager, client = mock_docker
    c = _probe(client)
    c.start.side_effect = RuntimeError("no start")
    assert manager.probe_http("http://a:1/", "n") == -1
    c.remove.assert_called_once_with(force=True)


def test_remove_probe_containers(mock_docker):
    manager, client = mock_docker
    a, b = MagicMock(), MagicMock()
    client.containers.list.return_value = [a, b]
    assert manager.remove_probe_containers() == 2
    client.containers.list.assert_called_once_with(all=True, filters={"label": "styx.probe=true"})
    a.remove.assert_called_once_with(force=True)


def test_probe_fetch_hardened_no_shell_interpolation(mock_docker):
    import base64
    manager, client = mock_docker
    c = _fetch(client, base64.encodebytes(b"PNGDATA" * 20))
    assert manager.probe_fetch("http://app:80/x/", "styx-services", 1000) == b"PNGDATA" * 20
    args, kw = client.containers.create.call_args
    cmd = args[1]
    assert cmd[:2] == ["sh", "-c"] and "http://app:80/x/" not in cmd[2]
    assert "-S" in cmd[2] and "2>&1" not in cmd[2]
    assert cmd[3:] == ["probe", "http://app:80/x/", "5", "1000"]
    assert "$1" in cmd[2] and "base64" in cmd[2]
    assert kw["network"] == "styx-services" and kw["read_only"] is True
    assert kw["cap_drop"] == ["ALL"] and kw["user"] == "65534:65534"
    assert kw["security_opt"] == ["no-new-privileges"] and kw["labels"] == {"styx.probe": "true"}
    c.remove.assert_called_once_with(force=True)


def test_probe_fetch_failures_return_none(mock_docker):
    manager, client = mock_docker
    c = _probe(client, b"")
    assert manager.probe_fetch("http://a:1/", "n", 10) is None
    _probe(client, b"!!not base64!!")
    assert manager.probe_fetch("http://a:1/", "n", 10) is None
    c = _probe(client)
    c.wait.side_effect = RuntimeError("t")
    assert manager.probe_fetch("http://a:1/", "n", 10) is None
    c.remove.assert_called_once_with(force=True)
    with pytest.raises(ValueError):
        manager.probe_fetch("http://a;rm/", "n", 10)


def _fetch(client, body: bytes, headers: bytes = b""):
    c = MagicMock()
    c.logs.side_effect = lambda stdout=True, stderr=True, **kw: (
        body if stdout and not stderr else headers if stderr and not stdout else body + headers)
    client.containers.create.return_value = c
    return c


def _b64(b: bytes) -> bytes:
    import base64
    return base64.b64encode(b)


def _same(u):
    return u.startswith("http://app:80/")


def test_probe_fetch_cross_origin_redirect_discards_body(mock_docker):
    manager, client = mock_docker
    _fetch(client, _b64(b"secret"), b"  HTTP/1.1 302 Found\n  Location: http://169.254.169.254/x\n")
    assert manager.probe_fetch("http://app:80/a", "n", 100, allow_redirect_to=_same) is None


def test_probe_fetch_same_origin_relative_redirect_ok(mock_docker):
    manager, client = mock_docker
    _fetch(client, _b64(b"icon"), b"  HTTP/1.1 301 Moved\n  location: /b\n  HTTP/1.1 200 OK\n")
    assert manager.probe_fetch("http://app:80/a", "n", 100, allow_redirect_to=_same) == b"icon"


def test_probe_fetch_too_many_redirects(mock_docker):
    manager, client = mock_docker
    hdr = b"".join(b"  HTTP/1.1 302 Found\n  Location: /h%d\n" % i for i in range(4))
    _fetch(client, _b64(b"icon"), hdr)
    assert manager.probe_fetch("http://app:80/a", "n", 100, allow_redirect_to=_same) is None


def test_probe_fetch_ignores_location_in_stdout_body(mock_docker):
    manager, client = mock_docker
    body = b"Location: http://evil.test/\n"
    _fetch(client, _b64(body), b"  HTTP/1.1 200 OK\n")
    assert manager.probe_fetch("http://app:80/a", "n", 100, allow_redirect_to=_same) == body
    calls = [c.kwargs for c in client.containers.create.return_value.logs.call_args_list]
    assert {"stdout": True, "stderr": False} in calls and {"stdout": False, "stderr": True} in calls
