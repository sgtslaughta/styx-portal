from app.services.route_writer import build_routes_config


def test_static_routers_present():
    cfg = build_routes_config([], "example.com")
    routers = cfg["http"]["routers"]
    assert routers["frontend"]["priority"] == 1
    assert routers["api"]["priority"] == 100
    # catch-all fallback for /i/ paths
    fb = routers["instances_fallback"]
    assert fb["rule"] == "Host(`example.com`) && PathPrefix(`/i/`)"
    assert fb["priority"] == 10
    assert fb["service"] == "api"
    assert fb["middlewares"] == ["unavailable-rewrite"]
    # dashboard router must not be present
    assert "dashboard" not in routers


def test_static_middlewares_present():
    cfg = build_routes_config([], "example.com")
    mws = cfg["http"]["middlewares"]
    assert mws["unavailable-rewrite"] == {
        "replacePath": {"path": "/api/instance-unavailable"}
    }
    assert mws["instance-unavailable-errors"] == {
        "errors": {
            "status": ["500-599"],
            "service": "api",
            "query": "/api/instance-unavailable",
        }
    }


def test_instance_router_wraps_errors_then_strip():
    inst = {"id": "abc", "subdomain": "dev", "port": 3001, "protocol": "https", "tls_skip_verify": True}
    cfg = build_routes_config([inst], "example.com")
    router = cfg["http"]["routers"]["abc"]
    assert router["rule"] == "Host(`example.com`) && PathPrefix(`/i/dev`)"
    assert router["priority"] == 50
    # errors middleware must wrap (come before) the strip middleware
    assert router["middlewares"] == ["instance-unavailable-errors", "strip-dev"]
    assert cfg["http"]["middlewares"]["strip-dev"] == {
        "stripPrefix": {"prefixes": ["/i/dev"]}
    }
    # https service with tls_skip_verify keeps insecure-skip transport
    assert cfg["http"]["services"]["abc"]["loadBalancer"]["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {"insecureSkipVerify": True}


def test_insecure_transport_only_when_template_opts_in():
    cfg = build_routes_config(
        [{"id": "i1", "subdomain": "a", "port": 3001, "protocol": "https",
          "tls_skip_verify": True},
         {"id": "i2", "subdomain": "b", "port": 8443, "protocol": "https",
          "tls_skip_verify": False}],
        "example.com")
    assert cfg["http"]["services"]["i1"]["loadBalancer"]["serversTransport"] == "selkies-transport"
    assert "serversTransport" not in cfg["http"]["services"]["i2"]["loadBalancer"]


def test_no_transport_block_when_no_instance_opts_in():
    cfg = build_routes_config(
        [{"id": "i2", "subdomain": "b", "port": 8443, "protocol": "https",
          "tls_skip_verify": False}],
        "example.com")
    assert "serversTransports" not in cfg["http"]


def test_tunnel_mode_routes_use_web_and_no_dashboard():
    cfg = build_routes_config([], "example.com", deploy_mode="tunnel")
    routers = cfg["http"]["routers"]
    assert "dashboard" not in routers
    # websecure included so the self-signed LAN cert can serve workstation
    # enrollment when the operator publishes ports 80/443
    assert routers["frontend"]["entryPoints"] == ["web", "websecure"]
    assert routers["api"]["entryPoints"] == ["web", "websecure"]
    assert routers["instances_fallback"]["entryPoints"] == ["web", "websecure"]
    assert "tls" not in routers["frontend"]
    assert "tls" not in routers["api"]
    assert "tls" not in routers["instances_fallback"]


def test_direct_mode_routes_use_websecure_tls():
    cfg = build_routes_config([], "example.com", deploy_mode="direct")
    fr = cfg["http"]["routers"]["frontend"]
    assert fr["entryPoints"] == ["websecure"]
    assert fr["tls"]["certResolver"] == "letsencrypt"
    assert {"main": "example.com", "sans": ["*.example.com"]} in fr["tls"]["domains"]

    ar = cfg["http"]["routers"]["api"]
    assert ar["entryPoints"] == ["websecure"]
    assert ar["tls"]["certResolver"] == "letsencrypt"

    fb = cfg["http"]["routers"]["instances_fallback"]
    assert fb["entryPoints"] == ["websecure"]
    assert fb["tls"]["certResolver"] == "letsencrypt"


def test_direct_mode_instance_router_has_tls():
    cfg = build_routes_config(
        [{"id": "i1", "subdomain": "a", "port": 3001, "protocol": "https",
          "tls_skip_verify": True}], "example.com", deploy_mode="direct")
    router = cfg["http"]["routers"]["i1"]
    assert router["entryPoints"] == ["websecure"]
    assert router["tls"]["certResolver"] == "letsencrypt"
    assert {"main": "example.com", "sans": ["*.example.com"]} in router["tls"]["domains"]
