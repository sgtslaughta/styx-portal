"""Session cookie layout (spec §10.1).

API tokens are scoped to /api so proxied upstreams (same origin, other paths)
never receive them. forwardAuth gets its own styx_proxy cookie (Path=/), a
token the API refuses, so a leaked proxy cookie cannot drive the Styx API.
Path=/ cookies still reach Traefik on proxied paths, so every forwardAuth
endpoint returns `Cookie` minus STYX_COOKIES (strip_styx_cookies) and Traefik
swaps it in via authResponseHeaders: upstreams never see Styx credentials.
"""
from fastapi import Response

from app.config import Settings
from app.security.csrf import CSRF_COOKIE

_settings = Settings()

ACCESS_PATH = "/api"
REFRESH_PATH = "/api/auth"      # only /refresh and /logout read it
PROXY_COOKIE = "styx_proxy"
_LEGACY = ("access_token", "refresh_token")   # pre-split cookies lived at Path=/
TX_PATH = "/api/auth"           # oauth_tx (state + PKCE verifier): both callbacks live here
STYX_COOKIES = frozenset({PROXY_COOKIE, *_LEGACY, CSRF_COOKIE, "styx_svc", "oauth_tx", "styx_device",
                          "styx_mfa"})


def strip_styx_cookies(header: str) -> str:
    """Cookie header minus Styx's cookies; other pairs kept verbatim, in order."""
    keep = [p.strip() for p in header.split(";")]
    return "; ".join(p for p in keep
                     if p and p.split("=", 1)[0].strip() not in STYX_COOKIES)


def clean_cookie_header(request) -> dict[str, str]:
    """forwardAuth response header replacing the upstream request's Cookie.

    An empty value is sent when nothing is left: Traefik (v3 forward.go) always
    deletes the request header named in authResponseHeaders, then copies the
    auth response's values, so the upstream gets an empty `Cookie:` line.
    """
    return {"Cookie": strip_styx_cookies("; ".join(request.headers.getlist("cookie")))}


DEVICE_COOKIE = "styx_device"


def set_device_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(DEVICE_COOKIE, token, max_age=180 * 86400, path=TX_PATH, **_common())


MFA_COOKIE = "styx_mfa"


def set_mfa_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(MFA_COOKIE, token, max_age=300, path=TX_PATH, **_common())


def clear_mfa_cookie(resp: Response) -> None:
    resp.delete_cookie(MFA_COOKIE, path=TX_PATH, **_common())


def _common() -> dict:
    return dict(httponly=True, secure=_settings.COOKIE_SECURE, samesite="strict",
                domain=_settings.COOKIE_DOMAIN)


def _clear_legacy(resp: Response) -> None:
    for name in _LEGACY:
        resp.delete_cookie(name, path="/", domain=_settings.COOKIE_DOMAIN)


def set_auth_cookies(resp: Response, access: str, refresh: str, proxy: str, csrf: str,
                     persistent: bool = True) -> None:
    """persistent=False: browser-session cookies (no Max-Age), gone when the browser closes."""
    _clear_legacy(resp)
    long_ttl = _settings.REFRESH_TTL if persistent else None
    resp.set_cookie("access_token", access,
                    max_age=_settings.ACCESS_TTL if persistent else None,
                    path=ACCESS_PATH, **_common())
    resp.set_cookie("refresh_token", refresh, max_age=long_ttl, path=REFRESH_PATH, **_common())
    resp.set_cookie(PROXY_COOKIE, proxy, max_age=long_ttl, path="/", **_common())
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=long_ttl,
                    httponly=False, secure=_settings.COOKIE_SECURE,
                    samesite="strict", domain=_settings.COOKIE_DOMAIN)


def clear_auth_cookies(resp: Response) -> None:
    _clear_legacy(resp)
    d = _settings.COOKIE_DOMAIN
    resp.delete_cookie("access_token", path=ACCESS_PATH, domain=d)
    resp.delete_cookie("refresh_token", path=REFRESH_PATH, domain=d)
    resp.delete_cookie(PROXY_COOKIE, path="/", domain=d)
    resp.delete_cookie(CSRF_COOKIE, domain=d)
