import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.screenshot import ScreenshotService


def _make_service(tmpdir, browser=None):
    svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
    if browser is not None:
        svc._browser = browser
    return svc


def test_screenshot_cache_dir_created():
    with tempfile.TemporaryDirectory() as tmpdir:
        ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert Path(tmpdir).is_dir()


def test_get_screenshot_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert svc.get_path("nonexistent") is None
        cached = Path(tmpdir) / "inst-1.png"
        cached.write_bytes(b"\x89PNG data")
        assert svc.get_path("inst-1") == cached


@pytest.mark.asyncio
async def test_capture_uses_shared_viewer_when_streaming(monkeypatch):
    """When a stream is live, capture uses the non-intrusive #shared mirror only."""
    png_bytes = b"\x89PNG" + b"x" * 200

    page = AsyncMock()
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))
        monkeypatch.setattr(svc, "_is_streaming", AsyncMock(return_value=True))
        monkeypatch.setattr(svc, "_shoot", AsyncMock(return_value=png_bytes))

        result = await svc.capture("instance-123", "container-abc", 3001)

        assert result is True
        # Only the #shared viewer is opened — no controller (plain) connection.
        urls = [c.args[0] for c in page.goto.await_args_list]
        assert urls == ["https://172.18.0.5:3001/#shared"]
        assert (Path(tmpdir) / "instance-123.png").read_bytes() == png_bytes


@pytest.mark.asyncio
async def test_capture_skips_and_never_connects_primary_when_no_stream(monkeypatch):
    """No live stream → skip (return False) and keep the prior cache. Must NEVER
    open a plain (primary/controller) connection that would steal a session."""
    page = AsyncMock()
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context
    shot = AsyncMock(return_value=b"\x89PNGnew")

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.6")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))
        monkeypatch.setattr(svc, "_is_streaming", AsyncMock(return_value=False))
        monkeypatch.setattr(svc, "_shoot", shot)
        stale = Path(tmpdir) / "inst-http.png"
        stale.write_bytes(b"OLD")

        result = await svc.capture("inst-http", "cont", 3000, "http")

        assert result is False
        # Only the view-only #shared URL is ever opened — no primary connection.
        urls = [c.args[0] for c in page.goto.await_args_list]
        assert urls == ["http://172.18.0.6:3000/#shared"]
        shot.assert_not_awaited()
        assert stale.read_bytes() == b"OLD"


def test_secure_endpoint_prefers_3001():
    docker = MagicMock()
    container = MagicMock()
    container.attrs = {"Config": {"ExposedPorts": {"3000/tcp": {}, "3001/tcp": {}}}}
    docker._client.containers.get.return_value = container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=docker)
        # KasmVNC image exposes 3001 → upgrade to https:3001 despite http:3000 config
        assert svc._secure_endpoint("cid", 3000, "http") == ("https", 3001)


def test_secure_endpoint_falls_back_without_3001():
    docker = MagicMock()
    container = MagicMock()
    container.attrs = {"Config": {"ExposedPorts": {"8080/tcp": {}}}}
    docker._client.containers.get.return_value = container

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=docker)
        assert svc._secure_endpoint("cid", 8080, "http") == ("http", 8080)


@pytest.mark.asyncio
async def test_capture_joins_then_leaves_isolated_network(monkeypatch):
    """Instances sit on per-user isolated networks the backend isn't on; capture
    must attach the backend container for the shot and detach afterwards, without
    touching networks it already belongs to (e.g. styx-portal)."""
    docker = MagicMock()
    inst_c = MagicMock()
    inst_c.attrs = {"NetworkSettings": {"Networks": {"styx-u-abc": {}}}}
    self_c = MagicMock()
    self_c.attrs = {"NetworkSettings": {"Networks": {"styx-portal": {}}}}
    docker._client.containers.get.side_effect = (
        lambda cid: inst_c if cid == "cont" else self_c
    )
    net = MagicMock()
    docker._client.networks.get.return_value = net

    page = AsyncMock()
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=docker)
        svc._browser = browser
        monkeypatch.setattr(svc, "_self_container_id", lambda: "selfid")
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.22.0.3")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))
        monkeypatch.setattr(svc, "_is_streaming", AsyncMock(return_value=True))
        monkeypatch.setattr(svc, "_shoot", AsyncMock(return_value=b"\x89PNGxx"))

        result = await svc.capture("inst-1", "cont", 3001)

    assert result is True
    docker._client.networks.get.assert_called_with("styx-u-abc")
    net.connect.assert_called_once_with("selfid")
    net.disconnect.assert_called_once_with("selfid")


@pytest.mark.asyncio
async def test_capture_no_ip_returns_false(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: None)
        result = await svc.capture("inst-1", "cont-1", 3001)
        assert result is False


@pytest.mark.asyncio
async def test_capture_keeps_previous_on_failure(monkeypatch):
    context = AsyncMock()
    context.new_page.side_effect = Exception("render boom")
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        stale = Path(tmpdir) / "inst-1.png"
        stale.write_bytes(b"OLD")

        result = await svc.capture("inst-1", "cont-1", 3001)

        assert result is False
        assert stale.read_bytes() == b"OLD"
