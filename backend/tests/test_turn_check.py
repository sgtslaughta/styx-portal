import httpx
import pytest

from app.services.settings_store import settings as live
from app.services.turn_check import run_checks
from tests.test_workstation_agent_api import _make_ws

CRED = "https://rtc.live.cloudflare.com"
SECRETS = ("SECRET-API-TOK", "SECRET-ANA-TOK")


def mk(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def setup_cf(session, analytics=False):
    await live.set(session, "WEBRTC_TURN_PROVIDER", "cloudflare", None)
    await live.set(session, "CLOUDFLARE_TURN_TOKEN_ID", "keyOURS1234", None)
    await live.set(session, "CLOUDFLARE_TURN_API_TOKEN", SECRETS[0], None)
    if analytics:
        await live.set(session, "CLOUDFLARE_ACCOUNT_ID", "acct", None)
        await live.set(session, "CLOUDFLARE_ANALYTICS_TOKEN", SECRETS[1], None)


def by_id(rep):
    return {c["id"]: c for c in rep["checks"]}


def gql(groups):
    return httpx.Response(200, json={"data": {"viewer": {"accounts": [
        {"callsTurnUsageAdaptiveGroups": groups}]}}})


def cred_ok(req):
    return httpx.Response(200, json={"iceServers": [
        {"urls": ["stun:x", "turn:a", "turns:b"], "username": "u", "credential": "c"}]})


async def test_provider_none_skips(session):
    rep = await run_checks(session, mk(lambda r: pytest.fail("no http")))
    c = by_id(rep)
    assert c["provider"]["status"] == "skip" and "direct UDP" in c["provider"]["detail"]
    assert c["analytics"]["status"] == "skip"
    assert c["transport"]["status"] == "ok"


async def test_credentials_ok(session):
    await setup_cf(session)

    def h(req):
        assert req.url.path.endswith("/keys/keyOURS1234/credentials/generate")
        assert req.headers["authorization"] == f"Bearer {SECRETS[0]}"
        return cred_ok(req)
    c = by_id(await run_checks(session, mk(h)))["turn_credentials"]
    assert c["status"] == "ok" and "2 TURN" in c["detail"]


@pytest.mark.parametrize("code,text", [(401, "API token rejected"), (403, "API token rejected"),
                                       (404, "TURN key ID not found"), (500, "500")])
async def test_credentials_errors(session, code, text):
    await setup_cf(session)
    c = by_id(await run_checks(session, mk(lambda r: httpx.Response(code))))["turn_credentials"]
    assert c["status"] == "error" and text in c["detail"]


async def test_credentials_network_error(session):
    await setup_cf(session)

    def h(req):
        raise httpx.ConnectError("boom-net")
    c = by_id(await run_checks(session, mk(h)))["turn_credentials"]
    assert c["status"] == "error" and "boom-net" in c["detail"]


async def test_credentials_no_turn_urls(session):
    await setup_cf(session)
    c = by_id(await run_checks(session, mk(lambda r: httpx.Response(
        200, json={"iceServers": [{"urls": ["stun:x"]}]}))))["turn_credentials"]
    assert c["status"] == "error"


async def test_generic_reachable(session, monkeypatch):
    await live.set(session, "WEBRTC_TURN_PROVIDER", "generic", None)
    await live.set(session, "TURN_HOST", "turn.example", None)
    import asyncio

    class W:
        def close(self): pass

    async def ok(host, port):
        return None, W()
    monkeypatch.setattr(asyncio, "open_connection", ok)
    c = by_id(await run_checks(session, mk(lambda r: pytest.fail("no http"))))["turn_reachable"]
    assert c["status"] == "ok" and "UDP" in c["detail"]

    async def bad(host, port):
        raise OSError("refused")
    monkeypatch.setattr(asyncio, "open_connection", bad)
    c = by_id(await run_checks(session, mk(lambda r: pytest.fail("no http"))))["turn_reachable"]
    assert c["status"] == "error"


def two_stage(groups):
    def h(req):
        if "graphql" in req.url.path:
            return gql(groups)
        return cred_ok(req)
    return h


async def test_analytics_only_our_key(session):
    await setup_cf(session, analytics=True)
    g = [{"dimensions": {"keyId": "keyOURS1234"}, "sum": {"egressBytes": 1_200_000_000}}]
    c = by_id(await run_checks(session, mk(two_stage(g))))
    assert c["analytics"]["status"] == "ok" and "1.2 GB relayed this month" in c["analytics"]["detail"]
    assert "other_keys" not in c


async def test_analytics_other_key_warns(session):
    await setup_cf(session, analytics=True)
    g = [{"dimensions": {"keyId": "keyOURS1234"}, "sum": {"egressBytes": 5}},
         {"dimensions": {"keyId": "oldkeyABCD9876"}, "sum": {"egressBytes": 2_000_000_000}}]
    c = by_id(await run_checks(session, mk(two_stage(g))))
    w = c["other_keys"]
    assert w["status"] == "warn" and "…9876" in w["detail"] and "oldkeyABCD" not in w["detail"]


@pytest.mark.parametrize("resp,text", [
    (httpx.Response(403, json={}), "Analytics token rejected"),
    (httpx.Response(200, json={"errors": [{"message": "bad field"}]}), "bad field"),
])
async def test_analytics_error(session, resp, text):
    await setup_cf(session, analytics=True)

    def h(req):
        return resp if "graphql" in req.url.path else cred_ok(req)
    rep = await run_checks(session, mk(h))
    c = by_id(rep)
    assert c["analytics"]["status"] == "error" and text in c["analytics"]["detail"]
    assert not any(s in str(rep) for s in SECRETS)


async def test_transport_warn_and_ok(session):
    await setup_cf(session)
    ws = await _make_ws(session)
    c = by_id(await run_checks(session, mk(cred_ok)))["transport"]
    assert c["status"] == "warn" and "Default stream transport" in c["detail"]
    ws.stream_settings = {"transport": "webrtc"}
    session.add(ws)
    await session.commit()
    c = by_id(await run_checks(session, mk(cred_ok)))["transport"]
    assert c["status"] == "ok" and "1 workstation(s) use WebRTC" in c["detail"]


async def test_budget(session):
    await live.set(session, "TURN_BUDGET_GB", 10, None)
    c = by_id(await run_checks(session, mk(cred_ok)))["budget"]
    assert c["status"] == "ok" and "of 10 GB" in c["detail"]


async def test_endpoint(admin_client):
    r = await admin_client.get("/api/admin/turn-check")
    assert r.status_code == 200 and r.json()["provider"] == "none"


async def test_endpoint_admin_only(member_client):
    assert (await member_client.get("/api/admin/turn-check")).status_code in (401, 403)
