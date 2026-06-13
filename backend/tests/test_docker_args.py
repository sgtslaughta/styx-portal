import pytest
from app.services.docker_args import validate_extra_args, DockerArgError


def test_allows_safe_kwargs():
    out = validate_extra_args({"hostname": "box", "init": True}, is_admin=True)
    assert out == {"hostname": "box", "init": True}


def test_rejects_host_network_for_everyone():
    with pytest.raises(DockerArgError):
        validate_extra_args({"network_mode": "host"}, is_admin=True)


def test_rejects_raw_port_publish():
    with pytest.raises(DockerArgError):
        validate_extra_args({"ports": {"80/tcp": 8080}}, is_admin=True)


def test_rejects_host_bind_mount():
    with pytest.raises(DockerArgError):
        validate_extra_args({"binds": ["/etc:/etc"]}, is_admin=True)


def test_sysctls_rejected_for_everyone():
    """sysctls is blocked by denylist at launch; rejected for everyone."""
    with pytest.raises(DockerArgError):
        validate_extra_args({"sysctls": {"net.x": "1"}}, is_admin=False)
    with pytest.raises(DockerArgError):
        validate_extra_args({"sysctls": {"net.x": "1"}}, is_admin=True)


def test_unknown_kwarg_rejected():
    with pytest.raises(DockerArgError):
        validate_extra_args({"made_up_kwarg": 1}, is_admin=True)


def test_labels_cannot_override_traefik():
    with pytest.raises(DockerArgError):
        validate_extra_args({"labels": {"traefik.enable": "false"}}, is_admin=True)


def test_empty_returns_empty():
    assert validate_extra_args({}, is_admin=False) == {}
