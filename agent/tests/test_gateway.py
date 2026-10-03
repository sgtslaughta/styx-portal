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
async def test_ws_proxy_does_not_negotiate_compression(tmp_path):
    """H264 frames are already compressed; permessage-deflate would re-DEFLATE
    every frame in Python (latency + CPU). The client must not be granted it."""
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    app = gateway.create_app("styx", "pw",
                             upstream_port=up.server.port)
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", compress=15,
            headers={"Authorization": _basic("styx", "pw")})
        assert "Sec-WebSocket-Extensions" not in ws._response.headers
        await ws.close()
    finally:
        await client.close()
        await up.close()


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
    upstream.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()
    app = gateway.create_app("styx", "pw",
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
    upstream.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    app = gateway.create_app("styx", "pw",
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
        await ws.send_bytes(b"\x01\x00opus")   # audio is binary too, NOT video
        await send_frame.wait()          # stay frameless until told
        await ws.send_bytes(b"\x00frame")
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    state = tmp_path / "gw_state.json"
    app = gateway.create_app("styx", "pw",
                             upstream_port=up.server.port, state_file=str(state))
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.receive()               # audio arrives...
        await asyncio.sleep(0.1)
        st = json.loads(state.read_text())
        assert st["stream_starving"] is True   # ...but viewer still starving
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
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    upstream = web.Application()
    upstream.router.add_get("/", lambda r: web.Response(
        text="<html><head><title>x</title></head><body>dash</body></html>",
        content_type="text/html"))
    up = TestClient(TestServer(upstream))
    await up.start_server()
    app = gateway.create_app("styx", "pw", upstream_port=up.server.port)
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
        await up.close()


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
    upstream.router.add_get("/api/websockets", upstream_ws)
    upstream_client = TestClient(TestServer(upstream))
    await upstream_client.start_server()
    upstream_port = upstream_client.server.port

    state = tmp_path / "gw_state.json"
    app = gateway.create_app("styx", "pw",
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


@pytest.mark.asyncio
async def test_ws_proxy_rearms_starving_when_input_gets_no_frames(tmp_path,
                                                                 monkeypatch):
    """A session that streamed fine and then went frameless *while the user is
    still driving it* is wedged, not idle: wlroots can exhaust its output buffer
    slots (screencopy holds them all), the compositor stops rendering and the
    engine emits nothing while happily reporting "capture started". Input with
    no frames behind it re-arms the starvation flag so the supervisor restarts
    the engine. A static screen with no input must never trip it."""
    import asyncio
    import json
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    monkeypatch.setattr(gateway, "STALL_REARM_S", 0.05)

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_bytes(b"\x00frame")      # healthy start, then silence
        async for _ in ws:
            pass
        return ws

    upstream = web.Application()
    upstream.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(upstream))
    await up.start_server()

    state = tmp_path / "gw_state.json"
    app = gateway.create_app("styx", "pw",
                             upstream_port=up.server.port, state_file=str(state))
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        ws = await client.ws_connect(
            "/websocket", headers={"Authorization": _basic("styx", "pw")})
        await ws.receive()                     # first frame -> not starving
        await asyncio.sleep(0.1)
        assert json.loads(state.read_text())["stream_starving"] is False

        # Protocol chatter alone must not re-arm (it is not user activity).
        await ws.send_str("CLIENT_FRAME_ACK")
        await asyncio.sleep(0.1)
        assert json.loads(state.read_text())["stream_starving"] is False

        # Real input, no frames behind it -> wedged.
        await ws.send_str("m2,100,100")
        await asyncio.sleep(0.1)
        st = json.loads(state.read_text())
        assert st["stream_starving"] is True
        assert st["starving_since"] >= st["last_input_ts"] - 1
    finally:
        await client.close()
        await up.close()


async def _upstream_app():
    from aiohttp import web
    app = web.Application()
    page = "<html><head><title>Selkies</title></head><body>x</body></html>"
    app.router.add_get("/", lambda r: web.Response(text=page, content_type="text/html"))
    app.router.add_get("/assets/app.js", lambda r: web.Response(text="js();",
                                                                content_type="text/javascript"))

    async def echo_post(request):
        return web.Response(text=f"got {len(await request.read())}")
    app.router.add_post("/api/upload", echo_post)

    async def ws(request):
        w = web.WebSocketResponse()
        await w.prepare(request)
        await w.send_bytes(b"\x04\x11frame")
        async for _ in w:
            pass
        return w
    app.router.add_get("/api/websockets", ws)
    return app


@pytest.mark.asyncio
async def test_single_upstream_index_assets_api_and_ws(tmp_path):
    from aiohttp.test_utils import TestClient, TestServer
    up = TestClient(TestServer(await _upstream_app()))
    await up.start_server()
    app = gateway.create_app("styx", "pw", upstream_port=up.server.port,
                             cursor_workaround=True)
    c = TestClient(TestServer(app))
    await c.start_server()
    h = {"Authorization": _basic("styx", "pw")}
    try:
        html = await (await c.get("/", headers=h)).text()
        assert "cursor:none" in html                       # cursor workaround injected
        assert (await (await c.get("/assets/app.js", headers=h)).text()) == "js();"
        r = await c.post("/api/upload", data=b"12345", headers=h)
        assert (await r.text()) == "got 5"
        for path in ("/api/websockets", "/websockets", "/websocket"):
            ws = await c.ws_connect(path, headers=h)
            msg = await ws.receive()
            assert msg.data == b"\x04\x11frame"
            await ws.close()
        assert (await c.get("/assets/app.js")).status == 401  # auth on proxied paths
    finally:
        await c.close()
        await up.close()


@pytest.mark.asyncio
async def test_ws_proxy_upstream_down_returns_502():
    from aiohttp.test_utils import TestClient, TestServer
    app = gateway.create_app("styx", "pw", upstream_port=1)   # nothing listens on :1
    c = TestClient(TestServer(app))
    await c.start_server()
    try:
        r = await c.get("/api/websockets", headers={"Authorization": _basic("styx", "pw"),
                                                    "Upgrade": "websocket",
                                                    "Connection": "Upgrade",
                                                    "Sec-WebSocket-Version": "13",
                                                    "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})
        assert r.status == 502
        assert (await c.get("/", headers={"Authorization": _basic("styx", "pw")})).status == 502
    finally:
        await c.close()


def test_inject_cursor_hide():
    html = "<html><head></head><body></body></html>"
    assert gateway.inject_cursor_hide(html, False) == html
    out = gateway.inject_cursor_hide(html, True)
    assert "cursor:none !important" in out and out.index("cursor:none") < out.index("</head>")
