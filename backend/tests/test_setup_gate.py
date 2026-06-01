import pytest
from app.security.setup_gate import users_exist
from app.models import User
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_users_exist_false_when_empty(session):
    assert await users_exist(session) is False


@pytest.mark.asyncio
async def test_users_exist_true_after_insert(session):
    session.add(User(username="a", password_hash=hash_password("x")))
    await session.commit()
    assert await users_exist(session) is True
