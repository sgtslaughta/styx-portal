from unittest.mock import MagicMock

import pytest

from app.models import Instance, ProxiedService, PulledImage, ServiceTemplate, User
from app.services import service_favicon
from app.services.k8s_instances import K8sInstanceRuntime
from tests.test_service_icons_api import PNG


@pytest.fixture
def k8s(monkeypatch):
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    monkeypatch.setattr("app.services.k8s_instances.incluster_client", lambda: MagicMock())
    monkeypatch.setattr("app.services.k8s_runtime.incluster_client", lambda: MagicMock())


def test_images_router_uses_instance_runtime_on_k8s(k8s):
    from app.routers.images import get_docker_manager
    assert isinstance(get_docker_manager(), K8sInstanceRuntime)


@pytest.mark.asyncio
async def test_image_delete_and_purge_only_drop_rows_on_k8s(admin_client, session, k8s):
    session.add_all([PulledImage(image="a:1"), PulledImage(image="b:1")])
    await session.commit()
    first = (await admin_client.get("/api/images")).json()[0]["id"]
    assert (await admin_client.delete(f"/api/images/{first}")).status_code == 204
    assert (await admin_client.delete("/api/images")).status_code == 204
    assert (await admin_client.get("/api/images")).json() == []


@pytest.mark.asyncio
async def test_icon_refresh_uses_httpx_on_k8s(admin_client, session, k8s, monkeypatch):
    s = ProxiedService(slug="sonarr", name="Sonarr", kind="docker-local",
                       container="sonarr.media.svc", container_port=8989)
    session.add(s)
    await session.commit()
    seen = []

    async def fake_get(url, cap, verify, origin, transport, host=None):
        seen.append(url)
        if url.endswith("/sonarr/"):
            return b'<html><link rel="icon" href="i.png"></html>', url
        return PNG, url
    monkeypatch.setattr(service_favicon, "_get_httpx", fake_get)

    async def no_route(session, **kw):
        return None
    monkeypatch.setattr("app.services.route_writer.refresh_routes_from_db", no_route)
    r = await admin_client.post(f"/api/services/{s.id}/icon/refresh")
    assert r.status_code == 200, r.text
    assert seen and all("sonarr.media.svc" in u for u in seen)


@pytest.mark.asyncio
async def test_screenshots_degrade_cleanly_on_k8s(admin_client, session, k8s, tmp_path):
    from app.main import app
    from app.routers.instances import get_screenshot_service
    from app.services.docker_manager import DockerManager
    from app.services.screenshot import ScreenshotService
    app.dependency_overrides[get_screenshot_service] = lambda: ScreenshotService(
        cache_dir=str(tmp_path), docker_manager=DockerManager())
    admin = (await session.exec(__import__("sqlmodel").select(User).where(User.username == "admin"))).first()
    t = ServiceTemplate(name="t", display_name="T", image="x:1")
    session.add(t)
    await session.commit()
    inst = Instance(template_id=t.id, owner_id=admin.id, name="o", subdomain="o",
                    container_id="selkies-o", status="running")
    session.add(inst)
    await session.commit()
    assert (await admin_client.get(f"/api/instances/{inst.id}/screenshot")).status_code == 404
    r = await admin_client.post(f"/api/instances/{inst.id}/screenshot/refresh")
    assert r.status_code == 200 and r.json()["ok"] is False
