import re

import pytest

from app.services import k8s_routes
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


def test_k8s_skips_upstream_outside_allow_cidrs(monkeypatch, caplog):
    import logging
    from app import schemas
    monkeypatch.setattr(schemas._settings, "WORKSTATION_ALLOW_CIDRS", "192.168.1.0/24")
    with caplog.at_level(logging.WARNING, logger="styx-portal"):
        _, objs = _objs(lan_ip="10.42.1.5")
    names = {(o["kind"], o["metadata"]["name"]) for o in objs}
    assert ("Service", "ws-ws1") not in names
    assert ("EndpointSlice", "ws-ws1-ep") not in names
    assert not [o for o in objs if o["kind"] == "IngressRoute"
                and any(s["name"] == "ws-ws1" for r in o["spec"]["routes"]
                        for s in r["services"])]
    assert ("IngressRoute", "api") in names   # unrelated routes kept
    assert "ws-ws1" in caplog.text


def test_k8s_keeps_upstream_inside_allow_cidrs(monkeypatch):
    from app import schemas
    monkeypatch.setattr(schemas._settings, "WORKSTATION_ALLOW_CIDRS", "192.168.1.0/24")
    _, objs = _objs()
    assert _get(objs, "EndpointSlice", "ws-ws1-ep")
    assert _get(objs, "IngressRoute", "ws-ws1")


def test_cluster_service_upstream_becomes_namespaced_ref():
    svc = {"id": "s1", "slug": "sonarr", "upstream": "http://sonarr.media.svc:8989",
           "mount_mode": "path", "auth_mode": "styx", "verify_tls": True,
           "enabled": True, "upstream_host": None}
    cfg = build_routes_config([], "s.example", "tunnel", services=[svc])
    objs = to_k8s_objects(cfg, "styx")
    refs = [r["services"][0] for o in objs if o["kind"] == "IngressRoute"
            for r in o["spec"]["routes"] if "sonarr" in o["metadata"]["name"]]
    assert refs
    assert all(r == {"name": "sonarr", "namespace": "media", "port": 8989}
               for r in refs)
    assert not [o for o in objs if o["kind"] in ("Service", "EndpointSlice")]


def test_denied_namespaces_emit_no_ingressroute():
    def svc(slug, host):
        return {"id": slug, "slug": slug, "upstream": f"http://{host}:80",
                "mount_mode": "path", "auth_mode": "styx", "verify_tls": True,
                "enabled": True, "upstream_host": None}
    hosts = {"kube": "kubernetes.default.svc", "sys": "x.kube-system.svc",
             "self": "backend.styx.svc", "ok": "sonarr.media.svc"}
    cfg = build_routes_config([], "s.example", "tunnel",
                              services=[svc(k, h) for k, h in hosts.items()])
    names = [o["metadata"]["name"] for o in to_k8s_objects(cfg, "styx")
             if o["kind"] == "IngressRoute"]
    assert any("ok" in n for n in names)
    for k in ("kube", "sys", "self"):
        assert not [n for n in names if n.endswith(k) or f"-{k}-" in n or n.startswith(k)]


@pytest.fixture(autouse=True)
def _dns(monkeypatch):
    table = {"nas.lan": "192.168.1.10", "kubernetes.default": "10.43.0.1", "backend.styx": "10.43.7.7",
             "loop.example": "127.0.0.1"}

    def fake(host, port):
        if host == "nope.example":
            raise OSError("nxdomain")
        return [(2, 1, 6, "", (table.get(host, "93.184.216.34"), 0))]
    monkeypatch.setattr(k8s_routes, "_resolve", fake)


def _hsvc(slug, upstream):
    return {"id": slug, "slug": slug, "upstream": upstream,
            "mount_mode": "path", "auth_mode": "styx", "verify_tls": True,
            "enabled": True, "upstream_host": None}


def _svc_objs(slug, upstream):
    cfg = build_routes_config([], "s.example", "tunnel",
                              services=[_hsvc(slug, upstream)])
    return to_k8s_objects(cfg, "styx")


def _irs(objs, slug):
    return [o for o in objs if o["kind"] == "IngressRoute"
            and f"svc-{slug}" in o["metadata"]["name"]]


def test_hostname_upstream_becomes_externalname_service():
    objs = _svc_objs("nas", "http://nas.lan:8080")
    svc = _get(objs, "Service", "svc-nas")
    assert svc["spec"]["type"] == "ExternalName"
    assert svc["spec"]["externalName"] == "nas.lan"
    assert svc["spec"]["ports"] == [{"name": "http", "port": 8080, "targetPort": 8080}]
    (ir,) = _irs(objs, "nas")
    assert ir["spec"]["routes"][0]["services"] == [{"name": "svc-nas", "port": 8080}]


def test_hostname_https_upstream_keeps_scheme():
    objs = _svc_objs("x", "https://x.example.com")
    (ir,) = _irs(objs, "x")
    ref = ir["spec"]["routes"][0]["services"][0]
    assert ref["scheme"] == "https" and ref["port"] == 443


def test_externalname_never_points_into_cluster():
    for slug, up in (("a", "http://kubernetes.default.svc.cluster.local"),
                     ("b", "http://foo.cluster.local"),
                     ("c", "http://localhost:80"),
                     ("d", "http://app.localhost:80")):
        objs = _svc_objs(slug, up)
        assert not _irs(objs, slug), up
        assert not [o for o in objs if o["kind"] == "Service"
                    and o["metadata"]["name"] == f"svc-{slug}"]


def test_single_label_host_unchanged_for_internal_routers():
    cfg = build_routes_config([], "s.example", "tunnel")
    objs = to_k8s_objects(cfg, "styx")
    ir = _get(objs, "IngressRoute", "frontend")
    assert ir["spec"]["routes"][0]["services"] == [{"name": "frontend", "port": 3000}]


def test_proxied_service_never_targets_styx_namespace_service():
    assert not _irs(_svc_objs("fe", "http://frontend:80"), "fe")
    assert not _irs(_svc_objs("be", "http://backend.styx:8000"), "be")


def test_styxlocation_plugin_middleware_is_valid_crd():
    s = _hsvc("npm", "https://npm.lan:443")
    s["upstream_host"] = "app.example.com"
    cfg = build_routes_config([], "s.example", "tunnel", services=[s])
    objs = to_k8s_objects(cfg, "styx")
    mw = _get(objs, "Middleware", "svc-loc-npm")
    assert mw["apiVersion"] == "traefik.io/v1alpha1"
    assert mw["spec"] == {"plugin": {"styxlocation": {"host": "app.example.com"}}}
    (ir,) = _irs(objs, "npm")
    assert {"name": "svc-loc-npm"} in ir["spec"]["routes"][0]["middlewares"]


def test_externalname_resolve_and_normalize_checks():
    for slug, up in (("a", "http://kubernetes.default.svc.cluster.local.:80"),
                     ("b", "http://kubernetes.default:80"),
                     ("c", "http://a..b:80"),
                     ("d", "http://nope.example:80"),
                     ("e", "http://loop.example:80"),
                     ("f", "http://x.svc.evil.com:80")):
        assert not _irs(_svc_objs(slug, up), slug), up
    assert _irs(_svc_objs("nas", "http://nas.lan:80"), "nas")
    assert _irs(_svc_objs("x", "http://x.example.com:80"), "x")
