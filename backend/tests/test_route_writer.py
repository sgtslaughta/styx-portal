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
    inst = {"id": "abc", "subdomain": "dev", "port": 3001, "protocol": "https"}
    cfg = build_routes_config([inst], "example.com")
    router = cfg["http"]["routers"]["abc"]
    assert router["rule"] == "Host(`example.com`) && PathPrefix(`/i/dev`)"
    assert router["priority"] == 50
    # errors middleware must wrap (come before) the strip middleware
    assert router["middlewares"] == ["instance-unavailable-errors", "strip-dev"]
    assert cfg["http"]["middlewares"]["strip-dev"] == {
        "stripPrefix": {"prefixes": ["/i/dev"]}
    }
    # https service keeps insecure-skip transport
    assert cfg["http"]["services"]["abc"]["loadBalancer"]["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {"insecureSkipVerify": True}
