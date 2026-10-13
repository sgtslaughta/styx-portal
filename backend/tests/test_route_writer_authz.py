"""Every router route_writer emits that reaches an upstream carries the right
forwardAuth (spec §10.1). Instance routers are bound to their instance by the
auth address itself, so routing and authorization cannot disagree."""
import pytest

from app.services import route_writer
from app.services.route_writer import build_routes_config

INSTANCES = [
    {"id": "i-a", "subdomain": "dev", "port": 3001, "protocol": "https", "tls_skip_verify": True,
     "extra_ports": [{"slug": "web", "container_port": 8080},
                     {"slug": "raw", "container_port": 9000, "strip_prefix": False}]},
    {"id": "i-b", "subdomain": "devx", "port": 3001, "protocol": "http", "extra_ports": []},
]
WORKSTATIONS = [{"id": "w1", "subdomain": "ws1", "lan_ip": "10.0.0.9", "port": 8443,
                 "protocol": "https", "selkies_password": "pw"}]
SERVICES = [{"slug": s, "upstream": "http://10.0.0.2:1", "mount_mode": m, "auth_mode": a,
             "verify_tls": True, "enabled": True}
            for s, m, a in [("sonarr", "path", "sso"), ("bz", "path", "sso-with-bypass"),
                            ("plex", "path", "app-native"), ("unraid", "cookie-root", "sso"),
                            ("nas", "cookie-root", "app-native")]]
STYX = {"api", "frontend"}


@pytest.fixture(params=[("tunnel", False), ("tunnel", True), ("direct", False), ("direct", True)],
                ids=["tunnel", "tunnel-lan", "direct", "direct-lan"])
def cfg(request, tmp_path, monkeypatch):
    mode, lan = request.param
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    if lan:
        (tmp_path / "lan.crt").write_text("c")
        (tmp_path / "lan.key").write_text("k")
    return build_routes_config(INSTANCES, "example.com", mode, workstations=WORKSTATIONS,
                               services=SERVICES)


def _expected_auth(service: str) -> tuple[str, str]:
    """(middleware name, forwardAuth address) a router to `service` must use."""
    for inst in INSTANCES:
        if service == inst["id"] or service.startswith(inst["id"] + "-p-"):
            return (f"inst-auth-{inst['id']}",
                    f"http://backend:8000/internal/instances/{inst['id']}/auth-check")
    if service.startswith("ws-"):
        wid = service.removeprefix("ws-")
        return f"ws-auth-{wid}", f"http://backend:8000/internal/workstations/{wid}/auth-check"
    slug = service.removeprefix("svc-")
    svc = next(s for s in SERVICES if s["slug"] == slug)
    if svc["auth_mode"] == "app-native":
        return f"svc-strip-{slug}", f"http://backend:8000/internal/services/{slug}/strip"
    return f"svc-auth-{slug}", f"http://backend:8000/internal/services/{slug}/auth-check"


def test_every_upstream_router_has_its_own_forward_auth(cfg):
    routers, mws = cfg["http"]["routers"], cfg["http"]["middlewares"]
    upstream = {rid: r for rid, r in routers.items() if r["service"] not in STYX}
    assert upstream
    for rid, r in upstream.items():
        name, address = _expected_auth(r["service"])
        chain = r["middlewares"]
        fas = [m for m in chain if "forwardAuth" in mws[m] and m != "ip-ban-gate"]
        assert fas == [name], rid                               # exactly one, the right one
        fa = mws[name]["forwardAuth"]
        assert fa["address"] == address, rid
        assert "Cookie" in fa["authResponseHeaders"], rid
        # auth runs before any path rewrite reaches the upstream
        strips = [i for i, m in enumerate(chain) if "stripPrefix" in mws[m]]
        assert all(chain.index(name) < i for i in strips), rid


def test_instance_routers_enumerated(cfg):
    routers = cfg["http"]["routers"]
    inst = {rid for rid, r in routers.items()
            if r["service"].startswith(("i-a", "i-b"))}
    assert inst == {"i-a", "i-a-p-web", "i-a-p-raw", "i-b"}   # no LAN copies for instances
    for rid in inst:
        assert routers[rid]["middlewares"][0] == "instance-unavailable-errors", rid


def test_every_router_matching_i_reaches_api_or_gated_instance(cfg):
    """instances_fallback & co. route to the Styx API, never an instance container."""
    for rid, r in cfg["http"]["routers"].items():
        if "/i/" in r["rule"] and not r["service"].startswith(("i-a", "i-b")):
            assert r["service"] == "api", rid
    assert cfg["http"]["routers"]["instances_fallback"]["service"] == "api"


def test_no_shared_instance_middleware(cfg):
    mws = cfg["http"]["middlewares"]
    for gone in ("styx-cookie-strip", "instance-forward-auth", "ws-forward-auth"):
        assert gone not in mws


def test_instance_rule_is_segment_bounded():
    """/i/devx must not ride dev's router (and vice versa)."""
    routers = build_routes_config(INSTANCES, "example.com")["http"]["routers"]
    assert routers["i-a"]["rule"] == \
        "Host(`example.com`) && (Path(`/i/dev`) || PathPrefix(`/i/dev/`))"
    assert routers["i-b"]["rule"] == \
        "Host(`example.com`) && (Path(`/i/devx`) || PathPrefix(`/i/devx/`))"


def test_workstation_rules_are_segment_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(route_writer._settings, "LAN_CERT_DIR", str(tmp_path))
    (tmp_path / "lan.crt").write_text("c")
    (tmp_path / "lan.key").write_text("k")
    routers = build_routes_config([], "example.com", workstations=WORKSTATIONS)["http"]["routers"]
    assert routers["ws-w1"]["rule"] == \
        "Host(`example.com`) && (Path(`/w/ws1`) || PathPrefix(`/w/ws1/`))"
    assert routers["ws-w1-lan"]["rule"] == "Path(`/w/ws1`) || PathPrefix(`/w/ws1/`)"


@pytest.mark.parametrize("mode,rule", [
    ("tunnel", "Path(`/i/dev/p/web`) || PathPrefix(`/i/dev/p/web/`)"),
    ("direct", "Host(`dev.example.com`) && (Path(`/p/web`) || PathPrefix(`/p/web/`))"),
])
def test_extra_port_rules_are_segment_bounded(mode, rule):
    routers = build_routes_config(INSTANCES, "example.com", mode)["http"]["routers"]
    assert routers["i-a-p-web"]["rule"] == rule
