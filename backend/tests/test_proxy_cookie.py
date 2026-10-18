"""Cookie split (spec §10.1): API tokens scoped to /api, styx_proxy for forwardAuth."""
import pytest
from sqlmodel import select, update

from app.models import ProxiedService, RefreshToken, User
from app.security import tokens

PW = "correct horse battery staple"
AUTH = "/internal/services/sonarr/auth-check"


def _fwd(uri="/sonarr/"):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate"}


def _set_cookies(r) -> list[str]:
    return r.headers.get_list("set-cookie")


def _cookie(r, name: str, path: str) -> str | None:
    for c in _set_cookies(r):
        parts = [p.strip() for p in c.split(";")]
        if parts[0].startswith(f"{name}=") and f"Path={path}" in parts:
            return c
    return None


async def _svc(session):
    session.add(ProxiedService(slug="sonarr", name="Sonarr", kind="url",
                               upstream_url="http://10.0.0.2:8989", auth_mode="sso",
                               pass_identity=True))
    await session.commit()


def _sync_csrf(client):
    client.headers["X-CSRF-Token"] = client.cookies.get("csrf_token")


def _only(client, name):
    """Strip every cookie except `name` (a forwardAuth / upstream view of the jar)."""
    keep = {c.name: c.value for c in client.cookies.jar if c.name == name}
    client.cookies.clear()
    for k, v in keep.items():
        client.cookies.set(k, v)


# --- token type ---

def test_proxy_token_claims():
    t = tokens.create_proxy_token("u1", "fam1")
    c = tokens.decode_token(t)
    assert (c["type"], c["sub"], c["fam"]) == ("proxy", "u1", "fam1")


# --- cookie attributes ---

@pytest.mark.asyncio
async def test_setup_scopes_api_cookies_and_sets_proxy(client):
    r = await client.post("/api/auth/setup", json={"username": "admin", "password": PW})
    assert r.status_code == 201
    assert _cookie(r, "access_token", "/api")
    assert _cookie(r, "refresh_token", "/api/auth")
    proxy = _cookie(r, "styx_proxy", "/")
    assert proxy and "HttpOnly" in proxy and "SameSite=strict" in proxy
    # legacy Path=/ copies are expired so they stop leaking upstream
    for name in ("access_token", "refresh_token"):
        legacy = _cookie(r, name, "/")
        assert legacy and "Max-Age=0" in legacy


@pytest.mark.asyncio
async def test_login_refresh_and_change_pw_issue_proxy(member_client):
    r = await member_client.post("/api/auth/refresh")
    assert r.status_code == 200
    assert _cookie(r, "styx_proxy", "/") and _cookie(r, "refresh_token", "/api/auth")
    assert "Max-Age=0" in _cookie(r, "refresh_token", "/")
    _sync_csrf(member_client)
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": PW, "new_password": PW + "!x"})
    assert r.status_code == 200
    assert _cookie(r, "styx_proxy", "/")


@pytest.mark.asyncio
async def test_logout_clears_all_paths(member_client):
    r = await member_client.post("/api/auth/logout")
    assert r.status_code == 200
    for name, path in (("access_token", "/api"), ("refresh_token", "/api/auth"),
                       ("styx_proxy", "/"), ("access_token", "/"), ("refresh_token", "/")):
        c = _cookie(r, name, path)
        assert c and ('Max-Age=0' in c or 'expires=' in c.lower()), (name, path)


# --- API rejects the proxy token ---

@pytest.mark.asyncio
async def test_api_rejects_proxy_cookie(member_client):
    proxy = member_client.cookies.get("styx_proxy")
    member_client.cookies.clear()
    member_client.cookies.set("styx_proxy", proxy)
    assert (await member_client.get("/api/auth/me")).status_code == 401
    # even smuggled in as the access cookie
    member_client.cookies.set("access_token", proxy)
    assert (await member_client.get("/api/auth/me")).status_code == 401


@pytest.mark.asyncio
async def test_refresh_rejects_proxy_token(member_client):
    proxy = member_client.cookies.get("styx_proxy")
    csrf = member_client.cookies.get("csrf_token")
    member_client.cookies.clear()
    member_client.cookies.set("csrf_token", csrf)
    member_client.cookies.set("refresh_token", proxy)
    assert (await member_client.post("/api/auth/refresh")).status_code == 401


# --- forwardAuth uses only styx_proxy ---

@pytest.mark.asyncio
async def test_auth_check_accepts_proxy_cookie_alone(member_client, session):
    await _svc(session)
    _only(member_client, "styx_proxy")
    r = await member_client.get(AUTH, headers=_fwd())
    assert r.status_code == 200 and r.headers["x-styx-user"] == "member"


@pytest.mark.asyncio
async def test_auth_check_ignores_api_tokens(member_client, session):
    await _svc(session)
    access = [c.value for c in member_client.cookies.jar if c.name == "access_token"][0]
    refresh = [c.value for c in member_client.cookies.jar if c.name == "refresh_token"][0]
    member_client.cookies.clear()
    member_client.cookies.set("access_token", access)
    member_client.cookies.set("refresh_token", refresh)
    assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302


@pytest.mark.asyncio
async def test_auth_check_rejects_access_token_in_proxy_cookie(member_client, session):
    await _svc(session)
    user = (await session.exec(select(User).where(User.username == "member"))).first()
    member_client.cookies.clear()
    member_client.cookies.set("styx_proxy", tokens.create_access_token(user.id, user.role))
    assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302


@pytest.mark.asyncio
async def test_proxy_survives_rotation_but_dies_on_logout(member_client, session):
    await _svc(session)
    old_proxy = member_client.cookies.get("styx_proxy")
    assert (await member_client.post("/api/auth/refresh")).status_code == 200
    new_proxy = member_client.cookies.get("styx_proxy")
    assert new_proxy != old_proxy
    _sync_csrf(member_client)
    assert (await member_client.post("/api/auth/logout")).status_code == 200
    for p in (old_proxy, new_proxy):
        member_client.cookies.clear()
        member_client.cookies.set("styx_proxy", p)
        assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302


@pytest.mark.asyncio
async def test_proxy_dies_with_revoked_family(member_client, session):
    await _svc(session)
    _only(member_client, "styx_proxy")
    await session.exec(update(RefreshToken).values(revoked=True))
    await session.commit()
    assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302


@pytest.mark.asyncio
async def test_proxy_of_inactive_user_denied(member_client, session):
    await _svc(session)
    _only(member_client, "styx_proxy")
    user = (await session.exec(select(User).where(User.username == "member"))).first()
    user.is_active = False
    session.add(user)
    await session.commit()
    assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302


@pytest.mark.asyncio
async def test_expired_proxy_denied(member_client, session):
    await _svc(session)
    user = (await session.exec(select(User).where(User.username == "member"))).first()
    fam = (await session.exec(select(RefreshToken))).first().family_id
    member_client.cookies.clear()
    member_client.cookies.set("styx_proxy", tokens.create_proxy_token(user.id, fam, ttl=-5))
    assert (await member_client.get(AUTH, headers=_fwd())).status_code == 302
