import pytest


@pytest.mark.asyncio
async def test_security_headers_present(client):
    r = await client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert "Strict-Transport-Security" in r.headers
