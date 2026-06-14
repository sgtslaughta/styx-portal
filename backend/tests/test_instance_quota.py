"""Instance quota and rate limiting tests."""
import pytest
from unittest.mock import patch


def _payload(template_dict, i):
    """Generate a test instance creation payload."""
    return {
        "template_id": template_dict["id"],
        "name": f"quota-test-{i}",
        "subdomain": f"quota-test-{i}",
    }


@pytest.mark.asyncio
async def test_user_quota_enforced(member_client, session):
    """Non-admin users are limited by MAX_INSTANCES_PER_USER quota."""
    # Create a template
    payload = {
        "name": "test-quota-tmpl",
        "display_name": "Quota Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Patch the settings to allow only 2 instances
    with patch("app.routers.instances.sys_settings.get", return_value=2):
        # First create should succeed
        resp1 = await member_client.post("/api/instances", json=_payload(template, 1))
        assert resp1.status_code == 201, resp1.text

        # Second create should succeed
        resp2 = await member_client.post("/api/instances", json=_payload(template, 2))
        assert resp2.status_code == 201, resp2.text

        # Third create should fail with 429
        resp3 = await member_client.post("/api/instances", json=_payload(template, 3))
        assert resp3.status_code == 429, f"Expected 429, got {resp3.status_code}: {resp3.text}"
        assert "limit reached" in resp3.json()["detail"].lower() or "limit" in resp3.json()["detail"].lower(), \
            f"Expected limit message, got: {resp3.json()['detail']}"


@pytest.mark.asyncio
async def test_admin_exempt_from_quota(admin_client, session):
    """Admin users bypass the instance quota."""
    # Create a template
    payload = {
        "name": "test-admin-exempt-tmpl",
        "display_name": "Admin Exempt Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await admin_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Patch the settings to allow only 1 instance
    with patch("app.routers.instances.sys_settings.get", return_value=1):
        # First create should succeed
        resp1 = await admin_client.post("/api/instances", json=_payload(template, 1))
        assert resp1.status_code == 201, resp1.text

        # Second create should also succeed (admin exempt)
        resp2 = await admin_client.post("/api/instances", json=_payload(template, 2))
        assert resp2.status_code == 201, resp2.text


@pytest.mark.asyncio
async def test_zero_means_unlimited(member_client, session):
    """MAX_INSTANCES_PER_USER=0 means no quota limit."""
    # Create a template
    payload = {
        "name": "test-unlimited-tmpl",
        "display_name": "Unlimited Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Patch the settings to disable quota (0 = unlimited)
    with patch("app.routers.instances.sys_settings.get", return_value=0):
        # Should be able to create 4 instances without hitting quota
        for i in range(1, 5):
            resp = await member_client.post("/api/instances", json=_payload(template, i))
            assert resp.status_code == 201, f"Instance {i} failed: {resp.text}"


@pytest.mark.asyncio
async def test_create_rate_limit_per_user(member_client, session):
    """Per-user rate limiting on instance creation."""
    # Create a template
    payload = {
        "name": "test-ratelimit-tmpl",
        "display_name": "Rate Limit Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Replace the limiter with a tiny window
    from app.middleware.rate_limit import SlidingWindow

    # Patch with a limiter that allows only 2 creates per 3600s
    tiny_limiter = SlidingWindow(2, 3600)

    with patch("app.routers.instances._create_limiter", tiny_limiter):
        # First two creates should succeed
        resp1 = await member_client.post("/api/instances", json=_payload(template, 1))
        assert resp1.status_code == 201, resp1.text

        resp2 = await member_client.post("/api/instances", json=_payload(template, 2))
        assert resp2.status_code == 201, resp2.text

        # Third create should fail with 429 (rate limit)
        resp3 = await member_client.post("/api/instances", json=_payload(template, 3))
        assert resp3.status_code == 429, f"Expected 429, got {resp3.status_code}: {resp3.text}"


@pytest.mark.asyncio
async def test_instance_create_audited(member_client, session):
    """Instance creation is audited with template and subdomain."""
    from app.models import AuditLog, User
    from sqlmodel import select

    # Create a template
    payload = {
        "name": "test-audit-create-tmpl",
        "display_name": "Audit Create Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Create an instance
    create_payload = _payload(template, 1)
    resp = await member_client.post("/api/instances", json=create_payload)
    assert resp.status_code == 201

    # Get the member user
    user_result = await session.exec(select(User).where(User.username == "member"))
    member_user = user_result.first()

    # Query audit log
    audit_result = await session.exec(
        select(AuditLog)
        .where(AuditLog.action == "instance.create")
        .where(AuditLog.user_id == member_user.id)
    )
    audit_entries = audit_result.all()

    assert len(audit_entries) >= 1, f"Expected at least 1 audit entry, got {len(audit_entries)}"
    log = audit_entries[-1]  # Most recent
    assert log.action == "instance.create"
    assert log.user_id == member_user.id
    assert log.detail is not None
    assert log.detail.get("template") == "test-audit-create-tmpl"
    assert log.detail.get("subdomain") == "quota-test-1"


@pytest.mark.asyncio
async def test_instance_delete_audited(member_client, session):
    """Instance deletion is audited with subdomain."""
    from app.models import AuditLog, User
    from sqlmodel import select

    # Create a template
    payload = {
        "name": "test-audit-delete-tmpl",
        "display_name": "Audit Delete Template",
        "image": "test:latest",
        "internal_port": 3001,
    }
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201
    template = resp.json()

    # Create an instance
    create_payload = _payload(template, 1)
    resp = await member_client.post("/api/instances", json=create_payload)
    assert resp.status_code == 201
    instance_id = resp.json()["id"]

    # Get the member user
    user_result = await session.exec(select(User).where(User.username == "member"))
    member_user = user_result.first()

    # Delete the instance
    delete_resp = await member_client.delete(f"/api/instances/{instance_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    # Check audit log
    audit_result = await session.exec(
        select(AuditLog)
        .where(AuditLog.action == "instance.delete")
        .where(AuditLog.user_id == member_user.id)
    )
    audit_entries = audit_result.all()

    assert len(audit_entries) >= 1, f"Expected at least 1 audit entry, got {len(audit_entries)}"
    log = audit_entries[-1]  # Most recent
    assert log.action == "instance.delete"
    assert log.user_id == member_user.id
    assert log.detail is not None
    assert log.detail.get("subdomain") == "quota-test-1"


@pytest.mark.asyncio
async def test_quota_is_live(session):
    from app.services.settings_store import settings
    await settings.set(session, "MAX_INSTANCES_PER_USER", 0, actor_id=None)
    await session.commit()
    assert settings.get("MAX_INSTANCES_PER_USER") == 0
