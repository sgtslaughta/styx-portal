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
