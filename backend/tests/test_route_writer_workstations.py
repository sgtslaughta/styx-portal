from app.services.route_writer import build_routes_config


def _ws(**kw):
    base = {"id": "ws1", "subdomain": "desk", "lan_ip": "192.168.1.50",
            "port": 8443, "protocol": "http"}
    base.update(kw)
    return base


def test_workstation_route_emitted():
    cfg = build_routes_config([], "example.com", "tunnel", workstations=[_ws()])
    r = cfg["http"]["routers"]["ws-ws1"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/w/desk`)"
    assert "strip-w-desk" in r["middlewares"]
    assert cfg["http"]["middlewares"]["strip-w-desk"] == {
        "stripPrefix": {"prefixes": ["/w/desk"]}}
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["servers"] == [{"url": "http://192.168.1.50:8443"}]


def test_workstation_https_gets_skip_verify_transport():
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(protocol="https")])
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {
        "insecureSkipVerify": True}


def test_no_workstations_is_default():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert not any(k.startswith("ws-") for k in cfg["http"]["routers"])
