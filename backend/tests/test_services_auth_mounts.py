import pytest
from sqlmodel import select
from app.models import ProxiedService
from app.routers.services_auth import bypass_matches

JF = [{"path_prefix": "/jellyfin/", "required_header": "Authorization", "header_prefix": "MediaBrowser"},
      {"path_prefix": "/jellyfin/", "required_header": "X-Emby-Token"},
      {"path_prefix": "/jellyfin/", "required_query": "api_key"}]


@pytest.mark.parametrize("uri,headers,ok", [
    ("/jellyfin/Users", {"authorization": 'MediaBrowser Client="x", Token="t"'}, True),
    ("/jellyfin/Users", {"authorization": "Bearer t"}, False),
    ("/jellyfin/Users", {"authorization": ""}, False),
    ("/jellyfin/Users", {"x-emby-token": "abc"}, True),
    ("/jellyfin/Users", {"x-emby-token": "  "}, False),
    ("/jellyfin/Videos/1/stream?api_key=abc", {}, True),
    ("/jellyfin/Videos/1/stream?api_key=", {}, False),
    ("/jellyfin/Videos/1/stream?other=1", {}, False),
    ("/sonarr/api", {"x-emby-token": "abc"}, False),
])
def test_bypass(uri, headers, ok):
    assert bypass_matches(JF, uri, headers) is ok


def test_query_only_rule_needs_param():
    rules = [{"path_prefix": "/x/", "required_query": "k"}]
    assert bypass_matches(rules, "/x/a", {}) is False
    assert bypass_matches(rules, "/x/a?k=1", {}) is True


def test_unconditional_prefix_bypass_kept():
    assert bypass_matches([{"path_prefix": "/x/"}], "/x/a", {}) is True


async def _svc(session, **kw):
    d = {"slug": "graf", "name": "Graf", "upstream_url": "http://g"}
    d.update(kw)
    s = ProxiedService(**d)
    session.add(s)
    await session.commit()
    return s


async def test_identity_headers_only_when_opted_in(admin_client, session):
    await _svc(session)
    await _svc(session, slug="graf2", pass_identity=True)
    r = await admin_client.get("/internal/services/graf/auth-check", headers={"x-forwarded-uri": "/graf/"})
    assert r.status_code == 200 and "x-styx-user" not in r.headers
    r = await admin_client.get("/internal/services/graf2/auth-check", headers={"x-forwarded-uri": "/graf2/"})
    assert r.headers["x-styx-user"] == "admin" and "x-styx-email" in r.headers and "x-styx-groups" in r.headers


async def test_open_same_origin_sets_cookie_and_redirects(admin_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root")
    r = await admin_client.get("/_styx/open/immich", headers={"sec-fetch-site": "same-origin"},
                               follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("/_styx/app/immich/")
    svc = (await session.exec(select(ProxiedService).where(ProxiedService.slug == "immich"))).one()
    assert f"styx_svc=immich.{svc.id.replace('-', '')[:12]}" in r.headers["set-cookie"] and r.headers["clear-site-data"] == '"cache"'
    await _svc(session, slug="ha", mount_mode="cookie-root", frame_ok=False)
    r2 = await admin_client.get("/_styx/open/ha", headers={"sec-fetch-site": "none"}, follow_redirects=False)
    assert r2.headers["location"].endswith("/") and "/_styx/app" not in r2.headers["location"]


@pytest.mark.parametrize("h", [{"sec-fetch-site": "cross-site"}, {"sec-fetch-site": "same-site"}, {}])
async def test_open_cross_site_or_missing_header_shows_confirm_unauthenticated(client, h):
    r = await client.get("/_styx/open/immich", headers=h)
    assert r.status_code == 200 and 'href="/_styx/open/immich"' in r.text
    assert "set-cookie" not in r.headers


async def test_open_confirm_rejects_invalid_slug(client):
    assert (await client.get("/_styx/open/<b>x", headers={})).status_code == 404


async def test_open_anonymous_same_origin_clears_focus_via_exit(client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root")
    r = await client.get("/_styx/open/immich", headers={"sec-fetch-site": "same-origin",
                                                       "accept": "text/html", "sec-fetch-mode": "navigate"},
                         follow_redirects=False)
    assert r.status_code == 302 and "/_styx/exit?next=" in r.headers["location"]
    assert "/_styx/open" not in r.headers["location"]


def test_bypass_fragment_before_query_no_crash():
    rules = [{"path_prefix": "/j/", "required_query": "api_key"}]
    assert bypass_matches(rules, "/j/x#?api_key=1", {}) is False


async def test_focus_reports_cookie(admin_client, session):
    assert (await admin_client.get("/api/services/focus")).json() == {"slug": None}
    s = await _svc(session, slug="immich", mount_mode="cookie-root")
    tok = s.id.replace("-", "")[:12]
    for stale in ("immich", "immich.ffffffffffff", "nope." + tok, "garbage"):
        admin_client.cookies.set("styx_svc", stale)
        assert (await admin_client.get("/api/services/focus")).json() == {"slug": None}
    admin_client.cookies.set("styx_svc", f"immich.{tok}")
    assert (await admin_client.get("/api/services/focus")).json() == {"slug": "immich"}


async def test_open_denied_without_group(member_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root", allowed_groups=["family"])
    r = await member_client.get("/_styx/open/immich", headers={"sec-fetch-site": "same-origin",
                                                              "accept": "text/html"})
    assert r.status_code == 403
