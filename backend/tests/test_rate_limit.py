import pytest
from app.middleware.rate_limit import SlidingWindow, client_ip_from_headers, is_strict_auth


def test_strict_only_for_credential_posts():
    # credential-submitting POSTs are strict
    assert is_strict_auth("POST", "/api/auth/login") is True
    assert is_strict_auth("POST", "/api/auth/accept-invite") is True
    assert is_strict_auth("POST", "/api/auth/setup") is True


def test_login_page_gets_are_not_strict():
    # routes the login page polls must NOT be in the brute-force bucket
    assert is_strict_auth("GET", "/api/auth/setup-required") is False
    assert is_strict_auth("GET", "/api/auth/me") is False
    assert is_strict_auth("GET", "/api/auth/oauth/providers") is False
    assert is_strict_auth("POST", "/api/auth/refresh") is False
    assert is_strict_auth("POST", "/api/auth/logout") is False


def test_allows_under_limit():
    w = SlidingWindow(limit=3, window=60)
    assert all(w.allow("ip1", now=t) for t in (0, 1, 2))


def test_blocks_over_limit():
    w = SlidingWindow(limit=3, window=60)
    for t in (0, 1, 2):
        w.allow("ip1", now=t)
    assert w.allow("ip1", now=3) is False


def test_window_slides():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip1", now=10) is False
    assert w.allow("ip1", now=61) is True


def test_keys_isolated():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip2", now=0) is True


class _FakeReq:
    def __init__(self, headers, host="172.18.0.5"):  # traefik on a compose bridge
        self.headers = headers
        self.client = type("C", (), {"host": host})()


@pytest.fixture(autouse=True)
def _no_dns(monkeypatch):
    import socket

    def boom(*a, **k):
        raise AssertionError("peer trust must not use DNS")
    monkeypatch.setattr(socket, "getaddrinfo", boom)


def test_cf_connecting_ip_from_tunnel_subnet():
    req = _FakeReq({"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "172.31.254.2"})
    assert client_ip_from_headers(req) == "203.0.113.7"


def test_cf_header_ignored_when_peer_outside_tunnel_subnet():
    """Traefik published on the host: a direct client sets CF-Connecting-IP itself."""
    req = _FakeReq({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "172.18.0.5"})
    assert client_ip_from_headers(req) == "172.18.0.5"
    req = _FakeReq({"cf-connecting-ip": "1.1.1.1", "x-forwarded-for": "198.51.100.1"})
    assert client_ip_from_headers(req) == "198.51.100.1"


def test_tunnel_peer_cidrs_env_override(monkeypatch):
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TUNNEL_PEER_CIDRS", "172.30.0.0/24")
    req = {"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "172.30.0.7"}
    assert client_ip_from_headers(_FakeReq(req)) == "203.0.113.7"
    req["x-forwarded-for"] = "172.31.254.2"
    assert client_ip_from_headers(_FakeReq(req)) == "172.31.254.2"


def test_falls_back_to_first_xff():
    req = _FakeReq({"x-forwarded-for": "198.51.100.1, 10.0.0.5"})
    assert client_ip_from_headers(req) == "198.51.100.1"


def test_falls_back_to_client_host():
    req = _FakeReq({})
    assert client_ip_from_headers(req) == "172.18.0.5"


@pytest.mark.parametrize("peer", ["203.0.113.50", "10.9.9.9", "testclient", "2001:db8::1"])
def test_untrusted_peer_headers_ignored(peer):
    req = _FakeReq({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "5.6.7.8"}, host=peer)
    assert client_ip_from_headers(req) == peer


def test_trusted_proxy_cidrs_configurable(monkeypatch):
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert client_ip_from_headers(_FakeReq({"x-forwarded-for": "5.6.7.8"}, host="10.1.1.1")) == "5.6.7.8"
    assert client_ip_from_headers(_FakeReq({"x-forwarded-for": "5.6.7.8"})) == "172.18.0.5"


def test_cf_header_ignored_in_direct_mode(monkeypatch):
    """Direct mode has no Cloudflare in front: CF-Connecting-IP is client-controlled."""
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "DEPLOY_MODE", "direct")
    req = _FakeReq({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "198.51.100.1"})
    assert client_ip_from_headers(req) == "198.51.100.1"


@pytest.fixture(autouse=True)
def _legacy_bridge_trust(monkeypatch):
    """Most tests here use a 172.x proxy peer; trust it explicitly (the default no longer does)."""
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128,172.16.0.0/12")


def test_default_trusts_loopback_and_compose_bridges():
    for host in ("127.0.0.1", "::1", "172.17.0.2", "172.31.255.1"):
        assert client_ip_from_headers(_FakeReq({"x-forwarded-for": "5.6.7.8"}, host=host)) == "5.6.7.8"
    # LAN clients are not proxies: their forwarded headers are not believed
    assert client_ip_from_headers(_FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.16.3")) == "192.168.16.3"


def test_ban_check_is_exempt():
    from app.middleware.rate_limit import is_rate_limit_exempt
    assert is_rate_limit_exempt("/api/auth/ban-check") is True
    assert is_rate_limit_exempt("/api/auth/login") is False
    assert is_rate_limit_exempt("/api/agent/heartbeat", "POST") is True
    assert is_rate_limit_exempt("/api/enroll/agent.py") is True
    assert is_rate_limit_exempt("/api/enroll/register", "POST") is False


def test_middleware_reads_live_spec():
    from app.middleware.rate_limit import RateLimitMiddleware
    mw = RateLimitMiddleware(app=None)
    w1 = mw._window_for("3/60")
    assert w1.limit == 3 and w1.window == 60
    assert mw._window_for("3/60") is w1
    assert mw._window_for("9/60").limit == 9


def test_internal_forwardauth_paths_are_exempt():
    """Traefik's styx-ratelimit already runs before forwardAuth; per-asset
    auth-checks would otherwise exhaust the backend bucket and 429."""
    from app.middleware.rate_limit import is_rate_limit_exempt
    assert is_rate_limit_exempt("/internal/services/sonarr/auth-check") is True
    assert is_rate_limit_exempt("/internal/workstations/auth-check") is True
    assert is_rate_limit_exempt("/internalx") is False
    assert is_rate_limit_exempt("/api/internal/x") is False


def test_client_ip_resolved_flag():
    from app.middleware.rate_limit import client_ip_resolved
    assert client_ip_resolved(_FakeReq({}, host="127.0.0.1")) == ("127.0.0.1", False)
    assert client_ip_resolved(_FakeReq({"x-forwarded-for": "192.168.1.9"}, host="172.18.0.2")) == ("192.168.1.9", True)
    assert client_ip_resolved(_FakeReq({}, host="8.8.8.8")) == ("8.8.8.8", True)


_ROUTE = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\tMTU\tWindow\tIRTT\n"
    "eth0\t00000000\t0110A8C0\t0003\t0\t0\t0\t00000000\t0\t0\t0\n"      # default: skipped
    "eth0\t0010A8C0\t00000000\t0001\t0\t0\t0\t00F0FFFF\t0\t0\t0\n"      # 192.168.16.0/20
    "eth1\t000011AC\t00000000\t0001\t0\t0\t0\t0000FFFF\t0\t0\t0\n"      # 172.17.0.0/16
    "junk line\n"
)


def test_own_subnets_parses_proc_net_route(tmp_path):
    from app.middleware.rate_limit import own_subnets
    f = tmp_path / "route"
    f.write_text(_ROUTE)
    assert [str(n) for n in own_subnets(str(f))] == ["192.168.16.0/20", "172.17.0.0/16"]
    assert own_subnets(str(tmp_path / "missing")) == ()


def test_peer_in_own_subnet_is_trusted_proxy(tmp_path, monkeypatch):
    """F4: docker may place styx-portal in 192.168.x; Traefik must still be trusted."""
    from app.middleware import rate_limit
    f = tmp_path / "route"
    f.write_text(_ROUTE)
    rate_limit.snapshot_own_networks(str(f))
    req = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.16.3")
    assert client_ip_from_headers(req) == "5.6.7.8"
    other = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.99.3")
    assert client_ip_from_headers(other) == "192.168.99.3"


def test_snapshot_taken_once_ignores_later_networks(tmp_path):
    """A network the backend joins after startup (screenshot) must not become trusted."""
    from app.middleware import rate_limit
    f = tmp_path / "route"
    f.write_text(_ROUTE)
    rate_limit.snapshot_own_networks(str(f))
    f.write_text(_ROUTE + "br-x\t0063A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF\t0\t0\t0\n")  # 192.168.99.0/24
    rate_limit.snapshot_own_networks(str(f))
    later = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.99.9")
    assert client_ip_from_headers(later) == "192.168.99.9"
    ok = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="172.17.0.9")
    assert client_ip_from_headers(ok) == "5.6.7.8"


def test_foreign_docker_peer_not_trusted_by_default(monkeypatch):
    """172.25.x not in the snapshot: its forged XFF / CF headers are ignored."""
    from app.config import Settings
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", Settings.model_fields["TRUSTED_PROXY_CIDRS"].default)
    req = _FakeReq({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": "172.31.254.2"}, host="172.25.0.7")
    assert client_ip_from_headers(req) == "172.25.0.7"


def test_lifespan_snapshots_before_screenshot_task():
    import inspect

    from app import main
    src = inspect.getsource(main.lifespan)
    assert src.index("snapshot_own_networks()") < src.index("_screenshot_capture_loop()")


def test_unrecognised_private_proxy_is_unresolved(caplog):
    """Snapshot missed Traefik: do not attribute every client to its address."""
    from app.middleware import rate_limit
    from app.middleware.rate_limit import client_ip_resolved
    rate_limit._warned.clear()
    rate_limit._settings.TRUSTED_PROXY_CIDRS = "127.0.0.1/32"
    req = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.50.2")
    with caplog.at_level("ERROR"):
        assert client_ip_resolved(req) == ("192.168.50.2", False)
        client_ip_resolved(req)
    assert sum("unrecognised proxy" in r.message for r in caplog.records) == 1  # once per window
    assert client_ip_resolved(_FakeReq({}, host="192.168.50.2")) == ("192.168.50.2", True)
    assert client_ip_resolved(_FakeReq({"x-forwarded-for": "9.9.9.9"}, host="8.8.4.4")) \
        == ("8.8.4.4", True)


async def test_unresolved_requests_limited_by_peer(monkeypatch):
    """Fail closed: an unrecognised proxy is throttled as one client, not exempted."""
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    from app.services.settings_store import settings
    monkeypatch.setattr(settings, "get", lambda k: "2/60")
    mw = rate_limit.RateLimitMiddleware(app=None)

    async def call_next(r):
        return "ok"
    req = _FakeReq({"x-forwarded-for": "5.6.7.8"}, host="192.168.50.2")
    req.url = type("U", (), {"path": "/api/x"})()
    req.method = "GET"
    assert [await mw.dispatch(req, call_next) for _ in range(2)] == ["ok", "ok"]
    assert (await mw.dispatch(req, call_next)).status_code == 429
    assert "192.168.50.2:False" in mw._window_for("2/60")._hits


async def test_unresolved_login_tracked_but_never_banned(client, session, monkeypatch, caplog):
    from unittest.mock import AsyncMock

    from app.middleware import rate_limit
    from app.routers import auth as auth_router
    from app.services.abuse import fail_tracker
    from app.services import login_flow
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setattr(auth_router, "client_ip_resolved", lambda r: ("192.168.50.2", False))
    ban = AsyncMock()
    monkeypatch.setattr(login_flow, "ban_ip", ban)
    seen = []
    monkeypatch.setattr(fail_tracker, "record", lambda ip: seen.append(ip) or True)
    with caplog.at_level("ERROR"):
        r = await client.post("/api/auth/login", json={"username": "x", "password": "y"})
    assert r.status_code == 401
    assert seen == ["192.168.50.2"]        # tracker ran under the peer IP and tripped
    ban.assert_not_awaited()
    assert any("not resolved" in m.message for m in caplog.records)


def test_empty_snapshot_logs_error(tmp_path, caplog):
    from app.middleware import rate_limit
    with caplog.at_level("ERROR"):
        rate_limit.snapshot_own_networks(str(tmp_path / "missing"))
    assert any("no network interfaces" in r.message for r in caplog.records)


def test_trusted_networks_blank_is_empty():
    from app.middleware.rate_limit import _trusted_networks
    assert _trusted_networks("") == ()
    assert _trusted_networks(" , ") == ()
