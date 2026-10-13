"""Security-review fixes for the service proxy (cookie-root loop, session expiry, bypass)."""
from urllib.parse import parse_qs, urlsplit

import pytest

from app.models import ProxiedService

AUTH = "/internal/services/{slug}/auth-check"


async def _svc(session, **kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "auth_mode": "sso", "bypass_rules": []}
    d.update(kw)
    s = ProxiedService(**d)
    session.add(s)
    await session.commit()
    return s


def _fwd(uri, **h):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate", **h}


# --- B: cookie-root login loop ---

@pytest.mark.asyncio
async def test_cookie_root_anonymous_redirects_via_exit(client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root")
    r = await client.get(AUTH.format(slug="unraid"), headers=_fwd("/dash?x=1"))
    assert r.status_code == 302
    u = urlsplit(r.headers["location"])
    assert (u.scheme, u.netloc, u.path) == ("https", "localhost", "/_styx/exit")
    nxt = parse_qs(u.query)["next"][0]
    assert nxt.startswith("/login?next=")
    assert parse_qs(urlsplit(nxt).query)["next"][0] == "/dash?x=1"


@pytest.mark.asyncio
async def test_exit_honours_safe_next(client):
    r = await client.get("/_styx/exit", params={"next": "/login?next=/dash"},
                         follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=/dash"
    assert "styx_svc" in r.headers["set-cookie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("nxt", ["//evil.com", "///evil.com", "https://evil.com", "/\\evil.com",
                                 "\\\\evil.com", "/\tevil.com", " /x", "javascript:alert(1)",
                                 "/x\r\nSet-Cookie: a=b", "", "evil.com"])
async def test_exit_rejects_unsafe_next(client, nxt):
    r = await client.get("/_styx/exit", params={"next": nxt}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"


# --- C: forwardAuth survives access-token expiry via the refresh token ---

async def _member(session):
    from sqlmodel import select
    from app.models import User
    return (await session.exec(select(User).where(User.username == "member"))).first()


def _expired_access(user):
    from app.security import tokens
    return tokens.create_access_token(user.id, user.role, ttl=-60)


@pytest.mark.asyncio
@pytest.mark.parametrize("access", ["missing", "expired"])
async def test_valid_refresh_allows_when_access_missing_or_expired(member_client, session, access):
    await _svc(session)
    user = await _member(session)
    if access == "missing":
        member_client.cookies.delete("access_token")
    else:
        member_client.cookies.set("access_token", _expired_access(user))
    r = await member_client.get(AUTH.format(slug="sonarr"), headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-user"] == "member"


@pytest.mark.asyncio
async def test_revoked_refresh_denied(member_client, session):
    from sqlmodel import update
    from app.models import RefreshToken
    await _svc(session)
    member_client.cookies.delete("access_token")
    await session.exec(update(RefreshToken).values(revoked=True))
    await session.commit()
    r = await member_client.get(AUTH.format(slug="sonarr"), headers=_fwd("/sonarr/"))
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_invalid_or_wrong_type_refresh_denied(member_client, session):
    await _svc(session)
    user = await _member(session)
    member_client.cookies.delete("access_token")
    for bad in ("garbage", _expired_access(user)):
        member_client.cookies.set("refresh_token", bad)
        r = await member_client.get(AUTH.format(slug="sonarr"), headers=_fwd("/sonarr/"))
        assert r.status_code == 302


@pytest.mark.asyncio
async def test_refresh_of_inactive_user_denied(member_client, session):
    await _svc(session)
    user = await _member(session)
    user.is_active = False
    session.add(user)
    await session.commit()
    member_client.cookies.delete("access_token")
    r = await member_client.get(AUTH.format(slug="sonarr"), headers=_fwd("/sonarr/"))
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_refresh_fallback_keeps_group_acl(member_client, session):
    await _svc(session, allowed_groups=["ops"])
    member_client.cookies.delete("access_token")
    r = await member_client.get(AUTH.format(slug="sonarr"), headers=_fwd("/sonarr/"))
    assert r.status_code == 403


# --- D: auth-check is not under the public /api prefix ---

@pytest.mark.asyncio
async def test_auth_check_not_served_under_api(member_client, session):
    await _svc(session)
    r = await member_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code in (404, 405)


# --- E: bypass matching is segment-bounded and traversal-proof ---

def _bypass_svc(session):
    return _svc(session, auth_mode="sso-with-bypass",
                bypass_rules=[{"path_prefix": "/sonarr/api", "required_header": None}])


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", ["/sonarr/api", "/sonarr/api/v3/series?q=%2e%2e%2f",
                                 "/sonarr/api/", "/sonarr//api/x", "/sonarr/./api/x"])
async def test_bypass_allows_within_prefix(client, session, uri):
    await _bypass_svc(session)
    r = await client.get(AUTH.format(slug="sonarr"), headers=_fwd(uri))
    assert r.status_code == 200, uri


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", [
    "/sonarr/apix", "/sonarr/api-admin/x",                 # no segment boundary
    "/sonarr/api/../admin", "/sonarr/api/..",              # dot-dot segments
    "/sonarr/api/%2e%2e/admin", "/sonarr/api/%2E%2E/admin",  # encoded dots
    "/sonarr/api/.%2e/admin", "/sonarr/api%2f..%2fadmin", "/sonarr/api%2Fx",
    "/sonarr/api/%5c..%5cadmin", "/sonarr/api/%5Cx",         # encoded backslash
    "/sonarr/api/\\..\\admin", "/sonarr/api\\x",            # raw backslash
    "/sonarr/api/%252e%252e/admin",                          # double-encoded
])
async def test_bypass_rejects_boundary_and_traversal(client, session, uri):
    await _bypass_svc(session)
    r = await client.get(AUTH.format(slug="sonarr"), headers=_fwd(uri))
    assert r.status_code == 302, uri
