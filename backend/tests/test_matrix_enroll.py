from sqlmodel import select

from app.models import User
from app.services import matrix_card

PW = "correct horse battery staple"


async def _user(session, name):
    session.expire_all()
    return (await session.exec(select(User).where(User.username == name))).one()


async def _enable(c):
    g = (await c.post("/api/auth/matrix/generate", json={"password": PW})).json()
    r = await c.post("/api/auth/matrix/activate", json={"answer": g["cells"][g["confirm_cell"]]})
    assert r.status_code == 200
    return g


async def test_generate_requires_password(admin_client):
    r = await admin_client.post("/api/auth/matrix/generate", json={"password": "nope"})
    assert r.status_code == 401
    r = await admin_client.post("/api/auth/matrix/generate", json={"password": PW})
    assert r.status_code == 200
    assert len(r.json()["cells"]) == 50 and r.json()["confirm_cell"] in r.json()["cells"]


async def test_generate_then_activate_enables(admin_client, session):
    assert (await admin_client.get("/api/auth/matrix")).json() == {"enabled": False}
    await _enable(admin_client)
    assert (await admin_client.get("/api/auth/matrix")).json() == {"enabled": True}
    u = await _user(session, "admin")
    assert u.matrix_pending is None and u.matrix_serial == 1


async def test_activate_wrong_answer_400_and_not_enabled(admin_client):
    await admin_client.post("/api/auth/matrix/generate", json={"password": PW})
    r = await admin_client.post("/api/auth/matrix/activate", json={"answer": "!!!"})
    assert r.status_code == 400
    assert (await admin_client.get("/api/auth/matrix")).json() == {"enabled": False}
    r = await admin_client.post("/api/auth/matrix/activate", json={"answer": "x"})
    assert r.status_code == 400


async def test_activate_without_pending_400(admin_client):
    r = await admin_client.post("/api/auth/matrix/activate", json={"answer": "x"})
    assert r.status_code == 400


async def test_regenerate_keeps_old_until_activated(admin_client, session):
    g = await _enable(admin_client)
    await admin_client.post("/api/auth/matrix/generate", json={"password": PW})
    u = await _user(session, "admin")
    assert matrix_card.unseal(u.matrix_card) == g["cells"]
    assert u.matrix_pending is not None


async def test_remove_requires_password(admin_client, session):
    await _enable(admin_client)
    r = await admin_client.request("DELETE", "/api/auth/matrix", json={"password": "bad"})
    assert r.status_code == 401
    r = await admin_client.request("DELETE", "/api/auth/matrix", json={"password": PW})
    assert r.status_code == 200
    u = await _user(session, "admin")
    assert u.matrix_card is None and u.matrix_serial == 2


async def test_admin_reset(admin_client, session):
    from app.security.passwords import hash_password
    session.add(User(username="bob", password_hash=hash_password(PW), role="member",
                     is_active=True, matrix_card=matrix_card.seal({"A1": "AAA"}), matrix_serial=3))
    await session.commit()
    bob = await _user(session, "bob")
    r = await admin_client.request("DELETE", f"/api/users/{bob.id}/matrix")
    assert r.status_code == 200
    bob = await _user(session, "bob")
    assert bob.matrix_card is None and bob.matrix_serial == 4
    r = await admin_client.request("DELETE", "/api/users/nope/matrix")
    assert r.status_code == 404


async def test_member_cannot_admin_reset(member_client, session):
    u = await _user(session, "member")
    r = await member_client.request("DELETE", f"/api/users/{u.id}/matrix")
    assert r.status_code == 403


async def test_matrix_responses_not_cached(admin_client):
    r = await admin_client.post("/api/auth/matrix/generate", json={"password": PW})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert (await admin_client.get("/api/auth/matrix")).headers["cache-control"] == "no-store"
