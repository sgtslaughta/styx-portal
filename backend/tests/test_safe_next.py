"""Shared server-side ?next= rule (mirrors frontend/src/lib/safe-next.ts).

A cross-site link to /login?next=/api/... would turn into a same-site
navigation carrying SameSite=Strict cookies, so next= must never point at
Styx's own API/control paths, nor smuggle them via percent-encoding.
"""
import pytest

from app.security.safe_next import safe_next


@pytest.mark.parametrize("p", [
    "/", "/sonarr/", "/sonarr/?q=a%2Fb", "/w/desk/", "/i/dev/?a=1#x", "/i/dev/p/web/",
    "/instances", "/apis/x", "/api-docs", "/loginx", "/dash?next=/api/x",
])
def test_allows(p):
    assert safe_next(p) == p


@pytest.mark.parametrize("p", [
    None, "", "//evil.com", "/\\evil.com", "https://evil.com/", "evil.com",
    "javascript:alert(1)", "/a\\b", "/x\r\nSet-Cookie: a=b", " /sonarr/", "/\t/evil.com",
    # Styx-internal first segments, any case
    "/api", "/api/", "/api/auth/logout", "/API/auth/logout", "/Api/x?y=1",
    "/internal/strip", "/_styx/exit", "/login", "/login?next=/x", "/LOGIN",
    "/logout", "/setup", "/accept-invite?t=1", "/change-password",
    # encoded separators / dots, raw or as hidden first segment
    "/%61pi/x", "/%2e%2e/api", "/x/%2E%2E/api", "/x%2fapi", "/x%2Fy", "/x%5cy", "/x%5C",
    "/%252e%252e/api", "/./api", "/x/../api", "/a/./b",
])
def test_rejects(p):
    assert safe_next(p) is None


def test_allow_login_for_exit_chain():
    assert safe_next("/login?next=/dash", allow_login=True) == "/login?next=/dash"
    assert safe_next("/api/x", allow_login=True) is None


def test_shell_paths_allowed_other_styx_paths_not():
    for ok in ("/_styx/app/sonarr/series?p=1", "/_styx/app/x/", "/_styx/app/x/web/index.html", "/_styx/app/x"):
        assert safe_next(ok) == ok
    for p in ("/_styx/app/", "/_styx/exit", "/_styx/open/x", "/_styx/application", "/_styx/app",
              "/_styx/app/../exit", "/_styx/app/%2e%2e/exit", "/_styx/app/X/..",
              "/_styx/app/x/_styx/exit", "/_styx/app/x/api/auth/me", "/_styx/app/x/login",
              "/_styx/app/x/API/y?a=1", "/_styx/app/x/%61pi/y",
              "/_styx/app/x/api;/y", "/api;x/y", "/_styx/app/x/_styx/app/y/", "/_STYX;a/app/x/"):
        assert safe_next(p) is None, p
