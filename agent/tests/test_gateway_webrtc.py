"""WebRTC sessions: signaling tracking, busy refusal, beacons, idle/max-age cut."""
import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")
from .test_gateway import _basic  # noqa: E402
from .test_gateway_owner import _until  # noqa: E402

HDR = {"Authorization": _basic("styx", "pw")}


async def _pair(tmp_path, **kw):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    seen = []

    async def sig(request):
        seen.append(request.query_string)
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for _ in ws:
            pass
        return ws
    app = web.Application()
    app.router.add_get("/api/webrtc/signaling/", sig)
    up = TestClient(TestServer(app))
    await up.start_server()
    kw.setdefault("transport", "webrtc")
    client = TestClient(TestServer(gateway.create_app(
        "styx", "pw", upstream_port=up.server.port,
        state_file=str(tmp_path / "gw_state.json"), **kw)))
    await client.start_server()
    return up, client, seen


def _state(tmp_path):
    return json.loads((tmp_path / "gw_state.json").read_text())


async def _sig(client, sid):
    return await client.ws_connect(f"/api/webrtc/signaling/?styx_vid={sid}&x=1", headers=HDR)


async def _beacon(client, sid, relay=None, **extra):
    body = {"sid": sid, **({} if relay is None else {"relay_bytes": relay}), **extra}
    return await client.post("/styx/activity", json=body, headers=HDR)


@pytest.mark.asyncio
async def test_signaling_counts_as_connection_and_strips_sid(tmp_path):
    up, client, seen = await _pair(tmp_path)
    try:
        ws = await _sig(client, "A")
        await _until(lambda: _state(tmp_path)["active_connections"] == 1)
        assert _state(tmp_path)["transport"] == "webrtc"
        assert seen == ["x=1"]                            # styx_vid never reaches selkies
        await ws.close()
        await _until(lambda: _state(tmp_path)["active_connections"] == 0)
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_second_controller_refused_until_first_idle(tmp_path):
    up, client, _ = await _pair(tmp_path, idle_timeout_s=300, idle_enabled=True)
    try:
        a = await _sig(client, "A")
        assert (await _beacon(client, "A")).status == 204
        b = await _sig(client, "B")
        msg = await asyncio.wait_for(b.receive(), 3)
        assert msg.type == aiohttp.WSMsgType.CLOSE and b.close_code == gateway.BUSY_CODE
        assert not a.closed
        a2 = await _sig(client, "A")                       # same page reconnecting: fine
        await asyncio.sleep(0.1)
        assert not a2.closed
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_beacon_checks_origin_and_auth(tmp_path):
    up, client, _ = await _pair(tmp_path)
    try:
        r = await client.post("/styx/activity", json={"sid": "A"},
                              headers={**HDR, "Origin": "https://evil.example"})
        assert r.status == 403
        r = await client.post("/styx/refit", json={"w": 1, "h": 1, "dpr": 1},
                              headers={**HDR, "Origin": "https://evil.example"})
        assert r.status == 403
        assert (await client.post("/styx/activity", json={"sid": "A"})).status == 401
        assert (await client.post("/styx/activity", data="junk", headers=HDR)).status == 204
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_idle_session_is_closed_and_selkies_restart_requested(tmp_path):
    up, client, _ = await _pair(tmp_path, idle_timeout_s=1, idle_enabled=True)
    try:
        ws = await _sig(client, "A")
        msg = await asyncio.wait_for(ws.receive(), 4)       # no beacon: idle (fail-safe)
        assert msg.type == aiohttp.WSMsgType.CLOSE and ws.close_code == 4001
        assert (tmp_path / "gw_state.json.kill").read_text() == "idle"
        again = await _sig(client, "A")                    # a dead session stays dead
        await asyncio.wait_for(again.receive(), 3)
        assert again.close_code == 4001
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_beacons_keep_session_alive(tmp_path):
    up, client, _ = await _pair(tmp_path, idle_timeout_s=2, idle_enabled=True)
    try:
        ws = await _sig(client, "A")
        for _ in range(4):
            await asyncio.sleep(0.7)
            await _beacon(client, "A")
        assert not ws.closed and not (tmp_path / "gw_state.json.kill").exists()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_idle_disabled_never_cuts_but_max_session_does(tmp_path):
    up, client, _ = await _pair(tmp_path, idle_timeout_s=1, idle_enabled=False, max_session_s=2)
    try:
        ws = await _sig(client, "A")
        await asyncio.sleep(1.3)
        assert not ws.closed                                # idle off
        msg = await asyncio.wait_for(ws.receive(), 3)
        assert msg.type == aiohttp.WSMsgType.CLOSE
        assert (tmp_path / "gw_state.json.kill").read_text() == "max-session"
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_relay_bytes_accumulate_positive_deltas(tmp_path):
    up, client, _ = await _pair(tmp_path)
    try:
        await _sig(client, "A")
        for rb, total in ((100, 100), (250, 250), (250, 250), (200, 250), (300, 300)):
            await _beacon(client, "A", rb)
            assert _state(tmp_path)["turn_bytes_total"] == total
        await _beacon(client, "ghost", 999)                  # unknown sid: ignored
        await _beacon(client, "A", -5)
        await _beacon(client, "A", "x")
        assert _state(tmp_path)["turn_bytes_total"] == 300
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_bytes_only_report_does_not_count_as_activity(tmp_path):
    up, client, _ = await _pair(tmp_path, idle_timeout_s=1, idle_enabled=True)
    try:
        ws = await _sig(client, "A")
        got = asyncio.ensure_future(ws.receive())
        for _ in range(3):
            await asyncio.sleep(0.4)
            await _beacon(client, "A", 10, active=False)
        msg = await asyncio.wait_for(got, 3)
        assert msg.type == aiohttp.WSMsgType.CLOSE and ws.close_code == 4001
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_refit_beacon_feeds_size_owner_path(tmp_path):
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client, _ = await _pair(tmp_path, seat_dir=str(tmp_path))
    try:
        await _sig(client, "A")
        r = await client.post("/styx/refit", json={"sid": "A", "w": 1280, "h": 647, "dpr": 2}, headers=HDR)
        assert r.status == 204
        await _until(lambda: (tmp_path / "refit-request").exists())
        assert (tmp_path / "refit-request").read_text() == "2560x1294"
        assert (await client.post("/styx/refit", json={"w": "x"}, headers=HDR)).status == 400
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_refit_without_seat_is_a_noop(tmp_path):
    up, client, _ = await _pair(tmp_path)
    try:
        await _sig(client, "A")
        r = await client.post("/styx/refit", json={"w": 1280, "h": 647, "dpr": 1}, headers=HDR)
        assert r.status == 204 and not (tmp_path / "refit-request").exists()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_page_injection_only_for_webrtc(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="<html><head></head><body></body></html>",
                                                    content_type="text/html"))
    up = TestClient(TestServer(app))
    await up.start_server()
    out = {}
    for tr in ("webrtc", "websockets"):
        c = TestClient(TestServer(gateway.create_app("styx", "pw", upstream_port=up.server.port,
                                                     transport=tr)))
        await c.start_server()
        out[tr] = await (await c.get("/", headers=HDR)).text()
        await c.close()
    await up.close()
    assert "styx/activity" in out["webrtc"] and "styx/refit" in out["webrtc"]
    assert "styx/activity" not in out["websockets"]


def test_kill_flag_path_matches_agent():
    import agent_procs
    import gateway_webrtc
    assert agent_procs.KILL_SUFFIX == gateway_webrtc.KILL_SUFFIX


def test_relay_credit_capped_by_elapsed_time():
    import gateway_webrtc as gw
    g = gw.WebRTCGateway.__new__(gw.WebRTCGateway)
    g.turn_bytes = 0
    s = gw.Session("s1", 1000.0)
    g.credit(s, 10**12, now=1001.0)            # 1 TB claimed after 1 s
    assert g.turn_bytes <= 250e6 / 8 + gw.RELAY_SLACK_B
    before = g.turn_bytes
    g.credit(s, 10**12 + 5_000_000, now=1011.0)  # honest 5 MB over 10 s counts fully
    assert g.turn_bytes - before == 5_000_000
