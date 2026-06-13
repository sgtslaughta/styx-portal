from app.services.route_writer import build_routes_config


def _instance(extra_ports):
    """Create a test instance dict with extra_ports."""
    return {
        "id": "i1",
        "subdomain": "app",
        "port": 3001,
        "protocol": "https",
        "tls_skip_verify": True,
        "extra_ports": extra_ports,
    }


def test_extra_port_router_direct_mode():
    """Extra-port router in direct mode uses Host() + PathPrefix() with TLS."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "code",
            "slug": "code",
            "strip_prefix": True,
        }])],
        domain="example.com",
        deploy_mode="direct",
    )
    routers = cfg["http"]["routers"]

    # Find the extra-port router (key contains slug "code")
    extra = {k: r for k, r in routers.items() if "code" in k}
    assert extra, "no extra-port router generated"

    extra_router = next(iter(extra.values()))
    rule = extra_router["rule"]

    # Rule should contain PathPrefix for the extra port and Host
    assert "PathPrefix(`/p/code`)" in rule
    assert "app.example.com" in rule

    # Verify service references port 8080
    services = cfg["http"]["services"]
    extra_services = {k: s for k, s in services.items() if "code" in k}
    assert extra_services, "no extra-port service generated"
    service = next(iter(extra_services.values()))
    assert "8080" in str(service)

    # Verify strip-prefix middleware is present
    middlewares = cfg["http"]["middlewares"]
    assert any("stripPrefix" in str(v) for v in middlewares.values()), \
        "stripPrefix middleware not found"

    # Verify auth middleware is applied to extra-port router
    assert "instance-unavailable-errors" in extra_router["middlewares"], \
        "auth middleware missing from extra-port router"


def test_extra_port_router_tunnel_mode():
    """Extra-port router in tunnel mode uses PathPrefix() only."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "debug",
            "slug": "debug",
            "strip_prefix": True,
        }])],
        domain="example.com",
        deploy_mode="tunnel",
    )
    routers = cfg["http"]["routers"]

    # Find extra-port router
    extra = {k: r for k, r in routers.items() if "debug" in k}
    assert extra, "no extra-port router generated"

    extra_router = next(iter(extra.values()))
    rule = extra_router["rule"]

    # In tunnel mode, rule uses PathPrefix without Host
    assert "/i/app/p/debug" in rule

    # Verify entrypoints are tunnel-mode defaults
    assert set(extra_router["entryPoints"]) == {"web", "websecure"}


def test_no_extra_ports_leaves_one_router():
    """Instance with no extra_ports should only have one primary router."""
    cfg = build_routes_config(
        [_instance([])],
        domain="example.com",
        deploy_mode="direct",
    )
    routers = cfg["http"]["routers"]

    # Count routers for instance i1 (primary only)
    i1_routers = [k for k in routers if k.startswith("i1")]
    assert len(i1_routers) == 1, f"Expected 1 router for i1, got {len(i1_routers)}"


def test_extra_port_strip_prefix_middleware():
    """Extra-port router should have strip-prefix middleware when strip_prefix=True."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "code",
            "slug": "code",
            "strip_prefix": True,
        }])],
        domain="example.com",
        deploy_mode="direct",
    )
    middlewares = cfg["http"]["middlewares"]

    # Find the extra-port router
    routers = cfg["http"]["routers"]
    extra_router = next((r for k, r in routers.items() if "code" in k), None)
    assert extra_router, "no extra-port router found"

    # Get the strip middleware ID from the router
    strip_mws = [m for m in extra_router.get("middlewares", []) if "strip" in m]
    assert strip_mws, "no strip middleware in extra-port router"

    # Verify the middleware exists and has the right prefix
    strip_mw = strip_mws[0]
    assert strip_mw in middlewares
    assert "/p/code" in str(middlewares[strip_mw])


def test_multiple_extra_ports_creates_multiple_routers():
    """Instance with multiple extra_ports should create routers for each."""
    cfg = build_routes_config(
        [_instance([
            {"container_port": 8080, "label": "code", "slug": "code", "strip_prefix": True},
            {"container_port": 9000, "label": "api", "slug": "api", "strip_prefix": True},
        ])],
        domain="example.com",
        deploy_mode="direct",
    )
    routers = cfg["http"]["routers"]

    # Should have primary + 2 extra-port routers
    i1_routers = [k for k in routers if k.startswith("i1")]
    assert len(i1_routers) == 3, f"Expected 3 routers for i1 (1 primary + 2 extra), got {len(i1_routers)}"

    # Verify both extra-port slugs are present
    code_router = next((r for k, r in routers.items() if "code" in k), None)
    api_router = next((r for k, r in routers.items() if "api" in k), None)
    assert code_router, "code extra-port router not found"
    assert api_router, "api extra-port router not found"


def test_extra_port_inherits_primary_middlewares():
    """Extra-port router should inherit primary router's middlewares."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "code",
            "slug": "code",
            "strip_prefix": True,
        }])],
        domain="example.com",
        deploy_mode="direct",
    )
    routers = cfg["http"]["routers"]

    # Get primary and extra-port routers
    primary = routers["i1"]
    extra = next((r for k, r in routers.items() if "code" in k), None)
    assert extra, "no extra-port router found"

    # Both should have instance-unavailable-errors middleware
    assert "instance-unavailable-errors" in primary["middlewares"]
    assert "instance-unavailable-errors" in extra["middlewares"]


def test_extra_port_service_with_tls_skip_verify():
    """Extra-port service should use serversTransport when protocol is https + tls_skip_verify."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "code",
            "slug": "code",
            "strip_prefix": True,
        }])],
        domain="example.com",
        deploy_mode="direct",
    )
    services = cfg["http"]["services"]

    # Find extra-port service
    extra_service = next((s for k, s in services.items() if "code" in k), None)
    assert extra_service, "no extra-port service found"

    # Should have serversTransport reference
    assert extra_service["loadBalancer"].get("serversTransport") == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {"insecureSkipVerify": True}


def test_extra_port_no_strip_prefix():
    """Extra-port router should work without strip_prefix middleware when disabled."""
    cfg = build_routes_config(
        [_instance([{
            "container_port": 8080,
            "label": "code",
            "slug": "code",
            "strip_prefix": False,
        }])],
        domain="example.com",
        deploy_mode="direct",
    )
    routers = cfg["http"]["routers"]

    extra_router = next((r for k, r in routers.items() if "code" in k), None)
    assert extra_router, "no extra-port router found"

    # Should not have a strip middleware for this extra port
    # (but should still have instance-unavailable-errors)
    middlewares = [m for m in extra_router["middlewares"] if "strip" in m and "code" in m]
    assert not middlewares, "strip middleware should not be present when strip_prefix=False"
