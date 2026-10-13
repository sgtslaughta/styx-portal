"""forwardAuth for instance desktops: Styx login + ownership (spec §10.1).

The instance is bound by the forwardAuth address route_writer emits per
instance (/internal/instances/<id>/auth-check), never parsed from the request.
"""
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlmodel import select

from app.models import Instance, User


def auth(iid="i-dev"):
    return f"/internal/instances/{iid}/auth-check"


def _fwd(uri, **h):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate", **h}


async def _inst(session, owner_id, sub="dev", status="running"):
    session.add(Instance(id=f"i-{sub}", template_id="t", name=sub, subdomain=sub,
                         owner_id=owner_id, status=status))
    await session.commit()


async def _uid(session, username):
    return (await session.exec(select(User).where(User.username == username))).first().id


async def _owner(session):
    session.add(User(username="owner", password_hash="x", role="member", is_active=True))
    await session.commit()
    return await _uid(session, "owner")


@pytest.mark.asyncio
async def test_anonymous_navigation_redirects_to_login(client, session):
    await _inst(session, None)
    r = await client.get(auth(), headers=_fwd("/i/dev/?a=1"))
    assert r.status_code == 302
    u = urlsplit(r.headers["location"])
    assert (u.scheme, u.netloc, u.path) == ("https", "localhost", "/login")
    assert parse_qs(u.query)["next"] == ["/i/dev/?a=1"]


@pytest.mark.asyncio
async def test_anonymous_websocket_or_xhr_401(client, session):
    await _inst(session, None)
    for h in ({"sec-fetch-mode": "websocket"}, {"sec-fetch-mode": "cors", "accept": "*/*"}):
        r = await client.get(auth(), headers={"x-forwarded-uri": "/i/dev/websocket", **h})
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_forged_proxy_cookie_denied(client, session):
    await _inst(session, None)
    r = await client.get(auth(), headers={**_fwd("/i/dev/"), "cookie": "styx_proxy=forged"})
    assert r.status_code == 302


@pytest.mark.asyncio
async def test_host_routed_anonymous_redirect_has_no_next(client, session):
    await _inst(session, None)
    r = await client.get(auth(), headers=_fwd("/p/web/", **{"x-forwarded-host": "dev.localhost"}))
    assert r.status_code == 302
    assert r.headers["location"] == "https://localhost/login"


@pytest.mark.asyncio
async def test_anonymous_unsafe_next_dropped(client, session):
    await _inst(session, None)
    r = await client.get(auth(), headers=_fwd("/i/dev/%2e%2e/%2e%2e/api/x"))
    assert r.headers["location"] == "https://localhost/login"


@pytest.mark.asyncio
async def test_owner_allowed_with_stripped_cookie(member_client, session):
    await _inst(session, await _uid(session, "member"))
    tok = member_client.cookies.get("styx_proxy")
    member_client.cookies.clear()
    r = await member_client.get(auth(), headers={
        **_fwd("/i/dev/websocket"), "cookie": f"a=1; styx_proxy={tok}; csrf_token=c; b=2"})
    assert r.status_code == 200, r.text
    assert r.headers["cookie"] == "a=1; b=2"


@pytest.mark.asyncio
async def test_other_user_forbidden(second_member_client, session):
    await _inst(session, await _owner(session))
    r = await second_member_client.get(auth(), headers=_fwd("/i/dev/"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_ownerless_instance_forbidden_for_member(member_client, session):
    await _inst(session, None)
    r = await member_client.get(auth(), headers=_fwd("/i/dev/"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_allowed_on_any_instance(admin_client, session):
    await _inst(session, await _owner(session))
    r = await admin_client.get(auth(), headers=_fwd("/i/dev/"))
    assert r.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["stopped", "created", "error"])
async def test_not_running_instance_is_unavailable(member_client, session, status):
    # 5xx is caught by instance-unavailable-errors -> the same page as instances_fallback
    await _inst(session, await _uid(session, "member"), status=status)
    r = await member_client.get(auth(), headers=_fwd("/i/dev/"))
    assert r.status_code == 503


@pytest.mark.asyncio
async def test_idle_instance_allowed(member_client, session):
    await _inst(session, await _uid(session, "member"), status="idle")
    r = await member_client.get(auth(), headers=_fwd("/i/dev/"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_unknown_instance_id_fails_closed(member_client):
    r = await member_client.get(auth("nope"), headers=_fwd("/i/nope/"))
    assert r.status_code == 503


# --- request parsing never selects the instance (parser-differential proof) ---

TRICKY = [
    {"x-forwarded-uri": "/i/mine/"},
    {"x-forwarded-uri": "/i/mine/../victim/"},
    {"x-forwarded-uri": "/i/victim/../mine/"},
    {"x-forwarded-uri": "/i/mine%2f..%2fvictim/"},
    {"x-forwarded-uri": "//i/mine/"},
    {"x-forwarded-uri": "/I/MINE/"},
    {"x-forwarded-uri": "/i/victim/?x=/i/mine/"},
    {"x-forwarded-uri": "https://localhost/i/mine/"},
    {"x-forwarded-uri": "/p/web/", "x-forwarded-host": "mine.localhost"},
    {"x-forwarded-uri": "/p/web/", "x-forwarded-host": "MINE.localhost.:443"},
    {"x-forwarded-uri": "/i/mine/../../p/web", "x-forwarded-host": "mine.localhost"},
]


@pytest.mark.asyncio
@pytest.mark.parametrize("hdrs", TRICKY)
async def test_victim_router_denies_whatever_the_request_says(member_client, session, hdrs):
    """The member owns "mine"; "victim" is someone else's. On victim's router
    (its auth address) no forwarded path/host can borrow mine's ownership."""
    await _inst(session, await _uid(session, "member"), sub="mine")
    await _inst(session, await _owner(session), sub="victim")
    r = await member_client.get(auth("i-victim"), headers={"sec-fetch-mode": "navigate", **hdrs})
    assert r.status_code == 403
    r = await member_client.get(auth("i-mine"), headers={"sec-fetch-mode": "navigate", **hdrs})
    assert r.status_code == 200
