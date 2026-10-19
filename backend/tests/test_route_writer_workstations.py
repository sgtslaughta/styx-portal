import base64
from app.services.route_writer import build_routes_config


def _ws(**kw):
    base = {"id": "ws1", "subdomain": "desk", "lan_ip": "192.168.1.50",
            "port": 8443, "protocol": "http", "selkies_password": "pw"}
    base.update(kw)
    return base


def test_workstation_route_emitted():
    cfg = build_routes_config([], "example.com", "tunnel", workstations=[_ws()])
    r = cfg["http"]["routers"]["ws-ws1"]
    assert r["rule"] == "Host(`example.com`) && (Path(`/w/desk`) || PathPrefix(`/w/desk/`))"
    assert "ws-auth-ws1" in r["middlewares"]
    assert "strip-w-desk" in r["middlewares"]
    assert "auth-ws-desk" not in r["middlewares"]
    assert cfg["http"]["middlewares"]["strip-w-desk"] == {
        "stripPrefix": {"prefixes": ["/w/desk"]}}
    # Check forwardAuth middleware
    assert "ws-auth-ws1" in cfg["http"]["middlewares"]
    assert cfg["http"]["middlewares"]["ws-auth-ws1"]["forwardAuth"]["address"] == \
        "http://backend:8000/internal/workstations/ws1/auth-check"
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["servers"] == [{"url": "http://192.168.1.50:8443"}]


def test_workstation_https_gets_skip_verify_transport():
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(protocol="https")])
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {
        "insecureSkipVerify": True}


def test_lan_cert_emitted_as_default_certificate(tmp_path, monkeypatch):
    from app.services import route_writer
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    (tmp_path / "lan.crt").write_text("cert")
    (tmp_path / "lan.key").write_text("key")
    cfg = build_routes_config([], "example.com", "tunnel")
    default = cfg["tls"]["stores"]["default"]["defaultCertificate"]
    assert default == {"certFile": "/lan-certs/lan.crt",
                       "keyFile": "/lan-certs/lan.key"}
    assert cfg["tls"]["certificates"] == [
        {"certFile": "/lan-certs/lan.crt", "keyFile": "/lan-certs/lan.key"}]


def test_no_lan_cert_no_tls_block(tmp_path, monkeypatch):
    from app.services import route_writer
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    cfg = build_routes_config([], "example.com", "tunnel")
    assert "tls" not in cfg
    # no host-agnostic LAN routers without a LAN cert
    assert "api-lan" not in cfg["http"]["routers"]


def test_lan_routers_emitted_for_ip_access(tmp_path, monkeypatch):
    from app.services import route_writer
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    (tmp_path / "lan.crt").write_text("cert")
    (tmp_path / "lan.key").write_text("key")
    cfg = build_routes_config([], "example.com", "tunnel", workstations=[_ws()])
    routers = cfg["http"]["routers"]
    # Host-agnostic catch-alls on websecure so raw-IP requests route
    assert routers["api-lan"]["rule"] == "PathPrefix(`/api`)"
    assert routers["api-lan"]["entryPoints"] == ["websecure"]
    assert routers["api-lan"]["tls"] == {}
    assert routers["frontend-lan"]["rule"] == "PathPrefix(`/`)"
    # per-workstation LAN stream route carries the same forwardAuth
    ws_lan = routers["ws-ws1-lan"]
    assert ws_lan["rule"] == "Path(`/w/desk`) || PathPrefix(`/w/desk/`)"
    assert "ws-auth-ws1" in ws_lan["middlewares"]
    assert "auth-ws-desk" not in ws_lan["middlewares"]


def test_no_workstations_is_default():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert not any(k.startswith("ws-") for k in cfg["http"]["routers"])


def test_workstation_without_password_has_only_forward_auth():
    # Workstations without a password should still have forwardAuth but no auth-header
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(selkies_password="")])
    r = cfg["http"]["routers"]["ws-ws1"]
    assert "ws-auth-ws1" in r["middlewares"]
    assert "auth-ws-desk" not in r["middlewares"]
    assert "auth-ws-desk" not in cfg["http"]["middlewares"]


def test_forward_auth_uses_backend_internal_url(monkeypatch):
    from app.services import route_writer
    base = "http://backend.styx.svc.cluster.local:8000"
    monkeypatch.setattr(route_writer._settings, "BACKEND_INTERNAL_URL", base)
    cfg = build_routes_config([], "example.com", "tunnel", workstations=[_ws()])
    mws = cfg["http"]["middlewares"]
    assert mws["ws-auth-ws1"]["forwardAuth"]["address"] == \
        f"{base}/internal/workstations/ws1/auth-check"
    assert mws["ip-ban-gate"]["forwardAuth"]["address"] == f"{base}/api/auth/ban-check"


def test_workstation_route_has_no_credentials():
    import yaml
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(selkies_password="pw")])
    assert "auth-ws-desk" not in cfg["http"]["middlewares"]
    assert "auth-ws-desk" not in cfg["http"]["routers"]["ws-ws1"]["middlewares"]
    dumped = yaml.dump(cfg)
    assert base64.b64encode(b"styx:pw").decode() not in dumped
    assert "Basic" not in dumped and "customRequestHeaders" not in dumped
    fa = cfg["http"]["middlewares"]["ws-auth-ws1"]["forwardAuth"]
    assert fa["authResponseHeaders"] == ["Cookie", "Authorization"]
    # instances/services keep Cookie only
    assert cfg["http"]["middlewares"]["strip-w-desk"] == {
        "stripPrefix": {"prefixes": ["/w/desk"]}}
