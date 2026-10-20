"""k8s tunnel mode: CF-Connecting-IP trusted only from live cloudflared pod IPs."""
import pytest


class _FakeReq:
    def __init__(self, headers, host):
        self.headers = headers
        self.client = type("C", (), {"host": host})()


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
    monkeypatch.setattr(rate_limit, "_pod_ips_seen", {})
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
    monkeypatch.setattr(rate_limit._settings, "TRUSTED_PROXY_CIDRS", "172.16.0.0/12")
    monkeypatch.setattr(rate_limit._settings, "TUNNEL_PEER_CIDRS", "172.31.254.0/28")
    monkeypatch.setattr(rate_limit._settings, "DEPLOY_MODE", "tunnel")
    monkeypatch.setattr(k8s_api, "incluster_client",
                        lambda: (_ for _ in ()).throw(AssertionError("no k8s lookup")))
    req = _FakeReq({"cf-connecting-ip": "203.0.113.7", "x-forwarded-for": "172.31.254.2"},
                   host="172.18.0.5")
    assert rate_limit.client_ip_resolved(req) == ("203.0.113.7", True)
    assert rate_limit._tunnel_pod_ips() == set()


class _Gated(_PodClient):
    """Refresh held until released, so the request is observed while the set is stale."""
    def __init__(self, result):
        import threading
        super().__init__(result)
        self.gate = threading.Event()

    def list_pod_ips(self, *a, **k):
        self.gate.wait(5)
        return super().list_pod_ips(*a, **k)


def _stale(rl, monkeypatch, client, seen=()):
    import time
    from app.services import k8s_api
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    monkeypatch.setattr(rl, "_pod_ips", {"10.42.3.70"})
    monkeypatch.setattr(rl, "_pod_ips_seen", dict.fromkeys(["10.42.3.70", *seen]))
    monkeypatch.setattr(rl, "_pod_ok_at", time.monotonic() - 31)


def test_stale_known_hop_unresolved(k8s_tunnel, monkeypatch):
    """Lookups failing, hop is a previously seen cloudflared IP: never a bannable resolved IP."""
    client = _Gated({"10.42.3.70", "10.42.3.71"})
    _stale(k8s_tunnel, monkeypatch, client, seen=["10.42.3.71"])
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.71")) == ("10.42.3.71", False)
    client.gate.set()
    _settle(k8s_tunnel)
    assert len(client.calls) == 1   # the stale set triggered a refresh
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.3.71")) == ("1.2.3.4", True)


def test_stale_unknown_hop_stays_resolved(k8s_tunnel, monkeypatch):
    """A forged CF header from a never-seen hop (LAN SNAT) must stay bannable while stale."""
    client = _Gated({"10.42.3.70"})
    _stale(k8s_tunnel, monkeypatch, client)
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.2.224")) == ("10.42.2.224", True)
    client.gate.set()
    _settle(k8s_tunnel)


def test_never_loaded_unresolved(k8s_tunnel, monkeypatch):
    from app.services import k8s_api
    client = _Gated({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    assert k8s_tunnel.client_ip_resolved(_k8s_req("10.42.2.224")) == ("10.42.2.224", False)
    client.gate.set()
    _settle(k8s_tunnel)


def test_seen_ips_bounded_and_kept_across_refreshes(k8s_tunnel, monkeypatch):
    from app.services import k8s_api
    client = _PodClient({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    k8s_tunnel._refresh_tunnel_pod_ips("cloudflared:pod=cloudflared")
    client.result = {f"10.42.9.{i}" for i in range(70)}
    k8s_tunnel._refresh_tunnel_pod_ips("cloudflared:pod=cloudflared")
    assert len(k8s_tunnel._pod_ips_seen) == 64
    client.result = {"10.42.3.71"}
    k8s_tunnel._refresh_tunnel_pod_ips("cloudflared:pod=cloudflared")
    assert "10.42.3.71" in k8s_tunnel._pod_ips_seen and len(k8s_tunnel._pod_ips_seen) == 64


def test_proactive_refresh_at_80pct(k8s_tunnel, monkeypatch):
    import types
    from app.services import k8s_api
    clock = types.SimpleNamespace(now=1000.0)
    monkeypatch.setattr(k8s_tunnel, "time", types.SimpleNamespace(monotonic=lambda: clock.now))
    client = _PodClient({"10.42.3.70"})
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: client)
    k8s_tunnel._refresh_tunnel_pod_ips("cloudflared:pod=cloudflared")   # success at t
    clock.now += 20
    k8s_tunnel._tunnel_pod_ips()
    _settle(k8s_tunnel)
    assert len(client.calls) == 1   # not yet due
    clock.now += 5                  # t+25: past 0.8 x TTL, still inside TTL
    assert k8s_tunnel._pod_cache_fresh()
    k8s_tunnel._tunnel_pod_ips()
    _settle(k8s_tunnel)
    assert len(client.calls) == 2


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


def test_empty_pod_set_warns(k8s_tunnel, monkeypatch, caplog):
    from app.services import k8s_api
    fake = type("K", (), {"list_pod_ips": lambda self, *a, **k: set()})()
    monkeypatch.setattr(k8s_api, "incluster_client", lambda: fake)
    with caplog.at_level("WARNING"):
        k8s_tunnel._refresh_tunnel_pod_ips("cloudflared:pod=cloudflared")
    assert any("matched no Running pods" in r.message for r in caplog.records)
