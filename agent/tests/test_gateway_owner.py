import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")
from .test_gateway import _aborted, _basic, _refit_pair  # noqa: E402


async def _until(cond, timeout=3.0):
    import asyncio
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < end, "condition not met in time"
        await asyncio.sleep(0.02)


async def _vid_ws(client, vid, hdr, role=None):
    extra = f"&role={role}" if role else ""
    return await client.ws_connect(f"/websocket?styx_vid={vid}&x=1{extra}", headers=hdr)


async def _silent(ws, t=0.3):
    import asyncio
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ws.receive(), t)


@pytest.mark.asyncio
async def test_vid_stripped_upstream_and_shared_viewer_gets_no_frames(tmp_path):
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
        await _silent(a)
        await _silent(b)                                    # gateway adds no frames of its own
        assert seen == ["x=1", "x=1&role=viewer"]
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_shared_viewer_never_owns_size_or_scale(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        await b.send_str("r,1280x720,primary")              # no ownership, no refit
        await b.send_str('SETTINGS,{"scaling_dpi": 192}')   # never writes seat-scale
        await asyncio.sleep(0.6)
        assert not (tmp_path / "refit-request").exists()
        assert not (tmp_path / "seat-scale").exists()
        await _silent(a)
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_owner_reconnect_within_grace_keeps_ownership_then_hands_to_older_controller(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0)   # ownership, not the busy hold
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    saved = gateway.OWNER_GRACE_S
    gateway.OWNER_GRACE_S = 0.4
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr)                 # newer controller owns at once
        await a.send_str("r,1280x720,primary")              # A is not the owner
        await b.close()
        b2 = await _vid_ws(client, "B", hdr)                # same vid, within grace
        await asyncio.sleep(0.8)
        assert not (tmp_path / "refit-request").exists()    # A never became owner
        await b2.close()                                    # for good
        await _aborted(a)
        assert (tmp_path / "refit-request").read_text() == "1280x720"
    finally:
        gateway.OWNER_GRACE_S = saved
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_owner_leaves_with_only_shared_viewer_left_nobody_owns(tmp_path):
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    saved = gateway.OWNER_GRACE_S
    gateway.OWNER_GRACE_S = 0.2
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr, role="viewer")
        await b.send_str("r,1280x720,primary")
        await a.close()
        await asyncio.sleep(0.8)                            # well past the grace
        await _silent(b)
        assert not (tmp_path / "refit-request").exists()
    finally:
        gateway.OWNER_GRACE_S = saved
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_owner_settings_dpi_publishes_seat_scale(tmp_path):
    import asyncio
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr)                 # B owns, A is demoted
        await a.send_str('SETTINGS,{"scaling_dpi": 192}')
        await asyncio.sleep(0.1)                            # negative: nothing to poll for
        assert not (tmp_path / "seat-scale").exists()       # non-owner: ignored
        await b.send_str("SETTINGS,not json")                # garbage: ignored
        await b.send_str('SETTINGS,{"scaling_dpi": 192}')
        await _until(lambda: (tmp_path / "seat-scale").exists()
                     and (tmp_path / "seat-scale").read_text() == "2")
        await b.send_str('SETTINGS,{"scaling_dpi": 96}')
        await _until(lambda: (tmp_path / "seat-scale").read_text() == "1")
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_new_controller_takes_ownership_at_once(tmp_path):
    """The newest controller's size wins: the old one's resize is ignored."""
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        b = await _vid_ws(client, "B", hdr)
        await b.send_str("r,1280x720,primary")
        await a.send_str("r,1000x600,primary")               # demoted: ignored
        await _until(lambda: (tmp_path / "refit-request").exists())
        assert (tmp_path / "refit-request").read_text() == "1280x720"
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_previous_owners_pending_refit_timer_dies_when_replaced(tmp_path, monkeypatch):
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0)   # ownership, not the busy hold
    import asyncio
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        await a.send_str("r,1280x720,primary")               # settle timer armed
        await _vid_ws(client, "B", hdr)                      # takes over before it fires
        await asyncio.sleep(0.6)                             # negative: well past SETTLE_S
        assert not (tmp_path / "refit-request").exists()
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_seat_dpi_reaches_gnome_and_selkies_snapped(tmp_path):
    """GNOME and selkies must run one scale: pixelflux maps libei pointer
    input with selkies' scale. Both get the snapped seat scale."""
    import json
    received = []
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        await a.send_str('SETTINGS,{"scaling_dpi": 192, "h264_crf": 25}')
        await _until(lambda: any(m.startswith("SETTINGS,") for m in received))
        assert (tmp_path / "seat-scale").read_text() == "2"
        await a.send_str("s,120,primary")                     # side panel 125% -> 1.5
        await _until(lambda: any(m.startswith("s,") for m in received))
        assert (tmp_path / "seat-scale").read_text() == "1.5"
    finally:
        await client.close()
        await up.close()
    settings = [json.loads(m[9:]) for m in received if m.startswith("SETTINGS,")]
    assert settings == [{"scaling_dpi": 192, "h264_crf": 25}]
    assert [m for m in received if m.startswith("s,")] == ["s,144,primary"]


@pytest.mark.asyncio
async def test_selkies_runs_at_the_scale_the_seat_applied(tmp_path):
    """The mode may not offer the wanted scale: selkies takes the scale the
    seat helper applied (seat-scale-live), not the one asked for."""
    received = []
    (tmp_path / "seat-scale").write_text("3")
    (tmp_path / "seat-scale-live").write_text("2")
    up, client = await _refit_pair(tmp_path, received, str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        await a.send_str("s,288,primary")
        await _until(lambda: any(m.startswith("s,") for m in received))
    finally:
        await client.close()
        await up.close()
    assert [m for m in received if m.startswith("s,")] == ["s,192,primary"]


@pytest.mark.asyncio
async def test_seat_scale_change_restarts_selkies_at_same_size(tmp_path):
    """pixelflux's monitor stream keeps the scale it was made at (frozen
    stream, pointer off): a scale change refits at the live size, which
    restarts selkies on a fresh stream. An unchanged scale does not."""
    (tmp_path / "seat-size").write_text("2560x1440")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    try:
        a = await _vid_ws(client, "A", hdr)
        await a.send_str("s,96")                              # scale 1 = file default: no restart
        await asyncio_sleep(0.8)
        assert not (tmp_path / "refit-request").exists()
        await a.send_str("s,144")
        await _aborted(a)
        assert (tmp_path / "refit-request").read_text() == "2560x1440"
        assert (tmp_path / "seat-scale").read_text() == "1.5"
    finally:
        await client.close()
        await up.close()


async def asyncio_sleep(t):
    import asyncio
    await asyncio.sleep(t)


@pytest.mark.asyncio
async def test_gamemode_pins_seat_size_over_websocket(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    (tmp_path / "seat-size").write_text("1920x1080")

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
        "styx", "pw", upstream_port=up.server.port, seat_dir=str(tmp_path))))
    await client.start_server()
    hdr = {"Authorization": _basic("styx", "pw")}
    req = tmp_path / "refit-request"
    try:
        a = await _vid_ws(client, "A", hdr)
        r = await client.post("/styx/gamemode", json={"active": True, "w": 2560, "h": 1440}, headers=hdr)
        assert r.status == 204
        await _until(req.exists)
        assert req.read_text() == "2560x1440"
        req.unlink()
        a = await _vid_ws(client, "A", hdr)          # the refit dropped the old socket
        await a.send_str("r,1280x720,primary")
        await asyncio.sleep(0.6)
        assert not req.exists()
        r = await client.post("/styx/gamemode", json={"active": False, "w": 1280, "h": 720}, headers=hdr)
        assert r.status == 204
        await _until(req.exists)
        assert req.read_text() == "1280x720"
        req.unlink()
        (tmp_path / "seat-size").write_text("1280x720")
        a = await _vid_ws(client, "A", hdr)
        await a.send_str("r,1000x600,primary")
        await _until(req.exists)
        assert req.read_text() == "1000x600"
    finally:
        await client.close()
        await up.close()


@pytest.mark.asyncio
async def test_gamemode_pin_cleared_when_last_viewer_leaves(tmp_path, monkeypatch):
    # A tab closed in game mode must not leave every later session's resizes swallowed.
    monkeypatch.setattr(gateway, "BUSY_HOLD_S", 0)
    monkeypatch.setattr(gateway, "OWNER_GRACE_S", 0.3)
    monkeypatch.setattr(gateway, "REFIT_HOLD_S", 0)
    (tmp_path / "seat-size").write_text("1920x1080")
    up, client = await _refit_pair(tmp_path, [], str(tmp_path))
    hdr = {"Authorization": _basic("styx", "pw")}
    req = tmp_path / "refit-request"
    try:
        a = await _vid_ws(client, "A", hdr)
        r = await client.post("/styx/gamemode", json={"active": True, "w": 2560, "h": 1440}, headers=hdr)
        assert r.status == 204
        await _until(req.exists)
        req.unlink()
        await a.close()                                  # tab closed while pinned
        await asyncio.sleep(0.8)                         # grace over -> viewer expired
        (tmp_path / "seat-size").write_text("2560x1440")
        b = await _vid_ws(client, "B", hdr)
        await b.send_str("r,1280x720,primary")
        await _until(req.exists)                         # resizes work again
        assert req.read_text() == "1280x720"
    finally:
        await client.close()
        await up.close()
