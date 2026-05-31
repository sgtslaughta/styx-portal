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
async def test_capture_writes_png(monkeypatch):
    png_bytes = b"\x89PNG" + b"x" * 200

    page = AsyncMock()
    page.screenshot.return_value = png_bytes
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))

        result = await svc.capture("instance-123", "container-abc", 3001)

        assert result is True
        page.goto.assert_awaited_once()
        url = page.goto.call_args.args[0]
        assert url == "https://172.18.0.5:3001/"
        cached = Path(tmpdir) / "instance-123.png"
        assert cached.read_bytes() == png_bytes


@pytest.mark.asyncio
async def test_capture_uses_protocol_arg(monkeypatch):
    page = AsyncMock()
    page.screenshot.return_value = b"\x89PNG" + b"x" * 200
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.6")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))

        await svc.capture("inst-http", "cont", 3000, "http")

        assert page.goto.call_args.args[0] == "http://172.18.0.6:3000/"


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
