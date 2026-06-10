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
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/w/desk`)"
    assert "ws-forward-auth" in r["middlewares"]
    assert "strip-w-desk" in r["middlewares"]
    assert "auth-ws-desk" in r["middlewares"]
    assert cfg["http"]["middlewares"]["strip-w-desk"] == {
        "stripPrefix": {"prefixes": ["/w/desk"]}}
    # Check auth header middleware
    assert "auth-ws-desk" in cfg["http"]["middlewares"]
    auth_mw = cfg["http"]["middlewares"]["auth-ws-desk"]
    creds = base64.b64encode(b"styx:pw").decode()
    assert auth_mw["headers"]["customRequestHeaders"]["Authorization"] == f"Basic {creds}"
    # Check forwardAuth middleware
    assert "ws-forward-auth" in cfg["http"]["middlewares"]
    assert cfg["http"]["middlewares"]["ws-forward-auth"]["forwardAuth"]["address"] == \
        "http://backend:8000/api/workstations/auth-check"
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


def test_no_workstations_is_default():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert not any(k.startswith("ws-") for k in cfg["http"]["routers"])


def test_workstation_without_password_skips_auth_header_mw():
    # Workstations without a password should still have forwardAuth but no auth-header
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(selkies_password="")])
    r = cfg["http"]["routers"]["ws-ws1"]
    assert "ws-forward-auth" in r["middlewares"]
    assert "auth-ws-desk" not in r["middlewares"]
    assert "auth-ws-desk" not in cfg["http"]["middlewares"]
