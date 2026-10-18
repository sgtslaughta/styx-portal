import asyncio

from app.security import setup_token
from tests.helpers_setup import st

PW = "correct horse battery staple"


async def test_setup_requires_token(client):
    r = await client.post("/api/auth/setup", json={"username": "admin", "password": PW})
    assert r.status_code == 422 or r.status_code == 403
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": PW, "setup_token": "wrong"})
    assert r.status_code == 403
    assert (await client.get("/api/auth/setup-required")).json()["setup_required"] is True


async def test_setup_with_token_ok_and_token_deleted(client):
    r = await client.post("/api/auth/setup", json={"username": "admin", "password": PW, **st()})
    assert r.status_code == 201, r.text
    assert not setup_token._path().exists()


async def test_setup_cross_site_refused(client):
    r = await client.post("/api/auth/setup", json={"username": "admin", "password": PW, **st()},
                          headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


async def test_concurrent_setup_creates_one_admin(client, session):
    from sqlmodel import select, func
    from app.models import User
    bodies = [{"username": f"admin{i}", "password": PW, **st()} for i in range(5)]
    rs = await asyncio.gather(*[client.post("/api/auth/setup", json=b) for b in bodies])
    assert sorted(r.status_code for r in rs).count(201) == 1
    n = (await session.exec(select(func.count()).select_from(User))).one()
    assert n == 1


def test_announce_clears_stale_file_when_users_exist():
    setup_token.current()
    setup_token.announce(False)
    assert not setup_token._path().exists()


def test_announce_creates_file_when_pending():
    setup_token.clear()
    setup_token.announce(True)
    assert setup_token._path().exists()
    assert oct(setup_token._path().stat().st_mode & 0o777) == "0o600"
