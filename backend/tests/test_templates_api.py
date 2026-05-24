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


def test_create_template(client):
    resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "dev-desktop"
    assert data["id"] is not None


def test_list_templates(client):
    client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    resp = client.get("/api/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "dev-desktop"


def test_get_template(client):
    create_resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = client.get(f"/api/templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "dev-desktop"


def test_get_template_not_found(client):
    resp = client.get("/api/templates/nonexistent")
    assert resp.status_code == 404


def test_update_template(client):
    create_resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = client.put(
        f"/api/templates/{template_id}",
        json={"display_name": "Updated Name", "memory_limit": "16g"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"
    assert resp.json()["memory_limit"] == "16g"


def test_delete_template(client):
    create_resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    template_id = create_resp.json()["id"]
    resp = client.delete(f"/api/templates/{template_id}")
    assert resp.status_code == 204
    resp = client.get(f"/api/templates/{template_id}")
    assert resp.status_code == 404


def test_create_duplicate_template(client):
    client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    resp = client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    assert resp.status_code == 409
