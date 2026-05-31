import pytest


@pytest.mark.asyncio
async def test_instance_unavailable_page(client):
    resp = await client.get("/api/instance-unavailable")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    # JS derives subdomain from the path and redirects to /?stopped=...
    assert "location.replace" in body
    assert "/i/" in body
    assert "stopped=" in body
    # no-JS fallback to My Instances
    assert 'href="/"' in body
