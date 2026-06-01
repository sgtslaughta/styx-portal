from unittest.mock import patch, MagicMock

import pytest

MOCK_LSIO_RESPONSE = [
    {
        "name": "firefox",
        "description": "Firefox browser in a container",
        "project_logo": "https://raw.githubusercontent.com/linuxserver/docker-templates/master/linuxserver.io/img/firefox-logo.png",
        "category": "Productivity",
        "stars": 120,
        "monthly_pulls": 500000,
        "version": "v1.0.0-ls50",
        "stable": True,
        "config": {
            "env_vars": [
                {"name": "PUID", "default": "1000", "description": "User ID"},
                {"name": "PGID", "default": "1000", "description": "Group ID"},
            ],
            "volumes": [{"container": "/config", "description": "Config directory"}],
            "ports": [{"container": "3000", "description": "Web UI"}],
        },
        "architectures": [{"arch": "x86_64", "tag": "amd64-latest"}],
        "github_url": "https://github.com/linuxserver/docker-firefox",
        "project_url": "https://www.mozilla.org/firefox/",
    },
    {
        "name": "wireguard",
        "description": "WireGuard VPN",
        "project_logo": "https://example.com/wg.png",
        "category": "Network",
        "stars": 200,
        "monthly_pulls": 800000,
        "version": "v1.0.0-ls10",
        "stable": True,
        "config": {"env_vars": [], "volumes": [], "ports": []},
        "architectures": [],
        "github_url": "https://github.com/linuxserver/docker-wireguard",
        "project_url": "https://www.wireguard.com/",
    },
]


@patch("app.routers.registry.httpx")
@pytest.mark.asyncio
async def test_list_registry_images(mock_httpx, admin_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = await admin_client.get("/api/registry/images")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["name"] == "firefox"


@patch("app.routers.registry.httpx")
@pytest.mark.asyncio
async def test_list_registry_filter_category(mock_httpx, admin_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = await admin_client.get("/api/registry/images?category=Network")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "wireguard"


@patch("app.routers.registry.httpx")
@pytest.mark.asyncio
async def test_list_registry_search(mock_httpx, admin_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = await admin_client.get("/api/registry/images?search=fire")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "firefox"


@patch("app.routers.registry.httpx")
@pytest.mark.asyncio
async def test_get_registry_image(mock_httpx, admin_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = await admin_client.get("/api/registry/images/firefox")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "firefox"
    assert "config" in data


@patch("app.routers.registry.httpx")
@pytest.mark.asyncio
async def test_get_registry_image_not_found(mock_httpx, admin_client):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = MOCK_LSIO_RESPONSE
    mock_httpx.get.return_value = mock_response

    resp = await admin_client.get("/api/registry/images/nonexistent")
    assert resp.status_code == 404
