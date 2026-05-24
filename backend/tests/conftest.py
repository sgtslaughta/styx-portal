import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from unittest.mock import MagicMock

from app.main import app
from app.database import get_session
from app.routers.instances import get_docker_manager


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

    app.dependency_overrides[get_session] = get_session_override
    app.dependency_overrides[get_docker_manager] = get_docker_manager_override
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()
