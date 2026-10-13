import pytest
from sqlmodel import select
from app.models import Group, ProxiedService, User, UserGroup


async def _svc(session, **kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "auth_mode": "sso-with-bypass",
         "bypass_rules": [{"path_prefix": "/sonarr/api", "required_header": "X-Api-Key"}]}
    d.update(kw)
    s = ProxiedService(**d)
    session.add(s)
    await session.commit()
    return s


def _fwd(uri, **h):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate", **h}


@pytest.mark.asyncio
async def test_anonymous_navigation_redirects_to_login(client, session):
    await _svc(session)
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 302
    assert r.headers["location"] == "https://localhost/login?next=/sonarr/"


@pytest.mark.asyncio
async def test_anonymous_xhr_401(client, session):
    await _svc(session)
    r = await client.get("/internal/services/sonarr/auth-check",
                    headers={"x-forwarded-uri": "/sonarr/x", "accept": "application/json"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bypass_with_header_allows_anonymous(client, session):
    await _svc(session)
    r = await client.get("/internal/services/sonarr/auth-check",
                    headers=_fwd("/sonarr/api/v3/series?x=1", **{"X-Api-Key": "k"}))
    assert r.status_code == 200
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/api/v3/series"))
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_member_allowed_when_no_groups_required(member_client, session):
    await _svc(session)
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-user"] == "member"


@pytest.mark.asyncio
async def test_member_denied_then_allowed_by_group(member_client, session):
    await _svc(session, allowed_groups=["media"])
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 403
    g = Group(name="media")
    session.add(g)
    await session.commit()
    user = (await session.exec(select(User).where(User.username == "member"))).first()
    session.add(UserGroup(user_id=user.id, group_id=g.id))
    await session.commit()
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-groups"] == "media"


@pytest.mark.asyncio
async def test_admin_always_allowed(admin_client, session):
    await _svc(session, allowed_groups=["nobody"])
    r = await admin_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_disabled_or_unknown_404(admin_client, session):
    await _svc(session, enabled=False)
    r = await admin_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 404
    r = await admin_client.get("/internal/services/nope/auth-check", headers=_fwd("/nope/"))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_enter_sets_cookie_and_exit_clears(member_client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso", bypass_rules=[])
    r = await member_client.post("/api/services/unraid/enter")
    assert r.status_code == 200
    assert "styx_svc=unraid" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"]
    r = await member_client.get("/_styx/exit", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    assert "styx_svc=;" in r.headers["set-cookie"] or 'styx_svc=""' in r.headers["set-cookie"]


@pytest.mark.asyncio
async def test_enter_denied_without_group(member_client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso",
               bypass_rules=[], allowed_groups=["ops"])
    r = await member_client.post("/api/services/unraid/enter")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_enter_rejects_path_mode(member_client, session):
    await _svc(session)
    r = await member_client.post("/api/services/sonarr/enter")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unavailable_page(client):
    r = await client.get("/api/service-unavailable")
    assert r.status_code == 503 and "text/html" in r.headers["content-type"]


# --- security extras ---

@pytest.mark.asyncio
async def test_anonymous_denied_when_group_required(client, session):
    await _svc(session, allowed_groups=["media"])
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_anonymous_enter_denied(client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso", bypass_rules=[])
    r = await client.post("/api/services/unraid/enter")
    assert r.status_code in (401, 403)
    assert "styx_svc" not in r.headers.get("set-cookie", "")


@pytest.mark.asyncio
async def test_bypass_ignored_unless_sso_with_bypass(client, session):
    await _svc(session, auth_mode="sso")
    r = await client.get("/internal/services/sonarr/auth-check",
                         headers=_fwd("/sonarr/api/v3", **{"X-Api-Key": "k"}))
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_disabled_service_denied_for_anonymous_and_enter(member_client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso",
               bypass_rules=[], enabled=False)
    r = await member_client.post("/api/services/unraid/enter")
    assert r.status_code == 404
    assert "styx_svc" not in r.headers.get("set-cookie", "")


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", ["//evil.com", "//evil.com/x", "/\\evil.com", "https://evil.com",
                                 "/a\\b", "evil.com", "/x\r\nSet-Cookie: a=b"])
async def test_login_redirect_never_open(client, session, uri):
    await _svc(session)
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd(uri))
    assert r.status_code == 302
    loc = r.headers["location"]
    assert loc.startswith("https://localhost/login")
    assert "evil.com" not in loc


@pytest.mark.asyncio
async def test_login_redirect_ignores_untrusted_forwarded_host(client, session):
    await _svc(session)
    h = _fwd("/sonarr/")
    h["x-forwarded-host"] = "evil.com"
    r = await client.get("/internal/services/sonarr/auth-check", headers=h)
    assert "evil.com" not in r.headers["location"]


@pytest.mark.asyncio
@pytest.mark.parametrize("nxt", ["//evil.com", "https://evil.com", "/\\evil.com"])
async def test_exit_ignores_next_param(client, nxt):
    r = await client.get("/_styx/exit", params={"next": nxt}, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"


@pytest.mark.asyncio
@pytest.mark.parametrize("nxt", ["//evil.com", "https://evil.com", "/\\evil.com"])
async def test_enter_ignores_next_param(member_client, session, nxt):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso", bypass_rules=[])
    r = await member_client.post("/api/services/unraid/enter", params={"next": nxt})
    assert r.status_code == 200
    assert "location" not in r.headers


@pytest.mark.asyncio
async def test_cookie_cannot_select_other_service(member_client, session):
    """auth-check keys on the slug Traefik routed to, never on the styx_svc cookie."""
    await _svc(session, slug="secret", allowed_groups=["ops"], auth_mode="sso", bypass_rules=[])
    await _svc(session, slug="open", auth_mode="sso", bypass_rules=[])
    member_client.cookies.set("styx_svc", "secret")
    r = await member_client.get("/internal/services/secret/auth-check", headers=_fwd("/secret/"))
    assert r.status_code == 403
    r = await member_client.get("/internal/services/open/auth-check", headers=_fwd("/x"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_bypass_root_prefix_accepted_pinned(client, session):
    await _svc(session, bypass_rules=[{"path_prefix": "/"}])
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/anything"))
    assert r.status_code == 200
