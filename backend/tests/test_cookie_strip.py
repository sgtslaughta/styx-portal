"""Styx cookies never reach proxied upstreams (spec §10.1).

forwardAuth endpoints return a cleaned `Cookie` header and every forwardAuth
middleware lists `Cookie` in authResponseHeaders, so Traefik replaces the
request's Cookie with the cleaned one before proxying upstream.
"""
import pytest
from sqlmodel import select

from app.models import ProxiedService, User, Workstation
from app.security.cookies import strip_styx_cookies
from app.security.passwords import hash_password
from app.services.route_writer import build_routes_config

PW = "correct horse battery staple"
STYX = "styx_proxy=P; access_token=A; refresh_token=R; csrf_token=C; styx_svc=sonarr"


# --- filter ---

@pytest.mark.parametrize("raw,want", [
    ("a=1; styx_proxy=x; b=2", "a=1; b=2"),
    ("styx_proxy=x", ""),
    ("", ""),
    (STYX, ""),
    ("z=9; " + STYX + "; a=1", "z=9; a=1"),                  # order preserved
    ("styx_proxy2=k; my_access_token=t; xcsrf_token=c", "styx_proxy2=k; my_access_token=t; xcsrf_token=c"),
    ("a=\"q;\"; b=%20x==", "a=\"q; \"; b=%20x=="),           # naive split, values not re-encoded
    ("junk; a=1;;  ; =v; styx_svc=s", "junk; a=1; =v"),       # malformed pairs kept verbatim
    ("  styx_proxy = x ; a=1", "a=1"),                       # whitespace around name
])
def test_strip_styx_cookies(raw, want):
    assert strip_styx_cookies(raw) == want


# --- endpoints ---

@pytest.fixture
def anon(client):
    return client


async def _proxy_token(session, client) -> str:
    session.add(User(username="m", password_hash=hash_password(PW), role="member",
                     is_active=True))
    await session.commit()
    r = await client.post("/api/auth/login", json={"username": "m", "password": PW})
    assert r.status_code == 200, r.text
    tok = client.cookies.get("styx_proxy")
    client.cookies.clear()
    return tok


async def _svc(session, **kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "auth_mode": "sso"}
    d.update(kw)
    session.add(ProxiedService(**d))
    await session.commit()


def _hdr(cookie, uri="/sonarr/", **h):
    return {"x-forwarded-uri": uri, "cookie": cookie, **h}


@pytest.mark.asyncio
async def test_service_auth_check_success_returns_clean_cookie(anon, session):
    await _svc(session)
    tok = await _proxy_token(session, anon)
    r = await anon.get("/internal/services/sonarr/auth-check",
                       headers=_hdr(f"a=1; styx_proxy={tok}; csrf_token=c; b=2"))
    assert r.status_code == 200
    assert r.headers["cookie"] == "a=1; b=2"


@pytest.mark.asyncio
async def test_service_auth_check_empty_when_only_styx(anon, session):
    await _svc(session)
    tok = await _proxy_token(session, anon)
    r = await anon.get("/internal/services/sonarr/auth-check", headers=_hdr(f"styx_proxy={tok}"))
    assert r.status_code == 200
    assert "cookie" in r.headers and r.headers["cookie"] == ""


@pytest.mark.asyncio
async def test_service_bypass_returns_clean_cookie(anon, session):
    await _svc(session, auth_mode="sso-with-bypass",
               bypass_rules=[{"path_prefix": "/sonarr/api", "required_header": None}])
    r = await anon.get("/internal/services/sonarr/auth-check",
                       headers=_hdr("styx_proxy=stolen; k=v", uri="/sonarr/api/x"))
    assert r.status_code == 200
    assert r.headers["cookie"] == "k=v"


@pytest.mark.asyncio
async def test_strip_endpoint_always_200_with_clean_cookie(anon):
    r = await anon.get("/internal/services/anything/strip",
                       headers={"cookie": "z=1; " + STYX + "; a=2"})
    assert r.status_code == 200
    assert r.headers["cookie"] == "z=1; a=2"
    r = await anon.get("/internal/services/anything/strip")
    assert r.status_code == 200
    assert r.headers["cookie"] == ""


@pytest.mark.asyncio
async def test_generic_strip_endpoint(anon):
    r = await anon.get("/internal/strip", headers={"cookie": "styx_proxy=x; sid=1"})
    assert r.status_code == 200
    assert r.headers["cookie"] == "sid=1"


@pytest.mark.asyncio
async def test_workstation_auth_check_returns_clean_cookie(anon, session):
    tok = await _proxy_token(session, anon)
    uid = (await session.exec(select(User))).first().id
    session.add(Workstation(id="w1", name="desk", hostname="desk", subdomain="desk",
                            lan_ip="10.0.0.5", port=8443, all_users=True, created_by=uid))
    await session.commit()
    r = await anon.get("/internal/workstations/w1/auth-check",
                       headers=_hdr(f"x=1; styx_proxy={tok}", uri="/w/desk/"))
    assert r.status_code == 200, r.text
    assert r.headers["cookie"] == "x=1"


# --- routes ---

def _all_cfg():
    inst = {"id": "i1", "subdomain": "d1", "port": 3001, "protocol": "https",
            "extra_ports": [{"slug": "web", "container_port": 8080}]}
    ws = {"id": "w1", "subdomain": "ws1", "lan_ip": "10.0.0.9", "port": 8443, "protocol": "https"}
    svcs = [{"slug": s, "upstream": "http://10.0.0.2:1", "mount_mode": m, "auth_mode": a,
             "verify_tls": True, "enabled": True}
            for s, m, a in [("sonarr", "path", "sso"), ("bz", "path", "sso-with-bypass"),
                            ("plex", "path", "app-native"), ("unraid", "cookie-root", "app-native")]]
    return build_routes_config([inst], "example.com", "tunnel", workstations=[ws], services=svcs)


def test_every_upstream_forward_auth_rewrites_cookie():
    mws = _all_cfg()["http"]["middlewares"]
    fas = {k: v["forwardAuth"] for k, v in mws.items() if "forwardAuth" in v}
    # ip-ban-gate guards the Styx API itself (needs its cookies), no response headers
    fas.pop("ip-ban-gate")
    assert {"svc-auth-sonarr", "svc-auth-bz", "svc-strip-plex", "svc-strip-unraid",
            "ws-auth-w1", "inst-auth-i1"} <= set(fas)
    for name, fa in fas.items():
        assert "Cookie" in fa["authResponseHeaders"], name
    assert mws["svc-auth-sonarr"]["forwardAuth"]["authResponseHeaders"] == [
        "X-Styx-User", "X-Styx-Groups", "Cookie"]
    assert mws["svc-strip-plex"]["forwardAuth"]["address"] == \
        "http://backend:8000/internal/services/plex/strip"
    assert mws["inst-auth-i1"]["forwardAuth"]["address"] == \
        "http://backend:8000/internal/instances/i1/auth-check"


def test_every_proxied_router_strips_cookies():
    routers = _all_cfg()["http"]["routers"]
    expect = {"svc-sonarr": "svc-auth-sonarr", "svc-bz": "svc-auth-bz",
              "svc-plex": "svc-strip-plex", "svc-unraid": "svc-strip-unraid",
              "ws-w1": "ws-auth-w1", "i1": "inst-auth-i1",
              "i1-p-web": "inst-auth-i1"}
    for rid, mw in expect.items():
        assert mw in routers[rid]["middlewares"], rid
    # every non-Styx upstream router is covered
    upstream = {k for k, r in routers.items() if r["service"] not in ("api", "frontend")}
    assert upstream == set(expect)
