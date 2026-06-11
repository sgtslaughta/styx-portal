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
