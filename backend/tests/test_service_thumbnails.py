"""Task B: proxied-service thumbnails (capture_url jail, GET route, capture pass, cleanup)."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models import ProxiedService
from app.routers.services import get_thumb_dir
from app.main import app
from app.services.screenshot import ScreenshotService
from tests import test_services_api as _api

docker_mock = _api.docker_mock
no_route_write = _api.no_route_write
PNG = b"\x89PNG" + b"x" * 50


def _svc(d, page=None):
    context = AsyncMock()
    context.new_page.return_value = page or AsyncMock()
    browser = AsyncMock()
    browser.new_context.return_value = context
    s = ScreenshotService(cache_dir=d, docker_manager=MagicMock())
    s._browser = browser
    s._ensure_browser = AsyncMock()
    return s, browser, context


async def test_capture_url_jails_to_target_and_saves():
    page = AsyncMock()
    page.screenshot.return_value = PNG
    with tempfile.TemporaryDirectory() as d:
        s, browser, context = _svc(d, page)
        assert await s.capture_url("abc", "http://sonarr.lan:8989/ui") is True
        assert (Path(d) / "svc-abc.png").read_bytes() == PNG
        kw = browser.new_context.await_args.kwargs
        assert kw["service_workers"] == "block"
        assert kw["viewport"] == {"width": 1280, "height": 800}
        assert kw["proxy"] == {"server": "http://127.0.0.1:9", "bypass": "sonarr.lan:8989"}
        assert page.goto.await_args.args[0] == "http://sonarr.lan:8989/ui"
        _, handler = context.route.await_args.args
        foreign, own = AsyncMock(), AsyncMock()
        foreign.request.url = "http://docker-proxy:2375/x"
        own.request.url = "http://sonarr.lan:8989/app.js"
        await handler(foreign)
        await handler(own)
        foreign.abort.assert_awaited()
        own.fulfill.assert_awaited()
        context.close.assert_awaited()


async def test_capture_url_default_port_and_failure():
    with tempfile.TemporaryDirectory() as d:
        s, browser, _ = _svc(d)
        s._browser.new_context.side_effect = RuntimeError("boom")
        assert await s.capture_url("x", "https://app.example.com") is False
        assert not (Path(d) / "svc-x.png").exists()
        s2, browser2, _ = _svc(d)
        await s2.capture_url("y", "https://app.example.com")
        assert browser2.new_context.await_args.kwargs["proxy"]["bypass"] == "app.example.com:443"


async def test_capture_services_pass_skips_disabled(session):
    from app.services.screenshot_url import capture_services_pass
    session.add(ProxiedService(slug="a", name="A", upstream_url="http://10.0.0.2:80/"))
    session.add(ProxiedService(slug="b", name="B", upstream_url="http://10.0.0.3", enabled=False))
    session.add(ProxiedService(slug="c", name="C", kind="docker-local", container="c1",
                               container_port=80))
    await session.commit()
    shots = MagicMock()
    shots.capture_url = AsyncMock(return_value=True)
    await capture_services_pass(session, shots)
    urls = sorted(c.args[1] for c in shots.capture_url.await_args_list)
    assert urls == ["http://10.0.0.2:80", "http://c1:80"]


@pytest.fixture
def thumb_dir(client):
    with tempfile.TemporaryDirectory() as d:
        app.dependency_overrides[get_thumb_dir] = lambda: Path(d)
        yield Path(d)


async def _mk(session, **kw):
    s = ProxiedService(slug="sonarr", name="S", upstream_url="http://10.0.0.2", **kw)
    session.add(s)
    await session.commit()
    return s


async def test_thumbnail_route_ok_and_404(admin_client, session, thumb_dir):
    s = await _mk(session)
    r = await admin_client.get(f"/api/services/{s.id}/thumbnail")
    assert r.status_code == 404
    (thumb_dir / f"svc-{s.id}.png").write_bytes(PNG)
    r = await admin_client.get(f"/api/services/{s.id}/thumbnail")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.content == PNG
    assert (await admin_client.get("/api/services/nope/thumbnail")).status_code == 404


async def test_thumbnail_route_group_acl(member_client, session, thumb_dir):
    s = await _mk(session, allowed_groups=["media"])
    (thumb_dir / f"svc-{s.id}.png").write_bytes(PNG)
    assert (await member_client.get(f"/api/services/{s.id}/thumbnail")).status_code == 404
    open_s = ProxiedService(slug="open", name="O", upstream_url="http://10.0.0.4")
    session.add(open_s)
    await session.commit()
    (thumb_dir / f"svc-{open_s.id}.png").write_bytes(PNG)
    assert (await member_client.get(f"/api/services/{open_s.id}/thumbnail")).status_code == 200


async def test_thumbnail_requires_login(client, session, thumb_dir):
    s = await _mk(session)
    assert (await client.get(f"/api/services/{s.id}/thumbnail")).status_code in (401, 403)


async def test_delete_service_removes_thumbnail(admin_client, session, thumb_dir, docker_mock,
                                                no_route_write):
    s = await _mk(session)
    f = thumb_dir / f"svc-{s.id}.png"
    f.write_bytes(PNG)
    assert (await admin_client.delete(f"/api/services/{s.id}")).status_code == 204
    assert not f.exists()
