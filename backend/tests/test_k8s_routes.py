import re

from app.services.k8s_routes import MANAGED_LABEL, k8s_name, to_k8s_objects
from app.services.route_writer import build_routes_config


def _ws(**kw):
    base = {"id": "ws1", "subdomain": "desk", "lan_ip": "192.168.1.50",
            "port": 8443, "protocol": "http", "selkies_password": "pw"}
    base.update(kw)
    return base


def _objs(**kw):
    cfg = build_routes_config([], "s.example", "tunnel", workstations=[_ws(**kw)])
    return cfg, to_k8s_objects(cfg, "styx")


def _get(objs, kind, name):
    return next(o for o in objs if o["kind"] == kind
                and o["metadata"]["name"] == name)


def test_workstation_router_becomes_ingressroute():
    cfg, objs = _objs()
    ir = _get(objs, "IngressRoute", "ws-ws1")
    assert ir["spec"]["entryPoints"] == ["websecure"]
    assert ir["spec"]["tls"] == {}
    (route,) = ir["spec"]["routes"]
    assert route["match"] == cfg["http"]["routers"]["ws-ws1"]["rule"]
    assert route["services"] == [{"name": "ws-ws1", "port": 8443}]
    names = [m["name"] for m in route["middlewares"]]
    assert "ws-auth-ws1" in names and "strip-w-desk" in names


def test_ip_upstream_emits_service_and_endpointslice():
    _, objs = _objs()
    svc = _get(objs, "Service", "ws-ws1")
    assert "selector" not in svc["spec"]
    assert svc["spec"]["ports"] == [
        {"name": "http", "port": 8443, "targetPort": 8443}]
    ep = _get(objs, "EndpointSlice", "ws-ws1-ep")
    assert ep["addressType"] == "IPv4"
    assert ep["endpoints"][0]["addresses"] == ["192.168.1.50"]
    assert ep["metadata"]["labels"]["kubernetes.io/service-name"] == "ws-ws1"


def test_ipv6_upstream():
    _, objs = _objs(lan_ip="fd00::5")
    ep = _get(objs, "EndpointSlice", "ws-ws1-ep")
    assert ep["addressType"] == "IPv6"
    assert ep["endpoints"][0]["addresses"] == ["fd00::5"]


def test_api_service_maps_to_backend():
    _, objs = _objs()
    ir = _get(objs, "IngressRoute", "api")
    assert ir["spec"]["routes"][0]["services"] == [
        {"name": "backend", "port": 8000}]
    mw = _get(objs, "Middleware", "instance-unavailable-errors")
    assert mw["spec"]["errors"]["service"] == {"name": "backend", "port": 8000}
    fe = _get(objs, "IngressRoute", "frontend")
    assert fe["spec"]["routes"][0]["services"] == [
        {"name": "frontend", "port": 3000}]


def test_https_upstream_sets_scheme_and_transport():
    _, objs = _objs(protocol="https")
    ref = _get(objs, "IngressRoute", "ws-ws1")["spec"]["routes"][0]["services"][0]
    assert ref["scheme"] == "https"
    assert ref["serversTransport"] == "selkies-transport"
    st = _get(objs, "ServersTransport", "selkies-transport")
    assert st["spec"] == {"insecureSkipVerify": True}


def test_every_object_labeled_and_namespaced():
    _, objs = _objs()
    for o in objs:
        assert o["metadata"]["namespace"] == "styx"
        assert MANAGED_LABEL.items() <= o["metadata"]["labels"].items()


def test_router_without_middlewares_omits_key():
    cfg = {"http": {"routers": {"r": {"rule": "Host(`a`)", "service": "s",
                                      "priority": 1}},
                    "services": {"s": {"loadBalancer": {
                        "servers": [{"url": "http://svc:80"}]}}}}}
    (ir,) = to_k8s_objects(cfg, "styx")
    assert "middlewares" not in ir["spec"]["routes"][0]
    assert ir["spec"]["routes"][0]["services"] == [{"name": "svc", "port": 80}]


def test_k8s_name_long_and_invalid():
    n = k8s_name("WS_" + "a" * 80)
    assert re.fullmatch(r"[a-z0-9]([-a-z0-9]*[a-z0-9])?", n)
    assert len(n) <= 63
    assert n == k8s_name("WS_" + "a" * 80)
