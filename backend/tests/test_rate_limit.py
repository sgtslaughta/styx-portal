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
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "127.0.0.1/32")
    monkeypatch.setattr(auth_router, "client_ip_resolved", lambda r: ("192.168.50.2", False))
    ban = AsyncMock()
    monkeypatch.setattr(auth_router, "ban_ip", ban)
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


@pytest.fixture
def k8s_tunnel(monkeypatch):
    """k8s tunnel mode: Traefik's peer (last XFF hop) must be a live cloudflared pod."""
    from app.middleware import rate_limit
    monkeypatch.setattr(rate_limit._settings, "TUNNEL_PEER_K8S", "cloudflared:pod=cloudflared")
    monkeypatch.setattr(rate_limit._settings, "DEPLOY_MODE", "tunnel")
    monkeypatch.setattr(rate_limit._settings, "TUNNEL_PEER_CIDRS", "")
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "10.42.0.0/16")
    monkeypatch.setattr(rate_limit, "_pod_ips", set())
    monkeypatch.setattr(rate_limit, "_pod_next", 0.0)
    monkeypatch.setattr(rate_limit, "_pod_thread", None)
    monkeypatch.setattr(rate_limit, "_pod_ok_at", None)
    return rate_limit


def _k8s_req(xff):
    return _FakeReq({"cf-connecting-ip": "1.2.3.4", "x-forwarded-for": xff}, host="10.42.3.10")


@pytest.fixture
def fresh_pods(k8s_tunnel, monkeypatch):
    import time
    monkeypatch.setattr(k8s_tunnel, "_pod_ok_at", time.monotonic())
    monkeypatch.setattr(k8s_tunnel, "_tunnel_pod_ips", lambda: {"10.42.3.70"})


def test_cf_header_trusted_from_cloudflared_pod(k8s_tunnel, fresh_pods):
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.70")) == ("1.2.3.4", True)


def test_cf_header_forged_from_lan_ignored(k8s_tunnel, fresh_pods):
    assert k8s_tunnel.client_ip_resolved(_k8s_req("192.168.1.196")) == ("192.168.1.196", True)


def test_cf_header_forged_from_other_pod_ignored(k8s_tunnel, fresh_pods):
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.1.99")) == ("10.42.1.99", True)


class _PodClient:
    def __init__(self, result):
        self.calls, self.result = [], result

    def list_pod_ips(self, namespace, selector, timeout=10):
        self.calls.append((namespace, selector, timeout))
        if isinstance(self.result, Exception):
            raise self.result
        return set(self.result)


def _settle(rl):
    if rl._pod_thread is not None:
        rl._pod_thread.join(5)


def test_pod_lookup_failure_fails_closed(k8s_tunnel, monkeypatch):
    from app.services import k8s_api
    client = _PodClient(RuntimeError("k8s down"))
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.70")) == ("10.42.3.70", False)
    _settle(k8s_tunnel)
    assert client.calls == [("cloudflared", "pod=cloudflared", 2)]
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.70")) == ("10.42.3.70", False)
    _settle(k8s_tunnel)
    assert len(client.calls) == 1   # failure retry is rate-limited (_POD_RETRY)


def test_pod_lookup_failure_keeps_last_good_set(k8s_tunnel, monkeypatch):
    from app.services import k8s_api
    client = _PodClient({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    k8s_tunnel._tunnel_pod_ips()
    _settle(k8s_tunnel)
    client.result = RuntimeError("k8s down")
    monkeypatch.setattr(k8s_tunnel, "_pod_next", 0.0)   # force a refresh
    k8s_tunnel._tunnel_pod_ips()
    _settle(k8s_tunnel)
    assert len(client.calls) == 2
    assert k8s_tunnel._tunnel_pod_ips() == {"10.42.3.70"}


def test_pod_ips_cached(k8s_tunnel, monkeypatch):
    from app.services import k8s_api
    client = _PodClient({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    k8s_tunnel._tunnel_pod_ips()
    _settle(k8s_tunnel)
    assert k8s_tunnel._tunnel_pod_ips() == {"10.42.3.70"}
    _settle(k8s_tunnel)
    assert len(client.calls) == 1
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.70")) == ("1.2.3.4", True)


def test_pod_lookup_never_blocks_the_request(k8s_tunnel, monkeypatch):
    import threading
    from app.services import k8s_api
    gate = threading.Event()

    class _Slow(_PodClient):
        def list_pod_ips(self, *a, **k):
            gate.wait(5)
            return {"10.42.3.70"}
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: _Slow(None))
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.70")) == ("10.42.3.70", False)
    gate.set()
    _settle(k8s_tunnel)


def test_no_k8s_lookup_when_tunnel_peer_k8s_empty(monkeypatch):
    from app.middleware import rate_limit
    from app.services import k8s_api
    monkeypatch.setattr(rate_limit._settings, "TUNNEL_PEER_K8S", "")
    monkeypatch.setattr(k8s_api, "incluster_client",
                        lambda: (_ for _ in ()).throw(AssertionError("no k8s lookup")))
    req = _FakeReq({"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "172.31.254.2"})
    assert rate_limit.client_ip_resolved(req) == ("203.0.113.7", True)
    assert rate_limit._tunnel_pod_ips() == set()


def test_cache_miss_stale_returns_unresolved(k8s_tunnel, monkeypatch):
    """New cloudflared pod (rollout) not yet in a stale set: never a bannable resolved IP."""
    import threading
    import time
    from app.services import k8s_api
    gate = threading.Event()

    class _Gated(_PodClient):
        def list_pod_ips(self, *a, **k):
            gate.wait(5)
            return super().list_pod_ips(*a, **k)
    client = _Gated({"10.42.3.70", "10.42.3.71"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    monkeypatch.setattr(k8s_tunnel, "_pod_ips", {"10.42.3.70"})
    monkeypatch.setattr(k8s_tunnel, "_pod_ok_at", time.monotonic() - 31)
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.71")) == ("10.42.3.71", False)
    gate.set()
    _settle(k8s_tunnel)
    assert len(client.calls) == 1   # the miss triggered a refresh
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.71")) == ("1.2.3.4", True)


def test_cache_miss_fresh_stays_resolved(k8s_tunnel, monkeypatch):
    import time
    from app.services import k8s_api
    client = _PodClient({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    now = time.monotonic()
    monkeypatch.setattr(k8s_tunnel, "_pod_ips", {"10.42.3.70"})
    monkeypatch.setattr(k8s_tunnel, "_pod_ok_at", now)
    monkeypatch.setattr(k8s_tunnel, "_pod_next", now + 30)
    assert k8s_tunnel.client_ip_resolved(_k8s_req("192.168.1.196")) == ("192.168.1.196", True)
    _settle(k8s_tunnel)
    assert client.calls == []


def test_cache_miss_stale_respects_retry_guard(k8s_tunnel, monkeypatch):
    import time
    from app.services import k8s_api
    client = _PodClient(set())
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    monkeypatch.setattr(k8s_tunnel, "_pod_next", time.monotonic() + 5)   # failed just now
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.71")) == ("10.42.3.71", False)
    _settle(k8s_tunnel)
    assert client.calls == []
