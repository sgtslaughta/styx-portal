"""B1: screenshot browser network jail."""
import tempfile
from unittest.mock import AsyncMock, MagicMock

from app.services.screenshot import ScreenshotService, _origin_allowed


# ---- B1 ---------------------------------------------------------------
def test_origin_allowed_only_instance():
    ok = lambda u: _origin_allowed(u, "172.18.0.5", 3001, "https")  # noqa: E731
    assert ok("https://172.18.0.5:3001/#shared")
    assert ok("wss://172.18.0.5:3001/websockets")
    assert ok("data:image/png;base64,AAAA")
    assert ok("blob:https://172.18.0.5:3001/abc")
    assert not ok("http://docker-proxy:2375/containers/x/kill")
    assert not ok("https://172.18.0.5:8000/")           # other port on same host
    assert not ok("http://172.18.0.5:3001/")             # scheme downgrade
    assert not ok("http://169.254.169.254/latest")
    assert not ok("https://172.18.0.6:3001/")
    assert not ok("https://172.18.0.5:3001@evil.test/")
    assert not ok("ftp://172.18.0.5:3001/")


async def test_capture_routes_block_foreign_and_no_service_workers(monkeypatch):
    page = AsyncMock()
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context
    with tempfile.TemporaryDirectory() as d:
        svc = ScreenshotService(cache_dir=d, docker_manager=MagicMock())
        svc._browser = browser
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))
        monkeypatch.setattr(svc, "_is_streaming", AsyncMock(return_value=False))
        await svc.capture("i", "c", 3001, "https")
    assert browser.new_context.await_args.kwargs["service_workers"] == "block"
    pattern, handler = context.route.await_args.args
    foreign, own = AsyncMock(), AsyncMock()
    foreign.request.url = "http://docker-proxy:2375/containers/styx-traefik/kill"
    own.request.url = "https://172.18.0.5:3001/app.js"
    await handler(foreign)
    await handler(own)
    foreign.abort.assert_awaited()
    foreign.fulfill.assert_not_awaited()
    own.fulfill.assert_awaited()
    own.abort.assert_not_awaited()




async def test_guard_fetches_without_redirects_and_fulfills(monkeypatch):
    """F1: a redirect hop must re-enter the handler, so never follow redirects inside it."""
    context = AsyncMock()
    context.new_page.return_value = AsyncMock()
    browser = AsyncMock()
    browser.new_context.return_value = context
    with tempfile.TemporaryDirectory() as d:
        svc = ScreenshotService(cache_dir=d, docker_manager=MagicMock())
        svc._browser = browser
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        monkeypatch.setattr(svc, "_secure_endpoint", lambda cid, p, proto: (proto, p))
        monkeypatch.setattr(svc, "_is_streaming", AsyncMock(return_value=False))
        await svc.capture("i", "c", 3001, "https")
    _, handler = context.route.await_args.args
    hop1, hop2 = AsyncMock(), AsyncMock()
    hop1.request.url = "https://172.18.0.5:3001/go"
    hop2.request.url = "http://docker-proxy:2375/containers/x/json"
    resp = MagicMock()
    hop1.fetch = AsyncMock(return_value=resp)
    await handler(hop1)  # 302 to hop2 is fulfilled as-is; the browser then asks for hop2
    hop1.fetch.assert_awaited_with(max_redirects=0)
    hop1.fulfill.assert_awaited_with(response=resp)
    await handler(hop2)
    hop2.abort.assert_awaited()
    hop2.fetch.assert_not_awaited()
