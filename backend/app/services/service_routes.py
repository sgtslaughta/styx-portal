# backend/app/services/service_routes.py
"""Traefik routers/middlewares for proxied services (spec §4).

Mounted on the single Styx hostname. `path` services get Path(/slug) || PathPrefix(/slug/);
`cookie-root` services take over `/` for browsers carrying the styx_svc cookie.
"""

COOKIE_NAME = "styx_svc"
# /internal is never routed by Traefik (see test_auth_check_is_internal_and_unrouted).
AUTH_CHECK = "http://backend:8000/internal/services/{slug}/auth-check"
STRIP = "http://backend:8000/internal/services/{slug}/strip"
# Same origin: the browser sends Styx's Path=/ cookies (styx_proxy, csrf_token,
# styx_svc) to every proxied app. Each service forwardAuth answers with the
# Cookie header minus Styx cookies and Traefik swaps it in (authResponseHeaders
# replaces the request header), so upstream servers never see Styx credentials.
# app-native services get a strip-only forwardAuth (no auth) for the same reason.
IDENTITY_HEADERS = ["X-Styx-User", "X-Styx-Email", "X-Styx-Groups", "X-authentik-username",
                    "X-authentik-groups", "X-authentik-email", "X-authentik-uid"]
BASE_MW = ["ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "service-unavailable-errors",
           "styx-frame-sameorigin"]


def add_service_routes(config: dict, middlewares: dict, services: list[dict],
                       domain: str, transport: dict) -> None:
    routers = config["http"]["routers"]
    lbs = config["http"]["services"]
    has_cookie_root = False
    has_insecure = False
    transports: dict = {}
    emitted = 0
    for s in services:
        if not s.get("enabled", True):
            continue
        emitted += 1
        slug = s["slug"]
        rid = f"svc-{slug}"
        mws = list(BASE_MW)
        if s["auth_mode"] != "app-native":
            middlewares[f"svc-auth-{slug}"] = {"forwardAuth": {
                "address": AUTH_CHECK.format(slug=slug),
                "authResponseHeaders": ["X-Styx-User", "X-Styx-Email", "X-Styx-Groups", "Cookie"]}}
            mws.append(f"svc-auth-{slug}")
        else:
            middlewares[f"svc-strip-{slug}"] = {"forwardAuth": {
                "address": STRIP.format(slug=slug), "authResponseHeaders": ["Cookie"]}}
            mws.append(f"svc-strip-{slug}")
        if s["mount_mode"] == "cookie-root":
            has_cookie_root = True
            rule = (f"Host(`{domain}`) && HeaderRegexp(`Cookie`, "
                    f"`(^|; ){COOKIE_NAME}={slug}(;|$)`)")
            priority = 40
        else:
            # Segment boundary: slug "a" must not capture /assets, "son" not /sonarr.
            rule = f"Host(`{domain}`) && (Path(`/{slug}`) || PathPrefix(`/{slug}/`))"
            priority = 60
        routers[rid] = {"rule": rule, "service": rid, "priority": priority,
                        "middlewares": mws, **transport}
        lb: dict = {"servers": [{"url": s["upstream"]}]}
        if uh := s.get("upstream_host"):
            # Name-based proxy upstream (NPM, Caddy): it routes by Host and TLS SNI. The
            # Host header is swapped here; X-Forwarded-Host keeps the browser's name.
            middlewares[f"svc-host-{slug}"] = {"headers": {"customRequestHeaders": {"Host": uh}}}
            mws.append(f"svc-host-{slug}")
            # Local plugin (traefik/plugins-local): the app builds absolute redirects from
            # that Host; turn the ones aimed at it back into relative ones.
            middlewares[f"svc-loc-{slug}"] = {"plugin": {"styxlocation": {"host": uh}}}
            mws.append(f"svc-loc-{slug}")
            transports[f"styx-up-{slug}"] = {"serverName": uh,
                                             "insecureSkipVerify": not s.get("verify_tls", True)}
            lb["serversTransport"] = f"styx-up-{slug}"
        elif not s.get("verify_tls", True):
            lb["serversTransport"] = "styx-insecure-upstream"
            has_insecure = True
        lbs[rid] = {"loadBalancer": lb}

    if not emitted:
        return
    middlewares["styx-strip-identity"] = {"headers": {
        "customRequestHeaders": {h: "" for h in IDENTITY_HEADERS}}}
    middlewares["service-unavailable-errors"] = {"errors": {
        "status": ["502-504"], "service": "api", "query": "/api/service-unavailable"}}
    routers["styx-exit"] = {"rule": f"Host(`{domain}`) && PathPrefix(`/_styx`)",
                            "service": "api", "priority": 90,
                            "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    middlewares["styx-frame-sameorigin"] = {"headers": {"customFrameOptionsValue": "SAMEORIGIN"}}
    routers["styx-shell"] = {"rule": f"Host(`{domain}`) && PathPrefix(`/_styx/app`)",
                             "service": "frontend", "priority": 95,
                             "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    if has_cookie_root:
        # While a takeover cookie is set, /api belongs to the app unless the
        # request is from the Styx frontend (X-Styx-Client header).
        routers["api"]["rule"] = (f"Host(`{domain}`) && PathPrefix(`/api`) && "
                                  f"!HeaderRegexp(`Cookie`, `(^|; ){COOKIE_NAME}=`)")
        routers["api-client"] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)",
            "service": "api", "priority": 100,
            "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    if has_insecure:
        transports["styx-insecure-upstream"] = {"insecureSkipVerify": True}
    if transports:
        config["http"].setdefault("serversTransports", {}).update(transports)
