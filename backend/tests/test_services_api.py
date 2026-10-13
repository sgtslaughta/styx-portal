from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from app.main import app
from app.models import AuditLog, ProxiedService
from app.routers import services as services_router
from app.schemas import RESERVED_SERVICE_SLUGS


@pytest.fixture
def docker_mock():
    m = MagicMock()
    m.connect_to_network.return_value = True
    m.list_containers.return_value = [
        {"name": "sonarr", "image": "lscr.io/linuxserver/sonarr:latest", "ports": [8989],
         "networks": ["bridge"]},
        {"name": "random", "image": "nginx:1.27", "ports": [80], "networks": ["bridge"]},
    ]
    app.dependency_overrides[services_router.get_docker_manager] = lambda: m
    yield m
    app.dependency_overrides.pop(services_router.get_docker_manager, None)


@pytest.fixture(autouse=True)
def no_route_write(monkeypatch):
    calls = []

    async def fake(session):
        calls.append(1)
    monkeypatch.setattr("app.services.route_writer.refresh_routes_from_db", fake)
    return calls


def _body(**kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "mount_mode": "path", "auth_mode": "sso"}
    d.update(kw)
    return d


def _docker_body(**kw):
    return _body(kind="docker-local", upstream_url=None, container="sonarr",
                 container_port=8989, **kw)


async def _actions(session):
    return [a.action for a in (await session.exec(select(AuditLog))).all()]


@pytest.mark.asyncio
async def test_crud_and_routes_refresh(admin_client, docker_mock, no_route_write, session):
    r = await admin_client.post("/api/services", json=_body())
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert len(no_route_write) == 1
    r = await admin_client.post("/api/services", json=_body())
    assert r.status_code == 409
    r = await admin_client.put(f"/api/services/{sid}", json=_body(name="Sonarr TV"))
    assert r.status_code == 200 and r.json()["name"] == "Sonarr TV"
    r = await admin_client.post(f"/api/services/{sid}/disable")
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = await admin_client.post(f"/api/services/{sid}/enable")
    assert r.json()["enabled"] is True
    r = await admin_client.delete(f"/api/services/{sid}")
    assert r.status_code == 204
    assert len(no_route_write) == 5
    acts = await _actions(session)
    for a in ("service.create", "service.update", "service.disable", "service.enable",
              "service.delete"):
        assert a in acts


@pytest.mark.asyncio
async def test_missing_service_404(admin_client, docker_mock):
    assert (await admin_client.put("/api/services/nope", json=_body())).status_code == 404
    assert (await admin_client.delete("/api/services/nope")).status_code == 404
    assert (await admin_client.post("/api/services/nope/enable")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", sorted(RESERVED_SERVICE_SLUGS) + [
    "API", "../etc", "a/b", "a..b", "%2e%2e", ".", "..", "a b", "", "x" * 64])
async def test_bad_slug_rejected(admin_client, docker_mock, slug):
    r = await admin_client.post("/api/services", json=_body(slug=slug))
    assert r.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "javascript:alert(1)", "ftp://x/y", "unix:///var/run/docker.sock",
    "http://user:pw@10.0.0.2:8989", "https://:pw@host", "http://u@host", "//host", "http://",
    "http://host\n.evil", "gopher://x"])
async def test_bad_upstream_url_rejected(admin_client, docker_mock, url):
    r = await admin_client.post("/api/services", json=_body(upstream_url=url))
    assert r.status_code == 422, url
    sid = (await admin_client.post("/api/services", json=_body())).json()["id"]
    r = await admin_client.put(f"/api/services/{sid}", json=_body(upstream_url=url))
    assert r.status_code == 422, url


@pytest.mark.asyncio
async def test_docker_local_connects_network(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_docker_body())
    assert r.status_code == 201, r.text
    docker_mock.connect_to_network.assert_called_once_with("sonarr")
    assert r.json()["upstream_fallback"] is None


@pytest.mark.asyncio
async def test_docker_local_fallback_when_connect_fails(admin_client, docker_mock):
    docker_mock.connect_to_network.return_value = False
    r = await admin_client.post("/api/services", json=_docker_body())
    assert r.status_code == 201
    assert r.json()["upstream_fallback"] == "http://host.docker.internal:8989"


@pytest.mark.asyncio
async def test_docker_local_undiscovered_container_rejected(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_docker_body() | {"container": "styx-db"})
    assert r.status_code == 400
    docker_mock.connect_to_network.assert_not_called()
    sid = (await admin_client.post("/api/services", json=_docker_body())).json()["id"]
    docker_mock.connect_to_network.reset_mock()
    r = await admin_client.put(f"/api/services/{sid}",
                               json=_docker_body() | {"container": "ghost"})
    assert r.status_code == 400
    docker_mock.connect_to_network.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["a/b", "x y", "sonarr:80@evil", "../x", "a\nb", "-x"])
async def test_docker_local_bad_container_name_422(admin_client, docker_mock, name):
    r = await admin_client.post("/api/services", json=_docker_body() | {"container": name})
    assert r.status_code == 422
    docker_mock.connect_to_network.assert_not_called()


@pytest.mark.asyncio
async def test_member_list_filtered_by_group(member_client, session):
    # admin_client and member_client share one client; seed rows directly
    for slug, groups, enabled in [("sonarr", [], True), ("radarr", ["ops"], True),
                                  ("off", [], False)]:
        session.add(ProxiedService(slug=slug, name=slug, upstream_url="http://h:1",
                                   allowed_groups=groups, enabled=enabled))
    await session.commit()
    r = await member_client.get("/api/services")
    assert [s["slug"] for s in r.json()] == ["sonarr"]


@pytest.mark.asyncio
async def test_non_admin_forbidden_everywhere(admin_client, member_client, docker_mock):
    # admin_client and member_client share one client object; last login (member) wins
    r = await member_client.post("/api/services", json=_body(slug="x"))
    assert r.status_code == 403
    for method, path in [("put", "/api/services/x"), ("post", "/api/services/x/enable"),
                         ("post", "/api/services/x/disable"),
                         ("delete", "/api/services/x"), ("get", "/api/services/discover")]:
        kw = {"json": _body()} if method == "put" else {}
        r = await getattr(member_client, method)(path, **kw)
        assert r.status_code == 403, (method, path)
    docker_mock.list_containers.assert_not_called()
    docker_mock.connect_to_network.assert_not_called()


@pytest.mark.asyncio
async def test_anonymous_unauthorized(client, docker_mock):
    for method, path in [("post", "/api/services"), ("put", "/api/services/x"),
                         ("post", "/api/services/x/enable"), ("post", "/api/services/x/disable"),
                         ("delete", "/api/services/x"), ("get", "/api/services/discover"),
                         ("get", "/api/services"), ("get", "/api/services/presets")]:
        kw = {"json": _body()} if method in ("post", "put") and path == "/api/services" else {}
        r = await getattr(client, method)(path, **kw)
        assert r.status_code in (401, 403), (method, path, r.status_code)
    for path in ("/api/services/discover", "/api/services", "/api/services/presets"):
        assert (await client.get(path)).status_code == 401
    docker_mock.list_containers.assert_not_called()
    docker_mock.connect_to_network.assert_not_called()


@pytest.mark.asyncio
async def test_presets_and_discover(admin_client, docker_mock, session):
    from app.database import seed_service_presets
    import os
    await seed_service_presets(session, os.path.join(
        os.path.dirname(__file__), "..", "..", "templates", "services"))
    r = await admin_client.get("/api/services/presets")
    assert any(p["id"] == "sonarr" for p in r.json())
    r = await admin_client.get("/api/services/discover")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    assert by_name["sonarr"]["suggested_preset"] == "sonarr"
    assert by_name["random"]["suggested_preset"] is None
