"""Refit upgrade hold, keepalive, busy reason and client-stall helper."""
import asyncio
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")
from .test_gateway import _basic  # noqa: E402

HDR = {"Authorization": _basic("styx", "pw")}


async def _upstream(connects):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        connects.append(time.monotonic())
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws
    app = web.Application()
    app.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(app))
    await up.start_server()
    return up


async def _gw(up, **kw):
    from aiohttp.test_utils import TestClient, TestServer
    client = TestClient(TestServer(gateway.create_app(
        "styx", "pw", upstream_port=up.server.port, **kw)))
    await client.start_server()
    return client


@pytest.mark.asyncio
async def test_ws_upgrade_waits_while_refit_pending(tmp_path):
    connects = []
    up = await _upstream(connects)
    client = await _gw(up, seat_dir=str(tmp_path))
    req = tmp_path / "refit-request"
    req.write_text("2552x1294")
    try:
        t0 = time.monotonic()
        asyncio.get_running_loop().call_later(0.1, req.unlink)
        ws = await client.ws_connect("/websocket", headers=HDR)
        removed = t0 + 0.1
        assert connects and connects[0] >= removed - 0.01
        assert connects[0] - t0 < 2.0
        await ws.close()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_ws_upgrade_gives_up_waiting_after_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "REFIT_WAIT_S", 0.2)
    connects = []
    up = await _upstream(connects)
    client = await _gw(up, seat_dir=str(tmp_path))
    (tmp_path / "refit-request").write_text("2552x1294")
    try:
        ws = await client.ws_connect("/websocket", headers=HDR)
        assert len(connects) == 1
        await ws.close()
    finally:
        await client.close()
        await up.close()


def test_wait_constants():
    assert gateway.REFIT_WAIT_S == 5.0 and gateway.REFIT_POLL_S == 0.02


@pytest.mark.asyncio
async def test_busy_refusal_says_superseded(monkeypatch):
    monkeypatch.setattr(gateway, "CONNECT_QUIET_S", 0)
    up = await _upstream([])
    client = await _gw(up)
    try:
        a = await client.ws_connect("/websocket?styx_vid=A", headers=HDR)
        await a.send_str("m2,10,10,0,0")
        await asyncio.sleep(0.05)
        b = await client.ws_connect("/websocket?styx_vid=B", headers=HDR)
        msg = await asyncio.wait_for(b.receive(), 3)
        assert msg.type == aiohttp.WSMsgType.CLOSE and msg.data == gateway.BUSY_CODE
        assert msg.extra.startswith("superseded")
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_client_socket_uses_heartbeat(monkeypatch):
    seen = []
    real = gateway.web.WebSocketResponse

    class Spy(real):
        def __init__(self, *a, **kw):
            seen.append(kw)
            super().__init__(*a, **kw)
    monkeypatch.setattr(gateway.web, "WebSocketResponse", Spy)
    up = await _upstream([])
    client = await _gw(up)
    try:
        ws = await client.ws_connect("/websocket", headers=HDR)
        await ws.close()
    finally:
        await client.close()
        await up.close()
    assert gateway.WS_HEARTBEAT_S == 30.0
    assert any(kw.get("heartbeat") == gateway.WS_HEARTBEAT_S for kw in seen)


def test_stall_clock_reports_gap_only_while_video_on():
    c = gateway.StallClock(0.0)
    assert c.tick("kd,65", 5.0) is None            # video not started
    assert c.tick("START_VIDEO", 5.5) is None
    assert c.tick("m2,1,1", 6.0) is None           # 0.5 s: under threshold
    assert c.tick("pong,1", 7.5) == pytest.approx(1.5)
    assert c.tick(b"\x00", 7.6) is None            # binary never flips the flag
    assert c.tick("STOP_VIDEO", 8.0) is None
    assert c.tick("m2,1,1", 20.0) is None          # video stopped: silence is fine
    assert c.tick("START_VIDEO", 20.5) is None
    assert c.tick("m2,1,1", 22.0) == pytest.approx(1.5)


def test_is_bare_motion():
    from gateway_html import is_bare_motion
    assert is_bare_motion("m,10,20,0,0") and is_bare_motion("m2,1,-1,0,0,42")
    assert not is_bare_motion("m,10,20,1,0")      # button held
    assert not is_bare_motion("m,10,20,0,120")    # wheel
    assert not is_bare_motion("kd,65") and not is_bare_motion(b"\x00")
    assert not is_bare_motion("m2,100,100")       # malformed: treat as input


async def _switch_upstream(status):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def switch(request):
        return web.Response(status=status)
    app = web.Application()
    app.router.add_post("/api/switch", switch)
    up = TestClient(TestServer(app))
    await up.start_server()
    return up


@pytest.mark.asyncio
@pytest.mark.parametrize("status,body,expect", [
    (200, {"mode": "webrtc"}, "webrtc"),
    (200, {"mode": "websockets"}, "websockets"),
    (409, {"mode": "webrtc"}, None),
    (200, {"mode": "bogus"}, None),
])
async def test_switch_remembers_mode(tmp_path, status, body, expect):
    up = await _switch_upstream(status)
    client = await _gw(up, state_file=str(tmp_path / "gw_state.json"))
    try:
        r = await client.post("/api/switch", json=body, headers=HDR)
        assert r.status == status
        await asyncio.sleep(0.1)   # file is written just after the response is flushed
        f = tmp_path / "stream-mode"
        assert (f.read_text() if f.exists() else None) == expect
    finally:
        await client.close()
        await up.close()
