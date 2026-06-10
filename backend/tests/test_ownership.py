import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


TEMPLATE_PAYLOAD = {
    "name": "test-tmpl",
    "display_name": "Test Template",
    "image": "test:latest",
    "internal_port": 3001,
    "env_vars": {"PUID": "1000"},
    "volumes": [{"name": "{instance_id}-home", "mount": "/config"}],
    "session_config": {
        "idle_timeout": "30m",
        "grace_period": "5m",
        "timeout_action": "stop",
        "never_timeout": False,
        "max_session_duration": None,
    },
}


@pytest.mark.asyncio
async def test_user_sees_only_own_instances(admin_client):
    """Admin creates a template and instance, then a second user sees nothing."""
    # admin creates a template
    tmpl = await admin_client.post("/api/templates", json=TEMPLATE_PAYLOAD)
    assert tmpl.status_code == 201, tmpl.text
    template_id = tmpl.json()["id"]

    # admin creates an instance owned by admin
    inst = await admin_client.post(
        "/api/instances",
        json={"template_id": template_id, "name": "admin-instance", "subdomain": "admin"},
    )
    assert inst.status_code == 201, inst.text

    # admin sees their instance
    admin_view = await admin_client.get("/api/instances")
    assert admin_view.status_code == 200
    assert len(admin_view.json()) >= 1

    # invite a second user and accept in a fresh client sharing the same app/DB
    inv = (await admin_client.post("/api/users/invites", json={"role": "user"})).json()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as bob:
        # Bootstrap CSRF for bob
        csrf_r = await bob.get("/api/auth/csrf")
        assert csrf_r.status_code == 200
        csrf = bob.cookies.get("csrf_token")
        assert csrf
        bob.headers.update({"X-CSRF-Token": csrf})

        r = await bob.post(
            "/api/auth/accept-invite",
            json={"token": inv["token"], "username": "bob", "password": "bobs long password"},
        )
        assert r.status_code == 201, r.text
        bob_view = await bob.get("/api/instances")
        assert bob_view.status_code == 200
        assert bob_view.json() == []
