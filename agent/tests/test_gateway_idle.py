import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import styx_agent  # noqa: E402
gateway = pytest.importorskip("gateway")
aiohttp = pytest.importorskip("aiohttp")


def _cfg(tmp_path, **kw):
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "mode": "seat", "display": ":1",
        "stream_settings": {"framerate": 60},
        "install_dir": str(tmp_path / "styx-agent"),
        "ca_pin": "", "server_cert": "",
    }
    cfg.update(kw)
    return cfg


# === Agent-side idle computation tests ===

def test_idle_seconds_from_state_file(tmp_path):
    """idle_seconds reads last_input_ts from gateway state file."""
    cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)

    now = time.time()
    state.write_text(json.dumps({
        "active_connections": 1,
        "last_input_ts": now - 120,
        "ts": now
    }))

    idle = styx_agent.idle_seconds(cfg, gateway_alive=True)
    assert idle is not None
    assert 115 <= idle <= 130, f"expected ~120s idle, got {idle}"


def test_idle_seconds_returns_none_when_gateway_dead(tmp_path):
    """idle_seconds returns None when gateway is not running."""
    cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "active_connections": 1,
        "last_input_ts": time.time() - 60,
        "ts": time.time()
    }))

    idle = styx_agent.idle_seconds(cfg, gateway_alive=False)
    assert idle is None


def test_idle_seconds_returns_none_when_state_file_missing(tmp_path):
    """idle_seconds returns None if state file doesn't exist."""
    cfg = _cfg(tmp_path)
    idle = styx_agent.idle_seconds(cfg, gateway_alive=True)
    assert idle is None


def test_idle_seconds_returns_none_on_invalid_json(tmp_path):
    """idle_seconds returns None if state file is corrupted."""
    cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text("not valid json at all")

    idle = styx_agent.idle_seconds(cfg, gateway_alive=True)
    assert idle is None


def test_idle_seconds_returns_none_if_last_input_ts_missing(tmp_path):
    """idle_seconds returns None if last_input_ts key is absent."""
    cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "active_connections": 1,
        "ts": time.time()
    }))

    idle = styx_agent.idle_seconds(cfg, gateway_alive=True)
    assert idle is None


def test_idle_seconds_clamps_to_zero(tmp_path):
    """idle_seconds returns 0 (not negative) if last_input_ts is in future."""
    cfg = _cfg(tmp_path)
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "active_connections": 1,
        "last_input_ts": time.time() + 10,
        "ts": time.time()
    }))

    idle = styx_agent.idle_seconds(cfg, gateway_alive=True)
    assert idle >= 0


def test_health_payload_includes_idle_seconds(tmp_path):
    """health_payload() includes idle_seconds in the dict."""
    cfg = _cfg(tmp_path, mode="seat")
    state = styx_agent.gw_state_path(cfg)
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({
        "active_connections": 1,
        "last_input_ts": time.time() - 5,
        "ts": time.time()
    }))

    h = styx_agent.health_payload(cfg, selkies_alive=True, gateway_alive=True)
    assert "idle_seconds" in h
    assert isinstance(h["idle_seconds"], (int, float, type(None)))
    # should be around 5 seconds
    if h["idle_seconds"] is not None:
        assert 0 <= h["idle_seconds"] <= 10


def test_health_payload_idle_seconds_none_when_gateway_dead(tmp_path):
    """health_payload includes idle_seconds=None when gateway is dead."""
    cfg = _cfg(tmp_path, mode="seat")

    h = styx_agent.health_payload(cfg, selkies_alive=True, gateway_alive=False)
    assert "idle_seconds" in h
    assert h["idle_seconds"] is None


# === Gateway state file tracking tests ===

@pytest.mark.asyncio
async def test_gateway_writes_last_input_ts_on_connect(tmp_path):
    """Gateway state file includes last_input_ts when a connection is made."""
    import base64
    from aiohttp.test_utils import TestClient, TestServer
    from aiohttp import web

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
        # At start, state should have last_input_ts set (initial write)
        await asyncio.sleep(0.1)
        state_data = json.loads(state.read_text())
        assert "last_input_ts" in state_data
        assert isinstance(state_data["last_input_ts"], (int, float))
        assert state_data["active_connections"] == 0

        # Connect a websocket
        auth = "Basic " + base64.b64encode(b"styx:pw").decode()
        ws = await client.ws_connect("/websocket", headers={"Authorization": auth})
        await asyncio.sleep(0.1)

        # State should still have last_input_ts
        state_data = json.loads(state.read_text())
        assert "last_input_ts" in state_data
        assert state_data["active_connections"] == 1

        await ws.close()
        await asyncio.sleep(0.1)
    finally:
        await client.close()
        await upstream_client.close()


@pytest.mark.asyncio
async def test_gateway_updates_last_input_ts_on_client_input(tmp_path):
    """Gateway updates last_input_ts when client sends TEXT frames."""
    import base64
    from aiohttp.test_utils import TestClient, TestServer
    from aiohttp import web

    async def upstream_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        async for msg in ws:
            # Echo the message back for testing
            if msg.type == aiohttp.WSMsgType.TEXT:
                await ws.send_str(msg.data)
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
        auth = "Basic " + base64.b64encode(b"styx:pw").decode()
        ws = await client.ws_connect("/websocket", headers={"Authorization": auth})
        await asyncio.sleep(0.1)

        # Record initial last_input_ts
        state_data_before = json.loads(state.read_text())
        ts_before = state_data_before["last_input_ts"]
        await asyncio.sleep(0.2)

        # Send a message (client -> gateway -> upstream)
        await ws.send_str("test input")
        await asyncio.sleep(0.2)

        # last_input_ts should have advanced (or at least didn't go backward)
        state_data_after = json.loads(state.read_text())
        ts_after = state_data_after["last_input_ts"]
        assert ts_after >= ts_before, "last_input_ts should not go backward"

        await ws.close()
    finally:
        await client.close()
        await upstream_client.close()
