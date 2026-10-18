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


async def test_context_fenced_by_dead_proxy_and_launch_args(monkeypatch):
    """Network-level fence: only the instance ip:port bypasses a dead proxy."""
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
        proxy = browser.new_context.await_args.kwargs["proxy"]
        assert proxy == {"server": "http://127.0.0.1:9", "bypass": "172.18.0.5:3001"}

        svc2 = ScreenshotService(cache_dir=d, docker_manager=MagicMock())
        pw = MagicMock()
        pw.chromium.launch = AsyncMock()
        svc2._pw = pw
        await svc2._ensure_browser()
        kw = pw.chromium.launch.await_args.kwargs
        assert kw["proxy"] == {"server": "http://per-context"}
        for a in ("--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
                  "--webrtc-ip-handling-policy=disable_non_proxied_udp",
                  "--dns-prefetch-disable", "--disable-features=NetworkPrediction"):
            assert a in kw["args"]


async def test_real_browser_cannot_reach_forbidden_server():
    """Real Chromium: instance on one loopback port, forbidden target on another."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import pytest

    hits: list[str] = []

    class Forbidden(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(b"x")
        log_message = lambda *a: None  # noqa: E731

    forb = HTTPServer(("127.0.0.1", 0), Forbidden)
    fport = forb.server_port

    class Instance(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/redir":
                self.send_response(302)
                self.send_header("Location", f"http://127.0.0.1:{fport}/redir-hit")
                self.end_headers()
                return
            body = (f"<script>fetch('http://127.0.0.1:{fport}/fetch-hit').catch(()=>0);"
                    f"fetch('/redir').catch(()=>0)</script>"
                    f"<img src='http://127.0.0.1:{fport}/img-hit'>").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)
        log_message = lambda *a: None  # noqa: E731

    inst = HTTPServer(("127.0.0.1", 0), Instance)
    for s in (forb, inst):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as d:
        svc = ScreenshotService(cache_dir=d, docker_manager=MagicMock())
        try:
            await svc._ensure_browser()
        except Exception:
            pytest.skip("chromium not available")
        try:
            # Fence only (no route handler): the network level must hold on its own.
            ctx = await svc._browser.new_context(
                proxy={"server": "http://127.0.0.1:9", "bypass": f"127.0.0.1:{inst.server_port}"})
            page = await ctx.new_page()
            await page.goto(f"http://127.0.0.1:{inst.server_port}/", wait_until="load")
            await page.wait_for_timeout(1500)
            await ctx.close()
        finally:
            await svc.close()
            forb.shutdown()
            inst.shutdown()
    assert hits == []
