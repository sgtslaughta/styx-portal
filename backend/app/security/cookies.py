"""Session cookie layout (spec §10.1).

API tokens are scoped to /api so proxied upstreams (same origin, other paths)
never receive them. forwardAuth gets its own styx_proxy cookie (Path=/), a
token the API refuses, so a leaked proxy cookie cannot drive the Styx API.
"""
from fastapi import Response

from app.config import Settings
from app.security.csrf import CSRF_COOKIE

_settings = Settings()

ACCESS_PATH = "/api"
REFRESH_PATH = "/api/auth"      # only /refresh and /logout read it
PROXY_COOKIE = "styx_proxy"
_LEGACY = ("access_token", "refresh_token")   # pre-split cookies lived at Path=/


def _common() -> dict:
    return dict(httponly=True, secure=_settings.COOKIE_SECURE, samesite="strict",
                domain=_settings.COOKIE_DOMAIN)


def _clear_legacy(resp: Response) -> None:
    for name in _LEGACY:
        resp.delete_cookie(name, path="/", domain=_settings.COOKIE_DOMAIN)


def set_auth_cookies(resp: Response, access: str, refresh: str, proxy: str, csrf: str) -> None:
    _clear_legacy(resp)
    resp.set_cookie("access_token", access, max_age=_settings.ACCESS_TTL,
                    path=ACCESS_PATH, **_common())
    resp.set_cookie("refresh_token", refresh, max_age=_settings.REFRESH_TTL,
                    path=REFRESH_PATH, **_common())
    resp.set_cookie(PROXY_COOKIE, proxy, max_age=_settings.REFRESH_TTL, path="/", **_common())
    resp.set_cookie(CSRF_COOKIE, csrf, max_age=_settings.REFRESH_TTL,
                    httponly=False, secure=_settings.COOKIE_SECURE,
                    samesite="strict", domain=_settings.COOKIE_DOMAIN)


def clear_auth_cookies(resp: Response) -> None:
    _clear_legacy(resp)
    d = _settings.COOKIE_DOMAIN
    resp.delete_cookie("access_token", path=ACCESS_PATH, domain=d)
    resp.delete_cookie("refresh_token", path=REFRESH_PATH, domain=d)
    resp.delete_cookie(PROXY_COOKIE, path="/", domain=d)
    resp.delete_cookie(CSRF_COOKIE, domain=d)
