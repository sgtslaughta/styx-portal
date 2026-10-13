"""F: discovered containers join a dedicated styx-services network (Traefik only)."""
from unittest.mock import MagicMock, call, patch

import docker
import pytest

from app.services.docker_manager import DockerManager
from tests import test_services_api as _api

_docker_body = _api._docker_body
docker_mock = _api.docker_mock          # shared fixtures
no_route_write = _api.no_route_write

NET = "styx-services"


def test_ensure_traefik_network_creates_and_attaches_traefik():
    with patch("app.services.docker_manager.docker.DockerClient") as cls:
        client = MagicMock()
        cls.return_value = client
        client.networks.get.side_effect = docker.errors.NotFound("x")
        net = MagicMock()
        client.networks.create.return_value = net
        DockerManager().ensure_traefik_network(NET)
        client.networks.create.assert_called_once_with(NET, driver="bridge")
        net.connect.assert_called_once_with("styx-traefik")


def test_compose_traefik_joins_services_network_backend_does_not():
    import pathlib
    import yaml
    compose = yaml.safe_load((pathlib.Path(__file__).parents[2] / "docker-compose.yml").read_text())
    assert compose["networks"][NET]["name"] == NET
    assert compose["networks"][NET].get("external", False) is False
    for t in ("traefik", "traefik-direct"):
        assert NET in compose["services"][t]["networks"]
    for other in ("backend", "frontend", "cloudflared", "docker-proxy"):
        assert NET not in compose["services"][other].get("networks", [])


@pytest.mark.asyncio
async def test_docker_local_attaches_to_services_network(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_docker_body())
    assert r.status_code == 201, r.text
    docker_mock.ensure_traefik_network.assert_called_with(NET)
    docker_mock.connect_to_network.assert_called_once_with("sonarr", NET)


@pytest.mark.asyncio
async def test_update_to_other_container_disconnects_previous(admin_client, docker_mock):
    docker_mock.list_containers.return_value.append(
        {"name": "radarr", "image": "radarr", "ports": [7878], "networks": []})
    sid = (await admin_client.post("/api/services", json=_docker_body())).json()["id"]
    r = await admin_client.put(f"/api/services/{sid}", json=_docker_body() | {"container": "radarr"})
    assert r.status_code == 200, r.text
    docker_mock.disconnect_from_network.assert_called_once_with("sonarr", NET)


@pytest.mark.asyncio
async def test_update_keeps_previous_if_shared(admin_client, docker_mock):
    docker_mock.list_containers.return_value.append(
        {"name": "radarr", "image": "radarr", "ports": [7878], "networks": []})
    sid = (await admin_client.post("/api/services", json=_docker_body())).json()["id"]
    await admin_client.post("/api/services", json=_docker_body() | {"slug": "sonarr2", "name": "S2"})
    await admin_client.put(f"/api/services/{sid}", json=_docker_body() | {"container": "radarr"})
    docker_mock.disconnect_from_network.assert_not_called()


@pytest.mark.asyncio
async def test_update_to_url_kind_disconnects_previous(admin_client, docker_mock):
    sid = (await admin_client.post("/api/services", json=_docker_body())).json()["id"]
    body = _docker_body() | {"kind": "url", "upstream_url": "http://10.0.0.2:8989"}
    await admin_client.put(f"/api/services/{sid}", json=body)
    assert docker_mock.disconnect_from_network.call_args_list == [call("sonarr", NET)]


@pytest.mark.asyncio
async def test_delete_disconnects_only_when_unreferenced(admin_client, docker_mock):
    a = (await admin_client.post("/api/services", json=_docker_body())).json()["id"]
    b_body = _docker_body() | {"slug": "s2", "name": "S2"}
    b = (await admin_client.post("/api/services", json=b_body)).json()["id"]
    assert (await admin_client.delete(f"/api/services/{a}")).status_code == 204
    docker_mock.disconnect_from_network.assert_not_called()
    assert (await admin_client.delete(f"/api/services/{b}")).status_code == 204
    docker_mock.disconnect_from_network.assert_called_once_with("sonarr", NET)
