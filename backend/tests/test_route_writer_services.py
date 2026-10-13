# backend/tests/test_route_writer_services.py
from app.services.route_writer import build_routes_config


def _svc(**kw):
    d = {"slug": "sonarr", "upstream": "http://192.168.1.10:8989", "mount_mode": "path",
         "auth_mode": "sso", "verify_tls": True, "enabled": True}
    d.update(kw)
    return d


def test_path_mode_router():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    r = cfg["http"]["routers"]["svc-sonarr"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/sonarr`)"
    assert r["priority"] == 60
    for mw in ("ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "svc-auth-sonarr"):
        assert mw in r["middlewares"]
    fa = cfg["http"]["middlewares"]["svc-auth-sonarr"]["forwardAuth"]
    assert fa["address"] == "http://backend:8000/api/services/sonarr/auth-check"
    assert fa["authResponseHeaders"] == ["X-Styx-User", "X-Styx-Groups"]
    assert cfg["http"]["services"]["svc-sonarr"]["loadBalancer"]["servers"] == [
        {"url": "http://192.168.1.10:8989"}]
    # no cookie-root service: /api router untouched
    assert cfg["http"]["routers"]["api"]["rule"] == "Host(`example.com`) && PathPrefix(`/api`)"
    assert "api-client" not in cfg["http"]["routers"]


def test_cookie_root_router_and_api_gating():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="unraid", mount_mode="cookie-root")])
    r = cfg["http"]["routers"]["svc-unraid"]
    assert r["rule"] == "Host(`example.com`) && HeaderRegexp(`Cookie`, `(^|; )styx_svc=unraid(;|$)`)"
    assert r["priority"] == 40
    api = cfg["http"]["routers"]["api"]
    assert api["rule"] == ("Host(`example.com`) && PathPrefix(`/api`) && "
                           "!HeaderRegexp(`Cookie`, `(^|; )styx_svc=`)")
    client = cfg["http"]["routers"]["api-client"]
    assert client["rule"] == "Host(`example.com`) && PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)"
    assert client["priority"] == 100 and client["service"] == "api"


def test_exit_router_always_present_when_services():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    r = cfg["http"]["routers"]["styx-exit"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/_styx`)"
    assert r["priority"] == 90 and r["service"] == "api"


def test_app_native_has_no_forward_auth():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(auth_mode="app-native")])
    assert "svc-auth-sonarr" not in cfg["http"]["routers"]["svc-sonarr"]["middlewares"]
    assert "svc-auth-sonarr" not in cfg["http"]["middlewares"]


def test_insecure_upstream_transport():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(upstream="https://10.0.0.5", verify_tls=False)])
    lb = cfg["http"]["services"]["svc-sonarr"]["loadBalancer"]
    assert lb["serversTransport"] == "styx-insecure-upstream"
    assert cfg["http"]["serversTransports"]["styx-insecure-upstream"] == {"insecureSkipVerify": True}


def test_insecure_transport_coexists_with_selkies_transport():
    inst = {"id": "i1", "subdomain": "d1", "port": 3001, "protocol": "https",
            "tls_skip_verify": True, "extra_ports": []}
    cfg = build_routes_config([inst], "example.com", "tunnel",
                              services=[_svc(upstream="https://10.0.0.5", verify_tls=False)])
    assert set(cfg["http"]["serversTransports"]) == {"selkies-transport", "styx-insecure-upstream"}


def test_disabled_service_emits_nothing():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(enabled=False)])
    assert "svc-sonarr" not in cfg["http"]["routers"]
    assert "svc-sonarr" not in cfg["http"]["services"]


def test_identity_headers_stripped():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    hdrs = cfg["http"]["middlewares"]["styx-strip-identity"]["headers"]["customRequestHeaders"]
    assert hdrs["X-Styx-User"] == "" and hdrs["X-authentik-groups"] == ""


def test_no_services_no_service_middlewares():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert "styx-strip-identity" not in cfg["http"]["middlewares"]
    assert "styx-exit" not in cfg["http"]["routers"]


def test_services_not_reachable_via_lan_ip(tmp_path, monkeypatch):
    """Spec §2 'No LAN bypass': services and cookie-root takeover are public-Host only.

    api-lan / frontend-lan stay ungated and no service router is host-agnostic.
    """
    from app.services import route_writer
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    (tmp_path / "lan.crt").write_text("c")
    (tmp_path / "lan.key").write_text("k")
    cfg = build_routes_config([], "example.com", "tunnel", services=[
        _svc(), _svc(slug="unraid", mount_mode="cookie-root")])
    routers = cfg["http"]["routers"]
    assert routers["api-lan"]["rule"] == "PathPrefix(`/api`)"
    assert "svc-sonarr-lan" not in routers and "svc-unraid-lan" not in routers
    for name, r in routers.items():
        if name.startswith("svc-"):
            assert r["rule"].startswith("Host(`example.com`)")
