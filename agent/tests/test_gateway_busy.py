"""One active controller holds the seat: a second tab/device is refused (4003)
instead of letting selkies kick the active session; idle is timed per tab."""
import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")
from .test_gateway import _basic  # noqa: E402
from .test_gateway_owner import _vid_ws  # noqa: E402

HDR = {"Authorization": _basic("styx", "pw")}


@pytest.fixture(autouse=True)
def _no_connect_quiet(monkeypatch):
    monkeypatch.setattr(gateway, "CONNECT_QUIET_S", 0)


async def _pair(**kw):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws
    app = web.Application()
    app.router.add_get("/api/websockets", upstream_ws)
    up = TestClient(TestServer(app))
    await up.start_server()
    client = TestClient(TestServer(gateway.create_app(
        "styx", "pw", upstream_port=up.server.port, **kw)))
    await client.start_server()
    return up, client


async def _closed_with(ws, code=None, t=3.0, reason=None):
    msg = await asyncio.wait_for(ws.receive(), t)
    assert msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED)
    if code is not None:
        assert ws.close_code == code
    if reason is not None:
        assert msg.extra == reason


@pytest.mark.asyncio
async def test_second_controller_rejected_while_first_active(capsys):
    up, client = await _pair()
    try:
        a = await _vid_ws(client, "A", HDR)
        await a.send_str("m2,10,10,0,0")          # real input: A is active
        await asyncio.sleep(0.05)
        b = await _vid_ws(client, "B", {**HDR, "CF-Connecting-IP": "203.0.113.7"})
        await _closed_with(b, gateway.BUSY_CODE, reason="superseded: in use on another device")
        assert not a.closed                         # active session untouched
        out = capsys.readouterr().out
        assert "ws reject vid=B from=203.0.113.7" in out and "ws open vid=A" in out
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_shared_viewer_and_same_tab_reconnect_allowed():
    up, client = await _pair()
    try:
        a = await _vid_ws(client, "A", HDR)
        await a.send_str("m2,10,10,0,0")
        await asyncio.sleep(0.05)
        v = await _vid_ws(client, "B", HDR, role="viewer")
        a2 = await _vid_ws(client, "A", HDR)       # same tab (refit reconnect)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(v.receive(), 0.3)
        assert not v.closed and not a2.closed
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_takeover_allowed_once_active_tab_goes_quiet(monkeypatch):
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0.2)
    up, client = await _pair()
    try:
        a = await _vid_ws(client, "A", HDR)
        await a.send_str("m2,10,10,0,0")
        await asyncio.sleep(0.3)                    # A quiet past the hold
        b = await _vid_ws(client, "B", HDR)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.receive(), 0.3)
        assert not b.closed
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_idle_is_per_tab_not_shared(monkeypatch):
    """Another tab's input must not keep an idle tab alive."""
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0)
    up, client = await _pair(idle_timeout_s=1, idle_enabled=True)
    try:
        idle_tab = await _vid_ws(client, "A", HDR)
        busy_tab = await _vid_ws(client, "B", HDR)
        async def type_on_b():
            for _ in range(15):
                await busy_tab.send_str("kd,65")
                await asyncio.sleep(0.2)
        task = asyncio.ensure_future(type_on_b())
        await _closed_with(idle_tab, t=2.5)         # shared clock would keep it open
        task.cancel()
        assert not busy_tab.closed
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_reconnect_burst_does_not_renew_hold(monkeypatch):
    """A tab left open elsewhere reconnects on a loop; the resize it sends on
    every connect is not user input and must not hold the seat forever."""
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0.3)
    monkeypatch.setattr(gateway, "CONNECT_QUIET_S", 0.5)
    up, client = await _pair()
    try:
        a = await _vid_ws(client, "A", HDR)
        await asyncio.sleep(0.4)                    # A quiet past the hold
        await a.close()
        a = await _vid_ws(client, "A", HDR)        # stale tab reconnects...
        await a.send_str("r,1920x1080")            # ...and re-sends its size
        await asyncio.sleep(0.05)
        b = await _vid_ws(client, "B", HDR)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.receive(), 0.3)
        assert not b.closed
    finally:
        await client.close()
        await up.close()
