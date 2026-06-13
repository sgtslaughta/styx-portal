"""Test admin gating for risk fields in template create/update."""
import pytest


@pytest.mark.asyncio
async def test_non_admin_cannot_set_privileged(member_client):
    """Non-admin cannot create template with privileged=True."""
    r = await member_client.post("/api/templates", json={
        "name": "p", "display_name": "P", "image": "img", "privileged": True})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_set_devices(member_client):
    """Non-admin cannot create template with devices."""
    r = await member_client.post("/api/templates", json={
        "name": "d", "display_name": "D", "image": "img",
        "devices": ["/dev/dri:/dev/dri"]})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_bad_extra_args_rejected(member_client):
    """Non-admin cannot set admin-only extra_docker_args like network_mode."""
    r = await member_client.post("/api/templates", json={
        "name": "e", "display_name": "E", "image": "img",
        "extra_docker_args": {"network_mode": "host"}})
    assert r.status_code in (400, 403)


@pytest.mark.asyncio
async def test_admin_can_set_risk_fields(admin_client):
    """Admin can create template with risk fields."""
    r = await admin_client.post("/api/templates", json={
        "name": "ok", "display_name": "OK", "image": "img",
        "privileged": True, "devices": ["/dev/dri:/dev/dri"],
        "extra_docker_args": {"hostname": "box"}})
    assert r.status_code == 201


@pytest.mark.asyncio
async def test_non_admin_cannot_update_to_privileged(member_client):
    """Non-admin cannot update own template to set privileged."""
    # Create a plain template
    create_resp = await member_client.post(
        "/api/templates",
        json={
            "name": "plain-template",
            "display_name": "Plain",
            "image": "img",
        },
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    # Try to update to privileged
    r = await member_client.put(
        f"/api/templates/{template_id}",
        json={"privileged": True},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_update_to_set_entrypoint(member_client):
    """Non-admin cannot update template to set entrypoint."""
    create_resp = await member_client.post(
        "/api/templates",
        json={
            "name": "e2",
            "display_name": "E2",
            "image": "img",
        },
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    r = await member_client.put(
        f"/api/templates/{template_id}",
        json={"entrypoint": ["/bin/sh"]},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_to_set_risk_fields(admin_client, session):
    """Admin can update template to set risk fields."""
    from app.models import ServiceTemplate
    # Create a plain shared template
    template = ServiceTemplate(
        name="shared",
        display_name="Shared",
        image="img",
        owner_id=None,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)

    r = await admin_client.put(
        f"/api/templates/{template.id}",
        json={"privileged": True, "devices": ["/dev/dri:/dev/dri"]},
    )
    assert r.status_code == 200
    assert r.json()["privileged"] is True
    assert r.json()["devices"] == ["/dev/dri:/dev/dri"]
