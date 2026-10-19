# backend/app/services/service_routes.py
"""Traefik routers/middlewares for proxied services (spec §4).

Mounted on the single Styx hostname. `path` services get Path(/slug) || PathPrefix(/slug/);
`cookie-root` services take over `/` for browsers carrying the styx_svc cookie.
"""
import re

from app.services.route_writer import _settings

COOKIE_NAME = "styx_svc"


def focus_token(service_id: str) -> str:
    """Stable per service row; a re-created service (new id) invalidates old cookies."""
    return service_id.replace("-", "")[:12]


def focus_value(slug: str, service_id: str) -> str:
    return f"{slug}.{focus_token(service_id)}"


def focus_slug(value: str | None) -> str | None:
    """Slug half of a `<slug>.<token>` cookie value (None for old/odd formats).
    The token still has to be checked against the service row."""
    slug, dot, tok = (value or "").rpartition(".")
    return slug if dot and slug and tok else None


# /internal is never routed by Traefik (see test_auth_check_is_internal_and_unrouted).
AUTH_CHECK = "{base}/internal/services/{slug}/auth-check"
STRIP = "{base}/internal/services/{slug}/strip"
# Same origin: the browser sends Styx's Path=/ cookies (styx_proxy, csrf_token,
# styx_svc) to every proxied app. Each service forwardAuth answers with the
# Cookie header minus Styx cookies and Traefik swaps it in (authResponseHeaders
# replaces the request header), so upstream servers never see Styx credentials.
# app-native services get a strip-only forwardAuth (no auth) for the same reason.
# Underscore spellings map to the same CGI/WSGI variable as the dashed ones, and the
# common default trusted-header names must not be client-settable either.
IDENTITY_HEADERS = [
    *(f"X{sep}Styx{sep}{n}" for sep in "-_" for n in ("User", "Email", "Groups")),
    *(f"X{sep}authentik{sep}{n}" for sep in "-_" for n in ("username", "groups", "email", "uid")),
    "Remote-User", "X-Remote-User", "X-Forwarded-User", "X-Webauth-User"]
BASE_MW = ["ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "service-unavailable-errors",
           "styx-frame-sameorigin"]


def add_service_routes(config: dict, middlewares: dict, services: list[dict],
                       domain: str, transport: dict) -> None:
    routers = config["http"]["routers"]
    lbs = config["http"]["services"]
    focus_vals: list[str] = []
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
                "address": AUTH_CHECK.format(base=_settings.BACKEND_INTERNAL_URL, slug=slug),
                "authResponseHeaders": ["X-Styx-User", "X-Styx-Email", "X-Styx-Groups", "Cookie"]}}
            mws.append(f"svc-auth-{slug}")
        else:
            middlewares[f"svc-strip-{slug}"] = {"forwardAuth": {
                "address": STRIP.format(base=_settings.BACKEND_INTERNAL_URL, slug=slug), "authResponseHeaders": ["Cookie"]}}
            mws.append(f"svc-strip-{slug}")
        if s["mount_mode"] == "cookie-root":
            focus_vals.append(re.escape(focus_value(slug, s["id"])))
            rule = (f"Host(`{domain}`) && HeaderRegexp(`Cookie`, "
                    f"`(^|; ){COOKIE_NAME}={slug}\\.{focus_token(s['id'])}(;|$)`)")
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
    if focus_vals:
        # While a VALID takeover cookie is set, /api belongs to the app unless the
        # request is from the Styx frontend (X-Styx-Client header). A junk value
        # matches no Focus router and must still hit the gated api router.
        routers["api"]["rule"] = (
            f"Host(`{domain}`) && PathPrefix(`/api`) && "
            f"!HeaderRegexp(`Cookie`, `(^|; ){COOKIE_NAME}=({'|'.join(focus_vals)})(;|$)`)")
        gated = ["ip-ban-gate", "styx-ratelimit"]
        # Secret-bearing Styx URLs (top-level navigations, no X-Styx-Client) must never
        # reach a Focus app's upstream: OAuth code/state and invite tokens.
        routers["styx-oauth-cb"] = {
            "rule": (f"Host(`{domain}`) && (PathPrefix(`/api/auth/oauth/`) || "
                     "PathPrefix(`/api/auth/link/`) || PathPrefix(`/api/oauth-providers/`))"),
            "service": "api", "priority": 101, "middlewares": gated, **transport}
        routers["styx-accept-invite"] = {
            "rule": f"Host(`{domain}`) && (Path(`/accept-invite`) || PathPrefix(`/accept-invite/`))",
            "service": "frontend", "priority": 101, "middlewares": gated, **transport}
        routers["api-client"] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)",
            "service": "api", "priority": 100,
            "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    if has_insecure:
        transports["styx-insecure-upstream"] = {"insecureSkipVerify": True}
    if transports:
        config["http"].setdefault("serversTransports", {}).update(transports)
