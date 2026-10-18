import pytest
from sqlmodel import select

from app.models import User

URL = "/api/auth/me/preferences"


@pytest.mark.asyncio
async def test_me_exposes_unset_preferences(member_client):
    j = (await member_client.get("/api/auth/me")).json()
    assert j["open_workspaces"] is None and j["open_apps"] is None


@pytest.mark.asyncio
async def test_put_changes_only_given_keys_and_null_resets(member_client):
    r = await member_client.put(URL, json={"open_apps": "new_tab"})
    assert r.status_code == 200, r.text
    assert r.json()["open_apps"] == "new_tab" and r.json()["open_workspaces"] is None
    r = await member_client.put(URL, json={"open_workspaces": "same_tab"})
    assert r.json()["open_apps"] == "new_tab" and r.json()["open_workspaces"] == "same_tab"
    me = (await member_client.get("/api/auth/me")).json()
    assert (me["open_apps"], me["open_workspaces"]) == ("new_tab", "same_tab")
    r = await member_client.put(URL, json={"open_apps": None})
    assert r.json()["open_apps"] is None and r.json()["open_workspaces"] == "same_tab"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"open_apps": "popup"}, {"open_apps": 1}, {"theme": "dark"}])
async def test_put_rejects_bad_values(member_client, body):
    assert (await member_client.put(URL, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_put_requires_csrf(member_client):
    member_client.headers.pop("X-CSRF-Token")
    assert (await member_client.put(URL, json={"open_apps": "new_tab"})).status_code == 403


@pytest.mark.asyncio
async def test_put_requires_auth(client):
    assert (await client.put(URL, json={"open_apps": "new_tab"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_other_users_untouched(member_client, session):
    from app.security.passwords import hash_password
    other = User(username="other", password_hash=hash_password("x" * 20))
    session.add(other)
    await session.commit()
    await member_client.put(URL, json={"open_apps": "new_tab", "open_workspaces": "new_tab"})
    o = (await session.exec(select(User).where(User.username == "other"))).first()
    await session.refresh(o)
    assert o.open_apps is None and o.open_workspaces is None
