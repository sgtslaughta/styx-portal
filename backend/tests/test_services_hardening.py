"""J: low-severity hardening (member list model, health targets, health races, CORS)."""
import pytest
from sqlmodel import delete, select

from app.models import ProxiedService
from app.services.service_health import check_url, run_health_pass

MEMBER_KEYS = {"id", "slug", "name", "icon_kind", "icon_etag", "mount_mode", "enabled", "up", "frame_ok",
               "needs_setup"}


@pytest.mark.asyncio
async def test_member_list_is_reduced(member_client, session):
    for slug, status in [("a", "healthy"), ("b", "unhealthy"), ("c", "unknown")]:
        session.add(ProxiedService(slug=slug, name=slug, kind="docker-local", container="x",
                                   container_port=1, upstream_fallback="http://h:1",
                                   health_status=status))
    await session.commit()
    r = await member_client.get("/api/services")
    assert r.status_code == 200
    rows = r.json()
    assert all(set(row) == MEMBER_KEYS for row in rows)
    assert [row["up"] for row in rows] == [True, False, None]


@pytest.mark.asyncio
async def test_admin_list_is_full(admin_client, session):
    session.add(ProxiedService(slug="a", name="a", upstream_url="http://10.0.0.2"))
    await session.commit()
    row = (await admin_client.get("/api/services")).json()[0]
    assert row["upstream_url"] == "http://10.0.0.2" and "bypass_rules" in row


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["http://169.254.169.254/latest/meta-data",
                                 "http://169.254.0.1:8080/x", "http://[fe80::1]/x",
                                 "http://[fd00:ec2::254]/"])
async def test_health_refuses_link_local_and_metadata(url):
    import httpx
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(200)
    assert await check_url(url, True, transport=httpx.MockTransport(handler)) == "unhealthy"
    assert calls == []


@pytest.mark.asyncio
async def test_health_pass_tolerates_row_deleted_mid_pass(session):
    keep = ProxiedService(slug="keep", name="K", upstream_url="http://10.0.0.1", health_path="/")
    gone = ProxiedService(slug="gone", name="G", upstream_url="http://10.0.0.2", health_path="/")
    session.add(keep)
    session.add(gone)
    await session.commit()
    gone_id = gone.id

    async def checker(url, verify):
        if "10.0.0.2" in url:
            await session.exec(delete(ProxiedService).where(ProxiedService.id == gone_id))
            await session.commit()
        return "healthy"

    await run_health_pass(session, checker=checker)
    rows = (await session.exec(select(ProxiedService))).all()
    assert [(s.slug, s.health_status) for s in rows] == [("keep", "healthy")]


@pytest.mark.asyncio
async def test_cors_allows_styx_client_header(client):
    r = await client.options("/api/services", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-Styx-Client"})
    assert r.status_code == 200
    assert "x-styx-client" in r.headers["access-control-allow-headers"].lower()
