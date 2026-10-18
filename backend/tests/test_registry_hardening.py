"""B4/B5: registry URL filtering and negative cache."""
from unittest.mock import MagicMock, patch

import httpx


# ---- B4 / B5 ----------------------------------------------------------
def _resp(data):
    m = MagicMock()
    m.json.return_value = data
    return m


@patch("app.routers.registry.httpx")
async def test_registry_strips_non_https_urls(mock_httpx, admin_client):
    from app.routers import registry
    registry._cache.update(data=None, fetched_at=0, failed_at=0)
    mock_httpx.HTTPError = httpx.HTTPError
    mock_httpx.get.return_value = _resp([{
        "name": "x", "project_url": "javascript:alert(1)", "github_url": "https://github.com/a",
        "project_logo": "data:text/html,hi"}])
    r = await admin_client.get("/api/registry/images/x")
    body = r.json()
    assert body["project_url"] is None and body["project_logo"] is None
    assert body["github_url"] == "https://github.com/a"


@patch("app.routers.registry.httpx")
async def test_registry_negative_cache(mock_httpx, admin_client):
    from app.routers import registry
    registry._cache.update(data=None, fetched_at=0, failed_at=0)
    mock_httpx.HTTPError = httpx.HTTPError
    mock_httpx.get.side_effect = httpx.ConnectError("down")
    for _ in range(3):
        assert (await admin_client.get("/api/registry/images")).status_code == 502
    assert mock_httpx.get.call_count == 1


