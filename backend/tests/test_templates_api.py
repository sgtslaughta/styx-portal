import pytest

TEMPLATE_PAYLOAD = {
    "name": "dev-desktop",
    "display_name": "Development Desktop",
    "image": "ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
    "description": "Full Linux desktop",
    "env_vars": {"PUID": "1000"},
    "gpu_enabled": True,
    "gpu_count": 1,
    "memory_limit": "8g",
    "internal_port": 3001,
    "category": "desktop",
    "tags": ["development"],
}


@pytest.mark.asyncio
async def test_create_template(admin_client):
    resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "dev-desktop"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_templates(admin_client):
    await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    resp = await admin_client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "dev-desktop"


@pytest.mark.asyncio
async def test_get_template(admin_client):
    create_resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = await admin_client.get(f"/api/templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "dev-desktop"


@pytest.mark.asyncio
async def test_get_template_not_found(admin_client):
    resp = await admin_client.get("/api/templates/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_template(admin_client):
    create_resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = await admin_client.put(
        f"/api/templates/{template_id}",
        json={"display_name": "Updated Name", "memory_limit": "16g"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"
    assert resp.json()["memory_limit"] == "16g"


@pytest.mark.asyncio
async def test_delete_template(admin_client):
    create_resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = await admin_client.delete(f"/api/templates/{template_id}")
    assert resp.status_code == 204
    resp = await admin_client.get(f"/api/templates/{template_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_template(admin_client):
    await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    resp = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_template_accepts_dind(admin_client):
    payload = {**TEMPLATE_PAYLOAD, "name": "dind-tpl", "dind": True}
    resp = await admin_client.post("/api/templates", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["dind"] is True
