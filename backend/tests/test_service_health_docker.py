"""docker-local health comes from the Docker API: the backend is not on styx-services."""
from unittest.mock import MagicMock, patch

import docker.errors
import pytest

from app.models import ProxiedService
from app.services.docker_manager import DockerManager
from app.services.service_health import run_health_pass


@pytest.fixture
def dm():
    with patch("app.services.docker_manager.docker.DockerClient") as cls:
        client = MagicMock()
        cls.return_value = client
        yield DockerManager(), client


def _container(status="running", health=None):
    c = MagicMock()
    c.status = status
    c.attrs = {"State": {"Status": status, **({"Health": {"Status": health}} if health else {})}}
    return c


@pytest.mark.parametrize("status,health,expected", [
    ("running", None, "healthy"),
    ("running", "healthy", "healthy"),
    ("running", "unhealthy", "unhealthy"),
    ("running", "starting", "unknown"),
    ("exited", None, "unhealthy"),
    ("exited", "healthy", "unhealthy"),
    ("paused", None, "unhealthy"),
])
def test_container_health_states(dm, status, health, expected):
    mgr, client = dm
    client.containers.get.return_value = _container(status, health)
    assert mgr.container_health("sonarr") == expected
    client.containers.get.assert_called_with("sonarr")


def test_container_health_not_found_is_down(dm):
    mgr, client = dm
    client.containers.get.side_effect = docker.errors.NotFound("nope")
    assert mgr.container_health("sonarr") == "unhealthy"


def test_container_health_docker_unreachable_is_unknown(dm):
    mgr, client = dm
    client.containers.get.side_effect = docker.errors.DockerException("socket gone")
    assert mgr.container_health("sonarr") == "unknown"


@pytest.mark.asyncio
async def test_docker_local_uses_docker_not_http(session):
    s = ProxiedService(slug="dl", name="DL", kind="docker-local", container="sonarr",
                       container_port=8989, health_path="/ping")
    nohp = ProxiedService(slug="np", name="NP", kind="docker-local", container="radarr",
                          container_port=7878)             # no health_path: still checked
    url = ProxiedService(slug="u", name="U", upstream_url="http://10.0.0.1", health_path="/h")
    for x in (s, nohp, url):
        session.add(x)
    await session.commit()
    seen = []

    async def fake(u, verify):
        seen.append(u)
        return "healthy"

    docker = MagicMock()
    docker.container_health.side_effect = {"sonarr": "unhealthy", "radarr": "healthy"}.get
    assert await run_health_pass(session, checker=fake, docker=docker) == 3
    assert seen == ["http://10.0.0.1/h"]
    for x in (s, nohp, url):
        await session.refresh(x)
    assert (s.health_status, nohp.health_status, url.health_status) == \
        ("unhealthy", "healthy", "healthy")


@pytest.mark.asyncio
async def test_docker_crash_is_unknown_and_isolated(session):
    s = ProxiedService(slug="dl", name="DL", kind="docker-local", container="sonarr",
                       container_port=8989)
    url = ProxiedService(slug="u", name="U", upstream_url="http://10.0.0.1", health_path="/h")
    session.add(s)
    session.add(url)
    await session.commit()

    async def fake(u, verify):
        return "healthy"

    docker = MagicMock()
    docker.container_health.side_effect = RuntimeError("boom")
    await run_health_pass(session, checker=fake, docker=docker)
    await session.refresh(s)
    await session.refresh(url)
    assert (s.health_status, url.health_status) == ("unknown", "healthy")
