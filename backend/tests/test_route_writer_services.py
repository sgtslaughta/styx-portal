# backend/tests/test_route_writer_services.py
from app.services.route_writer import build_routes_config


def _svc(**kw):
    d = {"slug": "sonarr", "upstream": "http://192.168.1.10:8989", "mount_mode": "path",
         "auth_mode": "sso", "verify_tls": True, "enabled": True,
         "id": "01234567-89ab-cdef-0123-456789abcdef"}
    d.update(kw)
    return d


def test_path_mode_router():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    r = cfg["http"]["routers"]["svc-sonarr"]
    assert r["rule"] == "Host(`example.com`) && (Path(`/sonarr`) || PathPrefix(`/sonarr/`))"
    assert r["priority"] == 60
    for mw in ("ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "svc-auth-sonarr"):
        assert mw in r["middlewares"]
    fa = cfg["http"]["middlewares"]["svc-auth-sonarr"]["forwardAuth"]
    assert fa["address"] == "http://backend:8000/internal/services/sonarr/auth-check"
    assert fa["authResponseHeaders"] == ["X-Styx-User", "X-Styx-Email", "X-Styx-Groups", "Cookie"]
    assert cfg["http"]["services"]["svc-sonarr"]["loadBalancer"]["servers"] == [
        {"url": "http://192.168.1.10:8989"}]
    # no cookie-root service: /api router untouched
    assert cfg["http"]["routers"]["api"]["rule"] == "Host(`example.com`) && PathPrefix(`/api`)"
    assert "api-client" not in cfg["http"]["routers"]


def test_cookie_root_router_and_api_gating():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="unraid", mount_mode="cookie-root")])
    r = cfg["http"]["routers"]["svc-unraid"]
    assert r["rule"] == ("Host(`example.com`) && HeaderRegexp(`Cookie`, "
                         "`(^|; )styx_svc=unraid\\.0123456789ab(;|$)`)")
    assert r["priority"] == 40
    api = cfg["http"]["routers"]["api"]
    assert api["rule"] == ("Host(`example.com`) && PathPrefix(`/api`) && "
                           "!HeaderRegexp(`Cookie`, `(^|; )styx_svc=(unraid\\.0123456789ab)(;|$)`)")
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


def _path_matches(rule: str, path: str) -> bool:
    """Evaluate the Path/PathPrefix terms of a Traefik rule (OR-ed) against a path."""
    import re
    exact = re.findall(r"Path\(`([^`]*)`\)", rule)
    prefixes = re.findall(r"PathPrefix\(`([^`]*)`\)", rule)
    return path in exact or any(path.startswith(p) for p in prefixes)


def test_path_rule_has_segment_boundary():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(slug="a")])
    rule = cfg["http"]["routers"]["svc-a"]["rule"]
    assert rule == "Host(`example.com`) && (Path(`/a`) || PathPrefix(`/a/`))"
    assert _path_matches(rule, "/a") and _path_matches(rule, "/a/x")
    for p in ("/assets/x", "/accept-invite/t", "/ab"):
        assert not _path_matches(rule, p)


def test_log_slug_does_not_capture_login():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(slug="log")])
    assert not _path_matches(cfg["http"]["routers"]["svc-log"]["rule"], "/login")


def test_prefix_slugs_are_disjoint():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="son"), _svc(slug="sonarr")])
    son = cfg["http"]["routers"]["svc-son"]["rule"]
    sonarr = cfg["http"]["routers"]["svc-sonarr"]["rule"]
    for p in ("/sonarr", "/sonarr/", "/sonarr/api"):
        assert _path_matches(sonarr, p) and not _path_matches(son, p)
    for p in ("/son", "/son/x"):
        assert _path_matches(son, p) and not _path_matches(sonarr, p)


def test_auth_check_is_internal_and_unrouted(tmp_path, monkeypatch):
    """forwardAuth targets /internal, and no public/LAN router sends /internal to the backend."""
    from app.services import route_writer
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    (tmp_path / "lan.crt").write_text("c")
    (tmp_path / "lan.key").write_text("k")
    inst = {"id": "i1", "subdomain": "d1", "port": 3001, "protocol": "https",
            "tls_skip_verify": True, "extra_ports": []}
    ws = {"id": "w1", "subdomain": "ws1", "lan_ip": "10.0.0.9", "port": 8443, "protocol": "https"}
    cfg = build_routes_config([inst], "example.com", "tunnel", workstations=[ws], services=[
        _svc(), _svc(slug="unraid", mount_mode="cookie-root")])
    fa = cfg["http"]["middlewares"]["svc-auth-sonarr"]["forwardAuth"]
    assert fa["address"] == "http://backend:8000/internal/services/sonarr/auth-check"
    for name, r in cfg["http"]["routers"].items():
        if r["service"] != "api":
            continue
        assert "Path" in r["rule"], name  # every backend router is path-scoped
        assert not _path_matches(r["rule"], "/internal/services/sonarr/auth-check"), name
        assert not _path_matches(r["rule"], "/internal/workstations/w1/auth-check"), name
        assert not _path_matches(r["rule"], "/internal/strip"), name
        assert not _path_matches(r["rule"], "/internal/services/sonarr/strip"), name
    wfa = cfg["http"]["middlewares"]["ws-auth-w1"]["forwardAuth"]
    assert wfa["address"] == "http://backend:8000/internal/workstations/w1/auth-check"


def test_shell_router_above_focus_and_exit():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="immich", mount_mode="cookie-root")])
    r = cfg["http"]["routers"]["styx-shell"]
    assert r["service"] == "frontend" and r["priority"] == 95
    assert "PathPrefix(`/_styx/app`)" in r["rule"]
    assert r["priority"] > cfg["http"]["routers"]["styx-exit"]["priority"]
    assert r["middlewares"] == ["ip-ban-gate", "styx-ratelimit"]


def test_service_routers_force_sameorigin():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    assert "styx-frame-sameorigin" in cfg["http"]["routers"]["svc-sonarr"]["middlewares"]
    mw = cfg["http"]["middlewares"]["styx-frame-sameorigin"]
    assert mw["headers"]["customFrameOptionsValue"] == "SAMEORIGIN"


def test_stale_old_format_cookie_matches_no_route():
    import re
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="unraid", mount_mode="cookie-root")])
    rx = re.search(r"HeaderRegexp\(`Cookie`, `(.*)`\)", cfg["http"]["routers"]["svc-unraid"]["rule"]).group(1)
    assert re.search(rx, "a=1; styx_svc=unraid.0123456789ab")
    for stale in ("styx_svc=unraid", "styx_svc=unraid.ffffffffffff", "styx_svc=unraidX0123456789ab"):
        assert not re.search(rx, stale)


def _routers(*svcs, **kw):
    return build_routes_config([], "example.com", "tunnel", services=list(svcs), **kw)["http"]["routers"]


def test_frontend_routers_carry_ban_gate():
    r = _routers(_svc())
    assert r["frontend"]["middlewares"] == ["ip-ban-gate", "styx-ratelimit"]


def test_api_exclusion_only_for_valid_focus_tokens():
    r = _routers(_svc(slug="unraid", mount_mode="cookie-root"),
                 _svc(slug="ha", id="fedcba98-7654-3210-fedc-ba9876543210", mount_mode="cookie-root"),
                 _svc(slug="plain"), _svc(slug="off", mount_mode="cookie-root", enabled=False))
    rule = r["api"]["rule"]
    assert "styx_svc=(unraid\\.0123456789ab|ha\\.fedcba987654)(;|$)" in rule
    assert "off" not in rule and "plain" not in rule
    assert "styx_svc=`" not in rule      # a junk styx_svc value no longer skips the api router


def test_secret_bearing_urls_ignore_focus_cookie():
    r = _routers(_svc(slug="unraid", mount_mode="cookie-root"))
    oauth, invite = r["styx-oauth-cb"], r["styx-accept-invite"]
    assert oauth["priority"] > 40 and invite["priority"] > 40
    assert oauth["service"] == "api" and invite["service"] == "frontend"
    assert "PathPrefix(`/api/auth/oauth/`)" in oauth["rule"]
    assert "PathPrefix(`/api/auth/link/`)" in oauth["rule"]            # F11
    assert "PathPrefix(`/api/oauth-providers/`)" in oauth["rule"]
    assert "/accept-invite" in invite["rule"]
    for x in (oauth, invite):
        assert x["middlewares"] == ["ip-ban-gate", "styx-ratelimit"]
        assert "HeaderRegexp" not in x["rule"]
    assert "styx-oauth-cb" not in _routers(_svc())


def test_identity_variants_stripped():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    hdrs = cfg["http"]["middlewares"]["styx-strip-identity"]["headers"]["customRequestHeaders"]
    for h in ("X_Styx_User", "X_Styx_Email", "X_Styx_Groups", "X_authentik_username",
              "Remote-User", "X-Remote-User", "X-Forwarded-User", "X-Webauth-User"):
        assert hdrs.get(h) == ""
