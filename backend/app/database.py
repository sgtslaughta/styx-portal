import json
import os

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import ServiceTemplate

settings = Settings()
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await _run_migrations(conn)
        await conn.run_sync(SQLModel.metadata.create_all)
    async with async_session() as session:
        await seed_templates(session, settings.TEMPLATES_DIR)


async def _run_migrations(conn):
    """Add missing columns to existing tables."""
    import sqlalchemy

    migrations = [
        ("instances", "error_message", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(sqlalchemy.text(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            ))
        except Exception:
            pass


async def get_session():
    async with async_session() as session:
        yield session


async def seed_templates(session: AsyncSession, templates_dir: str):
    if not os.path.isdir(templates_dir):
        return
    for filename in os.listdir(templates_dir):
        if not filename.endswith(".json"):
            continue
        filepath = os.path.join(templates_dir, filename)
        with open(filepath) as f:
            data = json.load(f)

        result = await session.exec(
            select(ServiceTemplate).where(ServiceTemplate.name == data["name"])
        )
        existing = result.first()
        if existing:
            continue

        template = ServiceTemplate(**data)
        session.add(template)

    await session.commit()
