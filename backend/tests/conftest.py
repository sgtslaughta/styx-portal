import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("RATE_LIMIT_AUTH", "1000/60")
os.environ.setdefault("RATE_LIMIT_DEFAULT", "1000/60")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.database import get_session
from app.routers.instances import get_docker_manager, get_screenshot_service


@pytest.fixture(name="session")
async def session_fixture():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session_factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(name="client")
async def client_fixture(session):
    async def get_session_override():
        yield session

    def get_docker_manager_override():
        manager = MagicMock()
        manager.create_volume.side_effect = lambda name: name
        manager.create_container.return_value = "container-abc123"
        manager.get_container_status.return_value = {"status": "running"}
        return manager

    def get_screenshot_service_override():
        # Avoid real ScreenshotService (mkdir of host cache dir + Playwright).
        svc = MagicMock()
        svc.capture = AsyncMock(return_value=True)
        svc.close = AsyncMock()
        return svc

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_docker_manager] = get_docker_manager_override
    app.dependency_overrides[get_screenshot_service] = get_screenshot_service_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
async def admin_client(client):
    """An AsyncClient that has completed first-run setup and holds admin cookies + CSRF header."""
    r = await client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery staple"})
    assert r.status_code == 201, r.text
    csrf = client.cookies.get("csrf_token")
    client.headers.update({"X-CSRF-Token": csrf})
    return client


@pytest.fixture
async def member_client(client, session):
    """An AsyncClient for a non-admin member user with auth cookies + CSRF header."""
    from app.models import User
    from app.security.passwords import hash_password
    session.add(User(
        username="member",
        password_hash=hash_password("correct horse battery staple"),
        role="member",
        is_active=True,
    ))
    await session.commit()
    r = await client.post("/api/auth/login", json={
        "username": "member", "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text
    client.headers.update({"X-CSRF-Token": client.cookies.get("csrf_token")})
    return client
