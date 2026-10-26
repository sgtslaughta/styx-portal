import pytest
from tests.helpers_setup import st


@pytest.mark.asyncio
async def test_preflight_available_before_setup(client):
    r = await client.get("/api/auth/setup-preflight")
    assert r.status_code == 200
    body = r.json()
    assert "docker" in body and "deploy_mode" in body and "domain_set" in body and "data_writable" in body


@pytest.mark.asyncio
async def test_preflight_404_after_user_exists(client):
    r = await client.post("/api/auth/setup", json={**st(), 
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    r2 = await client.get("/api/auth/setup-preflight")
    assert r2.status_code == 404


@pytest.mark.asyncio
async def test_preflight_reports_k8s_api_on_k8s(client, monkeypatch):
    from app.services import diagnostics

    class K:
        def get_json(self, path, params=None):
            return {"gitVersion": "v1.31.2"}
    monkeypatch.setenv("ROUTE_BACKEND", "k8s")
    monkeypatch.setattr(diagnostics, "incluster_client", lambda: K())
    body = (await client.get("/api/auth/setup-preflight")).json()
    assert body["docker"] == {"ok": True, "detail": "Kubernetes v1.31.2"}
    assert body["runtime"] == "kubernetes"
