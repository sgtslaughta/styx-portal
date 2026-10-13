import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")
from .test_gateway import _basic, _refit_pair  # noqa: E402


async def _until(cond, timeout=3.0):
    import asyncio
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < end, "condition not met in time"
        await asyncio.sleep(0.02)


async def _vid_ws(client, vid, hdr, role=None):
    extra = f"&role={role}" if role else ""
    return await client.ws_connect(f"/websocket?styx_vid={vid}&x=1{extra}", headers=hdr)


@pytest.mark.asyncio
async def test_vid_stripped_upstream_and_owner_messages(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    seen = []

    async def upstream_ws(request):
        seen.append(request.query_string)
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
        "styx", "pw", upstream_port=up.server.port, seat_dir=str(tmp_path))))
    await client.start_server()
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        assert (await a.receive()).data == "styx-owner,1"
        assert (await b.receive()).data == "styx-owner,0"
        assert seen == ["x=1", "x=1&role=viewer"]
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_owner_reconnect_within_grace_keeps_ownership_then_leaves_for_good(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    saved = gateway.OWNER_GRACE_S
    gateway.OWNER_GRACE_S = 0.4
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        assert (await a.receive()).data == "styx-owner,1"
        assert (await b.receive()).data == "styx-owner,0"
        await b.send_str("r,1280x720,primary")
        await a.close()
        a2 = await _vid_ws(client, "A", hdr)                # same vid, within grace
        assert (await a2.receive()).data == "styx-owner,1"
        await asyncio.sleep(0.8)
        assert not (tmp_path / "refit-request").exists()    # b never became owner
        await a2.close()                                    # for good
        msg = await asyncio.wait_for(b.receive(), timeout=3)
        assert msg.data == "styx-owner,1"
        msg = await asyncio.wait_for(b.receive(), timeout=3)
        assert msg.data == "styx-refit"
        assert (tmp_path / "refit-request").read_text() == "1280x720"
    finally:
        gateway.OWNER_GRACE_S = saved
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_takeover_swaps_owner_refits_and_is_not_forwarded(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    received = []
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        await a.receive()
        await b.receive()
        await b.send_str("r,1280x720,primary")              # swallowed, not owner
        await asyncio.sleep(0.1)
        assert not (tmp_path / "refit-request").exists()
        await b.send_str("styx-takeover")
        assert (await asyncio.wait_for(b.receive(), 3)).data == "styx-owner,1"
        assert (await asyncio.wait_for(a.receive(), 3)).data == "styx-owner,0"
        assert (await asyncio.wait_for(b.receive(), 3)).data == "styx-refit"
        assert (tmp_path / "refit-request").read_text() == "1280x720"
        assert "styx-takeover" not in received
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_owner_settings_dpi_publishes_seat_scale(tmp_path):
    import asyncio
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        await a.receive()
        await b.receive()
        await b.send_str('SETTINGS,{"scaling_dpi": 192}')
        await asyncio.sleep(0.1)                            # negative: nothing to poll for
        assert not (tmp_path / "seat-scale").exists()       # non-owner: ignored
        await a.send_str("SETTINGS,not json")                # garbage: ignored
        await a.send_str('SETTINGS,{"scaling_dpi": 192}')
        await _until(lambda: (tmp_path / "seat-scale").exists()
                     and (tmp_path / "seat-scale").read_text() == "2")
        await a.send_str('SETTINGS,{"scaling_dpi": 96}')
        await _until(lambda: (tmp_path / "seat-scale").read_text() == "1")
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_new_controller_takes_ownership_at_once(tmp_path):
    import asyncio
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        assert (await a.receive()).data == "styx-owner,1"
        b = await _vid_ws(client, "B", hdr)                  # controller: no role
        assert (await asyncio.wait_for(b.receive(), 3)).data == "styx-owner,1"
        assert (await asyncio.wait_for(a.receive(), 3)).data == "styx-owner,0"
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_previous_owners_pending_refit_timer_dies_on_takeover(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        assert (await a.receive()).data == "styx-owner,1"
        await a.send_str("r,1280x720,primary")               # settle timer armed
        b = await _vid_ws(client, "B", hdr)                  # takes over before it fires
        assert (await asyncio.wait_for(b.receive(), 3)).data == "styx-owner,1"
        await asyncio.sleep(0.6)                             # negative: well past SETTLE_S
        assert not (tmp_path / "refit-request").exists()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_new_controller_gets_owner_message_once(tmp_path):
    import asyncio
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        await a.receive()
        b = await _vid_ws(client, "B", hdr)
        assert (await asyncio.wait_for(b.receive(), 3)).data == "styx-owner,1"
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.receive(), 0.3)         # no duplicate
    finally:
        await client.close()
        await up.close()
