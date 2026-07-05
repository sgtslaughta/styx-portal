import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")


def _basic(user, pw):
    return "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()


def test_check_auth_accepts_valid_header():
    assert gateway.check_auth(_basic("styx", "pw"), "styx", "pw") is True


def test_check_auth_rejects_bad_password_and_garbage():
    assert gateway.check_auth(_basic("styx", "wrong"), "styx", "pw") is False
    assert gateway.check_auth("", "styx", "pw") is False
    assert gateway.check_auth("Bearer abc", "styx", "pw") is False
    assert gateway.check_auth("Basic !!notb64!!", "styx", "pw") is False


def test_inject_idle_watchdog_present_when_enabled():
    out = gateway.inject_idle_watchdog(
        "<head></head><body>x</body>", timeout_s=900, lead_s=60, enabled=True)
    assert "900" in out and "60" in out          # timeout + lead reach the script
    assert "<script>" in out
    assert out.index("<script>") < out.index("</head>")   # in <head>, pre-bundle


def test_inject_idle_watchdog_disabled_or_nonpositive_is_noop():
    html = "<head></head><body>x</body>"
    assert gateway.inject_idle_watchdog(html, 900, 60, enabled=False) == html
    assert gateway.inject_idle_watchdog(html, 0, 60, enabled=True) == html
    assert gateway.inject_idle_watchdog(html, -5, 60, enabled=True) == html


def test_inject_idle_watchdog_clamps_lead_below_half_timeout():
    # lead must never exceed timeout/2, else the warning outlives the timeout
    out = gateway.inject_idle_watchdog("<head></head>", timeout_s=100, lead_s=90,
                                       enabled=True)
    assert "LEAD=50" in out.replace(" ", "")       # 90 -> clamped to 100/2


def test_is_activity_excludes_protocol_and_telemetry():
    # Automated protocol/telemetry that must NOT reset the idle clock:
    assert gateway.is_activity("CLIENT_FRAME_ACK") is False     # per-frame ack (continuous)
    assert gateway.is_activity("START_AUDIO") is False
    assert gateway.is_activity("STOP_VIDEO") is False
    assert gateway.is_activity('SETTINGS,{"h264_crf":25}') is False
    assert gateway.is_activity("pong,1783193480.9") is False    # ping reply
    assert gateway.is_activity("_f,60") is False                # framerate stat (~5s)
    assert gateway.is_activity("_crf,25") is False
    # Real user input still counts:
    assert gateway.is_activity("m2,0,0,1") is True              # mouse
    assert gateway.is_activity("kd,65") is True                 # key (lowercase)
    assert gateway.is_activity("cw,hello") is True              # clipboard write
    assert gateway.is_activity("r,1920,1080") is True           # resize
    assert gateway.is_activity(b"\x01\x02") is True             # binary input


@pytest.mark.asyncio
async def test_ws_proxy_idle_close_ignores_pong_keepalive(tmp_path):
    """A steady pong keepalive must NOT keep an otherwise-idle session alive."""
    import asyncio
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/websocket", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()
    (tmp_path / "index.html").write_text("x")
    app = gateway.create_app(str(tmp_path), "styx", "pw",
                             upstream_port=up.server.port,
                             state_file=str(tmp_path / "s.json"),
                             idle_timeout_s=1, idle_enabled=True)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})

        async def spam_pong():
            for _ in range(20):
                await ws.send_str("pong,123")
                await asyncio.sleep(0.25)

        task = asyncio.ensure_future(spam_pong())
        msg = await asyncio.wait_for(ws.receive(), timeout=4)
        assert msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED)
        task.cancel()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_ws_proxy_closes_idle_connection(tmp_path):
    """Gateway is the idle authority: it closes the proxied stream socket once
    no client->server input has arrived for the timeout, no client JS needed."""
    import asyncio
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/websocket", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    (tmp_path / "index.html").write_text("x")
    app = gateway.create_app(str(tmp_path), "styx", "pw",
                             upstream_port=up.server.port,
                             state_file=str(tmp_path / "s.json"),
                             idle_timeout_s=1, idle_enabled=True)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})
        # no input sent -> gateway closes us for idleness within ~timeout+tick
        msg = await asyncio.wait_for(ws.receive(), timeout=4)
        assert msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED)
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_ws_proxy_starving_flag_clears_on_first_frame(tmp_path):
    """stream_starving is True while a viewer waits with no video, and clears
    the instant the engine sends its first binary frame — the signal the
    supervisor uses to restart a stuck (STOP_VIDEO) stream without killing a
    healthy static session."""
    import asyncio
    import json
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    send_frame = asyncio.Event()

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await send_frame.wait()          # stay frameless until told
        await ws.send_bytes(b"\x00frame")
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/websocket", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    (tmp_path / "index.html").write_text("x")
    state = tmp_path / "gw_state.json"
    app = gateway.create_app(str(tmp_path), "styx", "pw",
                             upstream_port=up.server.port, state_file=str(state))
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})
        await asyncio.sleep(0.1)
        st = json.loads(state.read_text())
        assert st["stream_starving"] is True
        assert isinstance(st["starving_since"], (int, float))
        # engine finally emits a frame -> flag clears
        send_frame.set()
        await ws.receive()               # pull the frame through the proxy
        await asyncio.sleep(0.1)
        assert json.loads(state.read_text())["stream_starving"] is False
        await ws.close()
        await asyncio.sleep(0.1)
        # no viewer -> not starving
        assert json.loads(state.read_text())["stream_starving"] is False
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_app_serves_static_with_auth(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    (tmp_path / "index.html").write_text("<html>dash</html>")
    app = gateway.create_app(str(tmp_path), "styx", "pw", upstream_port=1)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.get("/", headers={"Authorization": _basic("styx", "pw")})
        assert r.status == 200
        assert "dash" in await r.text()
        r = await client.get("/")
        assert r.status == 401
        assert r.headers["WWW-Authenticate"].startswith("Basic")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_ws_proxy_upstream_down_returns_502(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    (tmp_path / "index.html").write_text("x")
    app = gateway.create_app(str(tmp_path), "styx", "pw", upstream_port=1)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        r = await client.get("/websocket",
                             headers={"Authorization": _basic("styx", "pw")})
        assert r.status == 502
    finally:
        await client.close()


def test_inject_title_pins_hostname_in_head():
    out = gateway.inject_title("<head></head><body>x</body>", "ws-alice")
    assert '"ws-alice"' in out                      # JS string literal
    assert "document.title" in out
    assert out.index("<script>") < out.index("</head>")  # injected inside head


def test_inject_title_escapes_and_handles_no_head():
    out = gateway.inject_title("<body>x</body>", 'ev"il')
    assert '"ev\\"il"' in out                        # json-escaped, XSS-safe
    assert out.startswith("<script>")               # no </head> -> prepended


def test_inject_forces_stream_visible_then_restores():
    out = gateway.inject_title("<html><head></head><body></body></html>", "box1")
    # Lies at load so connect-while-hidden still sends START_VIDEO...
    assert "Object.defineProperty(document,'hidden'" in out
    assert "Object.defineProperty(document,'visibilityState'" in out
    # ...then restores native semantics so the client's hidden-tab frame
    # dropping and STOP_VIDEO work again (unbounded-queue slowdown fix).
    assert "delete document.hidden" in out
    assert "delete document.visibilityState" in out
    assert "new Event('visibilitychange')" in out
    assert "setTimeout" in out


@pytest.mark.asyncio
async def test_ws_proxy_counts_connections_in_state_file(tmp_path):
    """Occupancy source of truth: state file is 0 at start, 1 while a stream
    websocket is connected, 0 again after it closes. 502s never count."""
    import asyncio
    import json
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/websocket", upstream_ws)
    upstream_client = TestClient(TestServer(upstream))
    await upstream_client.start_server()
    upstream_port = upstream_client.server.port

    (tmp_path / "index.html").write_text("x")
    state = tmp_path / "gw_state.json"
    app = gateway.create_app(str(tmp_path), "styx", "pw",
                             upstream_port=upstream_port,
                             state_file=str(state))
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        assert json.loads(state.read_text())["active_connections"] == 0
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})
        await asyncio.sleep(0.1)
        assert json.loads(state.read_text())["active_connections"] == 1
        await ws.close()
        await asyncio.sleep(0.2)
        assert json.loads(state.read_text())["active_connections"] == 0
    finally:
        await client.close()
        await upstream_client.close()
