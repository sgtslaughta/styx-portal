import pytest
from sqlmodel import select, delete
from app.models import RefreshToken, AuditLog


@pytest.mark.asyncio
async def test_rotation_keeps_family(client, session):
    """Login → refresh once → all tokens share one family_id, family_id == first jti."""
    # Setup admin user
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201

    # Capture the refresh token from login
    refresh_token_1 = client.cookies.get("refresh_token")
    assert refresh_token_1 is not None

    # Get the first jti from database
    tokens_1 = (await session.exec(select(RefreshToken))).all()
    assert len(tokens_1) == 1
    first_token = tokens_1[0]
    first_jti = first_token.jti
    first_family_id = first_token.family_id

    # Family ID should be set to jti on first login
    assert first_family_id == first_jti

    # Refresh the token
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200

    # After refresh, both tokens should have the same family_id
    tokens_all = (await session.exec(select(RefreshToken))).all()
    assert len(tokens_all) == 2

    family_ids = {t.family_id for t in tokens_all}
    assert len(family_ids) == 1, "All tokens should share the same family_id"
    assert list(family_ids)[0] == first_jti, "family_id should be the original jti"


@pytest.mark.asyncio
async def test_reuse_of_rotated_token_revokes_family(client, session):
    """Login → refresh (succeeds) → replay old token → 401, all family tokens revoked."""
    # Setup admin user
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201

    # Capture the first refresh token
    old_refresh_token = client.cookies.get("refresh_token")
    assert old_refresh_token is not None

    # Get all tokens and verify only one exists and not revoked
    tokens_setup = (await session.exec(select(RefreshToken))).all()
    assert len(tokens_setup) == 1
    assert not tokens_setup[0].revoked

    # Refresh successfully (token rotates)
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 200

    # Capture the new refresh token
    new_refresh_token = client.cookies.get("refresh_token")
    assert new_refresh_token != old_refresh_token

    # After refresh, the old token is marked revoked, but new one is not
    tokens_after_refresh = (await session.exec(select(RefreshToken))).all()
    assert len(tokens_after_refresh) == 2
    revoked_count = sum(1 for t in tokens_after_refresh if t.revoked)
    assert revoked_count == 1, "One token should be revoked after refresh"

    # Now try to use the OLD (rotated) token
    client.cookies.set("refresh_token", old_refresh_token)
    # Update CSRF header to the current cookie value (updated during last refresh)
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    r = await client.post("/api/auth/refresh")
    assert r.status_code == 401

    # Verify that ALL tokens in the family are now revoked
    tokens_final = (await session.exec(select(RefreshToken))).all()
    assert len(tokens_final) == 2
    assert all(t.revoked for t in tokens_final), "All tokens in the family should be revoked"

    # Verify the audit log contains the refresh_reuse action
    audit_logs = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.refresh_reuse"))).all()
    assert len(audit_logs) == 1
    audit_log = audit_logs[0]
    assert audit_log.resource == tokens_setup[0].family_id


@pytest.mark.asyncio
async def test_login_success_audited(client, session):
    """Successful login → AuditLog has 'auth.login' action with user_id."""
    # Setup admin user
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201
    admin_id = r.json()["id"]

    # Clear audit logs
    await session.exec(delete(AuditLog))
    await session.commit()

    # Logout then log back in
    await client.post("/api/auth/logout")

    # Login with the admin user
    r = await client.post("/api/auth/login", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 200

    # Verify audit log for login
    logs = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.login"))).all()
    assert len(logs) == 1
    assert logs[0].user_id == admin_id


@pytest.mark.asyncio
async def test_login_failure_audited(client, session):
    """Failed login → 401 and AuditLog has 'auth.login_failed'."""
    # Setup admin user first
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201

    # Clear audit logs
    await session.exec(delete(AuditLog))
    await session.commit()

    # Try to login with wrong password
    r = await client.post("/api/auth/login", json={
        "username": "admin", "password": "wrong password"})
    assert r.status_code == 401

    # Verify audit log for failed login
    logs = (await session.exec(select(AuditLog).where(
        AuditLog.action == "auth.login_failed"))).all()
    assert len(logs) == 1
    assert logs[0].detail == {"username": "admin"}
