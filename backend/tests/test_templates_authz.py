import pytest
from app.models import ServiceTemplate


SHARED_TEMPLATE_PAYLOAD = {
    "name": "shared-desktop",
    "display_name": "Shared Desktop",
    "image": "ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
    "description": "Shared template",
    "env_vars": {},
}


@pytest.fixture
async def shared_template(session):
    """Create a shared template (owner_id=None) in the database."""
    template = ServiceTemplate(
        name="shared-desktop",
        display_name="Shared Desktop",
        image="ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
        description="Shared template",
        owner_id=None,  # Shared template
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


@pytest.mark.asyncio
async def test_non_admin_cannot_update_shared_template(member_client, shared_template):
    """Non-admin users cannot modify shared templates."""
    r = await member_client.put(
        f"/api/templates/{shared_template.id}",
        json={"display_name": "Evil Name"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_non_admin_cannot_delete_shared_template(member_client, shared_template):
    """Non-admin users cannot delete shared templates."""
    r = await member_client.delete(f"/api/templates/{shared_template.id}")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_update_shared_template(admin_client, shared_template):
    """Admin users can modify shared templates."""
    r = await admin_client.put(
        f"/api/templates/{shared_template.id}",
        json={"display_name": "Admin Updated"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Admin Updated"


@pytest.mark.asyncio
async def test_admin_can_delete_shared_template(admin_client, shared_template):
    """Admin users can delete shared templates."""
    r = await admin_client.delete(f"/api/templates/{shared_template.id}")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_template_update_ignores_unknown_fields(admin_client, shared_template):
    """Template update should only apply allowlisted fields."""
    # Try to set owner_id and other non-allowlisted fields via PUT
    r = await admin_client.put(
        f"/api/templates/{shared_template.id}",
        json={
            "display_name": "Updated Name",
            "owner_id": "evil-user-id",  # Not in allowlist
            "name": "evil-name",  # Not in allowlist
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["display_name"] == "Updated Name"
    assert data["owner_id"] is None  # Unchanged
    assert data["name"] == "shared-desktop"  # Unchanged


@pytest.mark.asyncio
async def test_member_can_read_shared_template(member_client, shared_template):
    """Non-admin users can read shared templates."""
    r = await member_client.get(f"/api/templates/{shared_template.id}")
    assert r.status_code == 200
    assert r.json()["id"] == shared_template.id


@pytest.mark.asyncio
async def test_member_can_update_own_template(member_client):
    """Member can update their own template."""
    # Member creates a template
    create_resp = await member_client.post(
        "/api/templates",
        json={
            "name": "member-template",
            "display_name": "Member Template",
            "image": "ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
        },
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    # Member updates their own template
    r = await member_client.put(
        f"/api/templates/{template_id}",
        json={"display_name": "Updated by Owner"},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "Updated by Owner"


@pytest.mark.asyncio
async def test_non_admin_cannot_create_template_with_cap_add(member_client):
    """Non-admin cannot create a template with cap_add capability override."""
    r = await member_client.post(
        "/api/templates",
        json={
            "name": "dangerous-template",
            "display_name": "Dangerous Template",
            "image": "ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
            "cap_add": ["SYS_NICE"],
        },
    )
    assert r.status_code == 403
    assert "cap_add/security_opt" in r.json()["detail"]


@pytest.mark.asyncio
async def test_non_admin_cannot_update_own_template_with_security_opt(member_client):
    """Non-admin cannot update their own template to add security_opt override."""
    # Member creates a plain template
    create_resp = await member_client.post(
        "/api/templates",
        json={
            "name": "member-plain-template",
            "display_name": "Plain Member Template",
            "image": "ghcr.io/linuxserver/baseimage-selkies:debiantrixie",
        },
    )
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    # Member tries to update with security_opt
    r = await member_client.put(
        f"/api/templates/{template_id}",
        json={"security_opt": ["seccomp=unconfined"]},
    )
    assert r.status_code == 403
    assert "cap_add/security_opt" in r.json()["detail"]
