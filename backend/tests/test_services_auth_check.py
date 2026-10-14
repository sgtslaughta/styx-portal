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
    await _svc(session, pass_identity=True)
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-user"] == "member"


@pytest.mark.asyncio
async def test_member_denied_then_allowed_by_group(member_client, session):
    await _svc(session, allowed_groups=["media"], pass_identity=True)
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
async def test_bypass_ignored_unless_sso_with_bypass(client, session):
    await _svc(session, auth_mode="sso")
    r = await client.get("/internal/services/sonarr/auth-check",
                         headers=_fwd("/sonarr/api/v3", **{"X-Api-Key": "k"}))
    assert r.status_code == 302


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


@pytest.mark.asyncio
async def test_exit_clears_focus_cookie(member_client):
    r = await member_client.get("/_styx/exit", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    assert "styx_svc=;" in r.headers["set-cookie"] or 'styx_svc=""' in r.headers["set-cookie"]


def _frame(uri, **h):
    return _fwd(uri, **{"sec-fetch-dest": "iframe", **h})


@pytest.mark.asyncio
@pytest.mark.parametrize("dest", ["iframe", "frame"])
async def test_framed_expiry_gets_sameorigin_page_with_top_link(client, session, dest):
    await _svc(session, auth_mode="sso", bypass_rules=[])
    h = _fwd("/sonarr/series?page=2", **{"sec-fetch-dest": dest})
    r = await client.get("/internal/services/sonarr/auth-check", headers=h)
    assert r.status_code == 401 and r.headers["content-type"].startswith("text/html")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in r.headers["Content-Security-Policy"]
    assert "<script" not in r.text and "Your session expired" in r.text
    assert 'target="_top"' in r.text
    assert 'href="/login?next=%2F_styx%2Fapp%2Fsonarr%2Fseries%3Fpage%3D2"' in r.text


@pytest.mark.asyncio
async def test_framed_expiry_cookie_root_maps_into_shell_and_clears_focus(client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root", auth_mode="sso", bypass_rules=[])
    r = await client.get("/internal/services/immich/auth-check", headers=_frame("/photos"))
    assert r.status_code == 401
    nxt = "%2Flogin%3Fnext%3D%252F_styx%252Fapp%252Fimmich%252Fphotos"
    assert f'href="/_styx/exit?next={nxt}"' in r.text


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", ["//evil.com", "/\\evil.com", "https://evil.com", "/a/%2e%2e/b"])
async def test_framed_expiry_next_is_sanitized(client, session, uri):
    await _svc(session, auth_mode="sso", bypass_rules=[])
    r = await client.get("/internal/services/sonarr/auth-check", headers=_frame(uri))
    assert r.status_code == 401
    assert "evil" not in r.text and 'href="/login"' in r.text


@pytest.mark.asyncio
async def test_unframed_expiry_still_redirects(client, session):
    await _svc(session, auth_mode="sso", bypass_rules=[])
    r = await client.get("/internal/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 302
