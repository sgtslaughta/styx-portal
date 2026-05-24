import json
import tempfile
import os

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import seed_templates
from app.models import ServiceTemplate


@pytest.mark.asyncio
async def test_seed_templates():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        template_data = {
            "name": "test-seed",
            "display_name": "Test Seed",
            "image": "test:latest",
            "internal_port": 3001,
        }
        with open(os.path.join(tmpdir, "test-seed.json"), "w") as f:
            json.dump(template_data, f)

        async with factory() as session:
            await seed_templates(session, tmpdir)
            result = await session.exec(select(ServiceTemplate))
            templates = result.all()
            assert len(templates) == 1
            assert templates[0].name == "test-seed"

    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_idempotent():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as tmpdir:
        template_data = {
            "name": "idem",
            "display_name": "Idem",
            "image": "test:latest",
            "internal_port": 3001,
        }
        with open(os.path.join(tmpdir, "idem.json"), "w") as f:
            json.dump(template_data, f)

        async with factory() as session:
            await seed_templates(session, tmpdir)
            await seed_templates(session, tmpdir)
            result = await session.exec(select(ServiceTemplate))
            templates = result.all()
            assert len(templates) == 1

    await engine.dispose()
