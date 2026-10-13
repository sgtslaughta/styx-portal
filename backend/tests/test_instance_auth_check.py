"""forwardAuth for /i/<sub> instance desktops: Styx login + ownership (spec §10.1)."""
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import select

from app.models import Instance, User

AUTH = "/internal/instances/auth-check"


def _fwd(uri, **h):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate", **h}


async def _inst(session, owner_id, sub="dev", status="running"):
    session.add(Instance(template_id="t", name=sub, subdomain=sub, owner_id=owner_id,
                         status=status))
    await session.commit()


async def _uid(session, username):
    return (await session.exec(select(User).where(User.username == username))).first().id


@pytest.mark.asyncio
async def test_anonymous_navigation_redirects_to_login(client, session):
    await _inst(session, None)
    r = await client.get(AUTH, headers=_fwd("/i/dev/?a=1"))
    assert r.status_code == 302
    u = urlsplit(r.headers["location"])
    assert (u.scheme, u.netloc, u.path) == ("https", "localhost", "/login")
    assert parse_qs(u.query)["next"] == ["/i/dev/?a=1"]


@pytest.mark.asyncio
async def test_anonymous_websocket_or_xhr_401(client, session):
    await _inst(session, None)
    for h in ({"sec-fetch-mode": "websocket"}, {"sec-fetch-mode": "cors", "accept": "*/*"}):
        r = await client.get(AUTH, headers={"x-forwarded-uri": "/i/dev/websocket", **h})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_forged_proxy_cookie_denied(client, session):
    await _inst(session, None)
    r = await client.get(AUTH, headers={**_fwd("/i/dev/"), "cookie": "styx_proxy=forged"})
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_owner_allowed_with_stripped_cookie(member_client, session):
    await _inst(session, await _uid(session, "member"))
    tok = member_client.cookies.get("styx_proxy")
    member_client.cookies.clear()
    r = await member_client.get(AUTH, headers={
        **_fwd("/i/dev/websocket"), "cookie": f"a=1; styx_proxy={tok}; csrf_token=c; b=2"})
    assert r.status_code == 200, r.text
    assert r.headers["cookie"] == "a=1; b=2"


@pytest.mark.asyncio
async def test_other_user_forbidden(second_member_client, session):
    session.add(User(username="owner", password_hash="x", role="member", is_active=True))
    await session.commit()
    await _inst(session, await _uid(session, "owner"))
    r = await second_member_client.get(AUTH, headers=_fwd("/i/dev/"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ownerless_instance_forbidden_for_member(member_client, session):
    await _inst(session, None)
    r = await member_client.get(AUTH, headers=_fwd("/i/dev/"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_allowed_on_any_instance(admin_client, session):
    session.add(User(username="owner", password_hash="x", role="member", is_active=True))
    await session.commit()
    await _inst(session, await _uid(session, "owner"))
    r = await admin_client.get(AUTH, headers=_fwd("/i/dev/"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_extra_port_tunnel_path(member_client, session):
    await _inst(session, await _uid(session, "member"))
    r = await member_client.get(AUTH, headers=_fwd("/i/dev/p/web/x"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_extra_port_direct_subdomain_host(member_client, second_member_client, session):
    await _inst(session, await _uid(session, "member"))
    h = _fwd("/p/web/x", **{"x-forwarded-host": "dev.localhost"})
    assert (await member_client.get(AUTH, headers=h)).status_code == 200
    assert (await second_member_client.get(AUTH, headers=h)).status_code == 403


@pytest.mark.asyncio
async def test_direct_subdomain_anonymous_redirect_has_no_next(client, session):
    await _inst(session, None)
    r = await client.get(AUTH, headers=_fwd("/p/web/", **{"x-forwarded-host": "dev.localhost"}))
    assert r.status_code == 302
    assert r.headers["location"] == "https://localhost/login"


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["stopped", "created", "error"])
async def test_not_running_instance_is_unavailable(member_client, session, status):
    # 5xx is caught by instance-unavailable-errors -> the same page as instances_fallback
    await _inst(session, await _uid(session, "member"), status=status)
    r = await member_client.get(AUTH, headers=_fwd("/i/dev/"))
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_unknown_instance_is_unavailable(member_client):
    r = await member_client.get(AUTH, headers=_fwd("/i/nope/"))
    assert r.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("uri", ["/", "/api/x", "/i/", "/w/dev/", "/i/../api"])
async def test_non_instance_path_forbidden(member_client, uri):
    r = await member_client.get(AUTH, headers=_fwd(uri))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_idle_instance_allowed(member_client, session):
    await _inst(session, await _uid(session, "member"), status="idle")
    r = await member_client.get(AUTH, headers=_fwd("/i/dev/"))
    assert r.status_code == 200
