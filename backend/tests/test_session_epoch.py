from sqlmodel import select

from app.models import User

PW = "correct horse battery staple"


async def _user(session, name):
    return (await session.exec(select(User).where(User.username == name))).first()


async def test_access_token_dies_on_password_change(member_client):
    old = member_client.cookies.get("access_token")
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": PW, "new_password": PW + "-new1"})
    assert r.status_code == 200, r.text
    assert (await member_client.get("/api/auth/me")).status_code == 200  # fresh session cookie
    member_client.cookies.clear()
    member_client.cookies.set("access_token", old, path="/api")
    assert (await member_client.get("/api/auth/me")).status_code == 401


async def test_admin_reset_kills_live_access_token(admin_client, member_client, session):
    # member_client and admin_client share one client object; use raw tokens explicitly.
    from app.security import tokens
    member = await _user(session, "member")
    old = tokens.create_access_token(member.id, member.role, tv=member.token_version)
    r = await admin_client.get("/api/auth/me", cookies={"access_token": old})
    assert r.status_code == 200
    member.token_version += 1
    session.add(member)
    await session.commit()
    r = await admin_client.get("/api/auth/me", cookies={"access_token": old})
    assert r.status_code == 401


async def test_reset_and_role_change_and_disable_bump_version(admin_client, session):
    from app.models import User as U
    from app.security.passwords import hash_password
    u = U(username="victim", password_hash=hash_password(PW), role="user")
    session.add(u)
    await session.commit()
    v0 = u.token_version
    assert (await admin_client.post(f"/api/users/{u.id}/reset-password")).status_code == 200
    await session.refresh(u)
    assert u.token_version == v0 + 1
    assert (await admin_client.patch(f"/api/users/{u.id}/role?role=admin")).status_code == 200
    await session.refresh(u)
    assert u.token_version == v0 + 2
    assert (await admin_client.patch(f"/api/users/{u.id}/disable")).status_code == 200
    await session.refresh(u)
    assert u.token_version == v0 + 3


async def test_must_change_pw_is_enforced_server_side(member_client, session):
    u = await _user(session, "member")
    u.must_change_pw = True
    session.add(u)
    await session.commit()
    r = await member_client.get("/api/templates")
    assert r.status_code == 403
    assert r.json()["detail"] == "Password change required"
    assert (await member_client.get("/api/auth/me")).status_code == 200
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": PW, "new_password": PW + "-new1"})
    assert r.status_code == 200, r.text
    assert (await member_client.get("/api/templates")).status_code == 200
