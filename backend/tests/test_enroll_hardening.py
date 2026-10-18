import pytest
from pydantic import ValidationError

from app.schemas import WorkstationRegisterRequest
from app.services.route_writer import build_routes_config


def test_register_port_bounded():
    for bad in (0, 70000, -1):
        with pytest.raises(ValidationError):
            WorkstationRegisterRequest(token="t", hostname="h", lan_ip="10.0.0.2", port=bad)
    assert WorkstationRegisterRequest(token="t", hostname="h", lan_ip="10.0.0.2").port is None


def test_ipv6_upstream_bracketed():
    ws = {"id": "w1", "subdomain": "d", "lan_ip": "fd00::5", "port": 8443}
    cfg = build_routes_config([], domain="x.test", workstations=[ws])
    assert cfg["http"]["services"]["ws-w1"]["loadBalancer"]["servers"][0]["url"] \
        == "http://[fd00::5]:8443"


async def test_enroll_tokens_list_and_revoke(admin_client):
    r = await admin_client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 201
    rows = (await admin_client.get("/api/workstations/enroll-tokens")).json()
    assert len(rows) == 1 and "token" not in rows[0] and "token_hash" not in rows[0]
    assert (await admin_client.delete(
        f"/api/workstations/enroll-tokens/{rows[0]['id']}")).status_code == 200
    assert (await admin_client.get("/api/workstations/enroll-tokens")).json() == []
    # revoked token cannot register
    tok = r.json()["token"]
    r2 = await admin_client.post("/api/enroll/register", json={
        "token": tok, "hostname": "h", "lan_ip": "192.168.1.9"})
    assert r2.status_code == 401


async def test_enroll_token_ttl_is_short(admin_client):
    from datetime import datetime, timezone
    r = await admin_client.post("/api/workstations/enroll-tokens")
    exp = datetime.fromisoformat(r.json()["expires_at"])
    assert (exp - datetime.now(timezone.utc)).total_seconds() <= 3700
