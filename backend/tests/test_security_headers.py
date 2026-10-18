import pytest


@pytest.mark.asyncio
async def test_security_headers_present(client):
    r = await client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert "Strict-Transport-Security" in r.headers


SAMEORIGIN_CSP = "frame-ancestors 'self'"


@pytest.mark.asyncio
async def test_unavailable_page_is_frameable_by_styx(client):
    r = await client.get("/api/service-unavailable")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert SAMEORIGIN_CSP in r.headers["Content-Security-Policy"]
    assert "'none'" not in r.headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_no_access_page_is_frameable_by_styx(member_client, session):
    from tests.test_no_access_page import NAV, _svc
    await _svc(session)
    r = await member_client.get("/internal/services/sonarr/auth-check", headers=NAV)
    assert r.status_code == 403
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert SAMEORIGIN_CSP in r.headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_open_confirm_page_is_frameable_by_styx(client):
    r = await client.get("/_styx/open/immich")
    assert r.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert SAMEORIGIN_CSP in r.headers["Content-Security-Policy"]


@pytest.mark.asyncio
async def test_api_json_stays_deny(client):
    r = await client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
