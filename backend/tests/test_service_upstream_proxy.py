"""upstream_is_proxy: serve apps that sit behind a name-based reverse proxy (NPM, Caddy, ...)."""
import httpx
import pytest
import sqlalchemy
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import _run_migrations
from app.models import ProxiedService
from app.schemas import ProxiedServiceCreate, ProxiedServiceUpdate
from app.services import service_favicon as sf
from app.services.route_writer import build_routes_config
from app.services.service_health import check_url, run_health_pass


def _body(**kw):
    d = {"slug": "g", "name": "G", "kind": "url", "upstream_url": "https://192.168.1.96"}
    d.update(kw)
    return d


URL = "https://unraid.home.lan"


@pytest.mark.parametrize("url", [URL, "http://nas:8080/x", "https://a.b.c/p"])
def test_proxy_accepts_dns_names(url):
    assert ProxiedServiceCreate(**_body(upstream_url=url, upstream_is_proxy=True)).upstream_is_proxy
    assert ProxiedServiceUpdate(**{k: v for k, v in _body(upstream_url=url, upstream_is_proxy=True)
                                   .items() if k != "slug"}).upstream_is_proxy


def test_proxy_defaults_false():
    assert ProxiedServiceCreate(**_body()).upstream_is_proxy is False


@pytest.mark.parametrize("url", ["https://192.168.1.96", "http://10.0.0.1:8080/x", "https://[::1]:8443"])
def test_proxy_rejects_ip_literal(url):
    with pytest.raises(ValidationError, match="picks the site by hostname"):
        ProxiedServiceCreate(**_body(upstream_url=url, upstream_is_proxy=True))
    ProxiedServiceCreate(**_body(upstream_url=url))      # fine when the switch is off


def test_proxy_only_for_url_kind():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_body(kind="docker-local", upstream_url=None, container="c",
                                     container_port=80, upstream_is_proxy=True))


def _svc(**kw):
    d = {"slug": "g", "upstream": "https://unraid.home.lan", "mount_mode": "path",
         "auth_mode": "sso", "verify_tls": True, "enabled": True}
    d.update(kw)
    return d


def _cfg(**kw):
    return build_routes_config([], "example.com", "tunnel", services=[_svc(**kw)])["http"]


@pytest.mark.parametrize("verify", [True, False])
def test_routes_with_upstream_proxy(verify):
    h = _cfg(upstream_host="unraid.home.lan", verify_tls=verify)
    assert h["middlewares"]["svc-host-g"] == {"headers": {
        "customRequestHeaders": {"Host": "unraid.home.lan"}}}
    mws = h["routers"]["svc-g"]["middlewares"]
    assert mws[-1] == "svc-host-g" and mws[-2] == "svc-auth-g"
    assert h["services"]["svc-g"]["loadBalancer"]["serversTransport"] == "styx-up-g"
    assert h["serversTransports"]["styx-up-g"] == {
        "serverName": "unraid.home.lan", "insecureSkipVerify": not verify}
    assert "styx-insecure-upstream" not in h.get("serversTransports", {})


def test_routes_without_upstream_proxy_unchanged():
    for extra in ({}, {"upstream_host": None}):
        h = _cfg(**extra)
        assert "svc-host-g" not in h["middlewares"]
        assert "svc-host-g" not in h["routers"]["svc-g"]["middlewares"]
        assert "serversTransport" not in h["services"]["svc-g"]["loadBalancer"]
        assert "styx-up-g" not in h.get("serversTransports", {})


@pytest.mark.asyncio
async def test_migration_adds_upstream_is_proxy_column():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE proxied_services (id TEXT PRIMARY KEY, icon TEXT)"))
        for _ in range(2):
            await _run_migrations(conn)
        cols = {r[1] for r in (await conn.execute(
            sqlalchemy.text("PRAGMA table_info(proxied_services)"))).fetchall()}
    assert "upstream_is_proxy" in cols


@pytest.mark.asyncio
async def test_check_url_sends_host_and_sni():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.headers["host"], req.extensions.get("sni_hostname")))
        return httpx.Response(200)

    t = httpx.MockTransport(handler)
    assert await check_url("https://10.0.0.1/", True, transport=t,
                           upstream_host="g.jmolabs.dev") == "healthy"
    assert await check_url("https://10.0.0.1/", True, transport=t) == "healthy"
    assert seen == [("g.jmolabs.dev", "g.jmolabs.dev"), ("10.0.0.1", None)]


@pytest.mark.asyncio
async def test_health_pass_threads_proxy_hostname(session):
    session.add(ProxiedService(slug="a", name="A", upstream_url="https://unraid.home.lan",
                               health_path="/", upstream_is_proxy=True))
    await session.commit()
    seen = []

    async def fake(url, verify, upstream_host=None):
        seen.append((url, upstream_host))
        return "healthy"

    await run_health_pass(session, checker=fake)
    assert seen == [("https://unraid.home.lan/", "unraid.home.lan")]


@pytest.mark.asyncio
async def test_favicon_probes_send_host_and_sni():
    seen = []
    page = b'<html><head><link rel="icon" href="/i.svg"></head></html>'
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
           b'<rect width="1" height="1"/></svg>')

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((req.headers["host"], req.extensions.get("sni_hostname")))
        return httpx.Response(200, content=svg if req.url.path == "/i.svg" else page)

    svc = ProxiedService(slug="g", name="G", upstream_url="https://unraid.home.lan", mount_mode="cookie-root",
                         upstream_is_proxy=True)
    out = await sf.fetch_favicon(svc, None, transport=httpx.MockTransport(handler))
    assert out and out.startswith("data:image/svg")      # same-origin filter still resolves it
    assert seen and set(seen) == {("unraid.home.lan", "unraid.home.lan")}


@pytest.mark.asyncio
async def test_api_round_trip(admin_client, monkeypatch):
    async def noop(session, **kw):
        return None
    monkeypatch.setattr("app.services.route_writer.refresh_routes_from_db", noop)
    body = _body(upstream_url=URL, upstream_is_proxy=True)
    r = await admin_client.post("/api/services", json=body)
    assert r.status_code == 201, r.text
    assert r.json()["upstream_is_proxy"] is True
    sid = r.json()["id"]
    put = {k: v for k, v in body.items() if k != "slug"}
    r = await admin_client.put(f"/api/services/{sid}", json={**put, "upstream_is_proxy": False})
    assert r.status_code == 200 and r.json()["upstream_is_proxy"] is False
    r = await admin_client.put(f"/api/services/{sid}", json={**put, "upstream_url": "https://10.0.0.1"})
    assert r.status_code == 422
    r = await admin_client.put(f"/api/services/{sid}", json={
        **put, "kind": "docker-local", "upstream_url": None, "container": "c",
        "container_port": 80})
    assert r.status_code == 422


def test_route_writer_derives_hostname_for_url_kind_only():
    from app.services.route_writer import _service_dict
    s = ProxiedService(slug="c", name="C", upstream_url="https://Unraid.Home.LAN:8443/",
                       upstream_is_proxy=True)
    assert _service_dict(s)["upstream_host"] == "unraid.home.lan"
    s = ProxiedService(slug="c", name="C", kind="docker-local", container="c", container_port=80,
                       upstream_is_proxy=True)
    assert _service_dict(s)["upstream_host"] is None
    assert _service_dict(ProxiedService(slug="c", name="C", upstream_url=URL))["upstream_host"] is None
