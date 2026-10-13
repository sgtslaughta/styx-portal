"""Security-review fixes for the service proxy (cookie-root loop, session expiry, bypass)."""
from urllib.parse import parse_qs, urlsplit

import pytest

from app.models import ProxiedService

AUTH = "/api/services/{slug}/auth-check"


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
