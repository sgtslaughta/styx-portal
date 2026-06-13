"""Test shared template visibility and authorization."""

import pytest


@pytest.mark.asyncio
async def test_shared_template_visible_to_other_user(member_client, second_member_client):
    """A shared template created by member should be visible to other members."""
    # member creates a private template
    r = await member_client.post("/api/templates", json={
        "name": "mine", "display_name": "Mine", "image": "img"})
    assert r.status_code == 201
    tid = r.json()["id"]

    # member shares it
    up = await member_client.put(f"/api/templates/{tid}", json={"shared": True})
    assert up.status_code == 200
    assert up.json()["shared"] is True

    # second_member should see it in their list
    resp = await second_member_client.get("/api/templates")
    templates = resp.json()
    names = {t["name"] for t in templates}
    assert "mine" in names


@pytest.mark.asyncio
async def test_unshared_template_not_visible_to_other_user(member_client, second_member_client):
    """An unshared template created by member should NOT be visible to other members."""
    # member creates a private (unshared) template
    r = await member_client.post("/api/templates", json={
        "name": "secret", "display_name": "Secret", "image": "img"})
    assert r.status_code == 201

    # second_member should NOT see it in their list
    resp = await second_member_client.get("/api/templates")
    templates = resp.json()
    names = {t["name"] for t in templates}
    assert "secret" not in names


@pytest.mark.asyncio
async def test_non_owner_cannot_edit_shared_template(member_client, second_member_client):
    """A non-owner should not be able to edit a shared template (even if shared)."""
    # member creates a shared template
    r = await member_client.post("/api/templates", json={
        "name": "mine2", "display_name": "Mine2", "image": "img", "shared": True})
    assert r.status_code == 201
    tid = r.json()["id"]

    # second_member attempts to edit it
    r2 = await second_member_client.put(f"/api/templates/{tid}", json={"display_name": "Hacked"})
    # Should be forbidden or not found
    assert r2.status_code in (403, 404)


@pytest.mark.asyncio
async def test_owner_can_edit_shared_template(member_client):
    """A template owner should be able to edit their own shared template."""
    # member creates a template
    r = await member_client.post("/api/templates", json={
        "name": "mine3", "display_name": "Mine3", "image": "img"})
    assert r.status_code == 201
    tid = r.json()["id"]

    # owner can share it
    r2 = await member_client.put(f"/api/templates/{tid}", json={"shared": True})
    assert r2.status_code == 200

    # owner can still edit it after sharing
    r3 = await member_client.put(f"/api/templates/{tid}", json={"display_name": "Updated"})
    assert r3.status_code == 200
    assert r3.json()["display_name"] == "Updated"


@pytest.mark.asyncio
async def test_admin_can_see_all_templates(admin_client, member_client):
    """Admin should see all templates (owned, global, and other users' unshared ones)."""
    # member creates a private template
    r = await member_client.post("/api/templates", json={
        "name": "private", "display_name": "Private", "image": "img"})
    assert r.status_code == 201

    # admin should see it
    resp = await admin_client.get("/api/templates")
    templates = resp.json()
    names = {t["name"] for t in templates}
    assert "private" in names
