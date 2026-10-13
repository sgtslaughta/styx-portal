# backend/app/services/service_routes.py
"""Traefik routers/middlewares for proxied services (spec §4).

Mounted on the single Styx hostname. `path` services get Path(/slug) || PathPrefix(/slug/);
`cookie-root` services take over `/` for browsers carrying the styx_svc cookie.
"""

COOKIE_NAME = "styx_svc"
# /internal is never routed by Traefik (see test_auth_check_is_internal_and_unrouted).
AUTH_CHECK = "http://backend:8000/internal/services/{slug}/auth-check"
# Known limitation (same-origin): services share the Styx origin, so the browser
# also sends Styx's access_token/refresh_token cookies to every proxied app.
# Stock Traefik cannot drop individual cookies from the Cookie header, so a
# service operator (or a compromised app) can read Styx session tokens.
# Only proxy apps you trust with Styx sessions; see docs (Security model).
IDENTITY_HEADERS = ["X-Styx-User", "X-Styx-Groups", "X-authentik-username",
                    "X-authentik-groups", "X-authentik-email", "X-authentik-uid"]
BASE_MW = ["ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "service-unavailable-errors"]


def add_service_routes(config: dict, middlewares: dict, services: list[dict],
                       domain: str, transport: dict) -> None:
    routers = config["http"]["routers"]
    lbs = config["http"]["services"]
    has_cookie_root = False
    has_insecure = False
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
                "authResponseHeaders": ["X-Styx-User", "X-Styx-Groups"]}}
            mws.append(f"svc-auth-{slug}")
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
        if not s.get("verify_tls", True):
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
        config["http"].setdefault("serversTransports", {})["styx-insecure-upstream"] = {
            "insecureSkipVerify": True}
