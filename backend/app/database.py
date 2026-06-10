import json
import logging
import os
import stat
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import ServiceTemplate

logger = logging.getLogger("styx-portal")

settings = Settings()
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def _restrict_db_perms():
    """Restrict SQLite database file permissions to 0600 (owner read/write only)."""
    url = settings.DATABASE_URL
    if "sqlite" not in url:
        return
    path = Path(url.split("///")[-1])
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600


async def init_db():
    async with engine.begin() as conn:
        await _run_migrations(conn)
        await conn.run_sync(SQLModel.metadata.create_all)
    _restrict_db_perms()
    async with async_session() as session:
        await seed_templates(session, settings.TEMPLATES_DIR)


async def _run_migrations(conn):
    """Add missing columns to existing tables."""
    import sqlalchemy
    from sqlalchemy.exc import OperationalError

    migrations = [
        ("instances", "error_message", "TEXT"),
        ("instances", "owner_id", "TEXT"),
        ("service_templates", "owner_id", "TEXT"),
        ("service_templates", "dind", "BOOLEAN"),
        ("service_templates", "cap_add", "TEXT"),
        ("service_templates", "security_opt", "TEXT"),
        ("service_templates", "tls_skip_verify", "BOOLEAN"),
        ("oauth_providers", "icon_url", "TEXT"),
        ("oauth_providers", "trust_email", "BOOLEAN"),
        ("oauth_providers", "allow_signup", "BOOLEAN"),
        ("oauth_providers", "auto_promote_admins", "BOOLEAN"),
        ("refresh_tokens", "family_id", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(sqlalchemy.text(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            ))
        except OperationalError as e:
            msg = str(e).lower()
            # expected on fresh installs / re-runs; anything else is a real failure
            if "duplicate column" not in msg and "no such table" not in msg:
                logger.error("Migration failed for %s.%s: %s", table, column, e)
                raise

    # ADD COLUMN ... BOOLEAN has no default, so rows that predate a column get NULL.
    # These are non-nullable bools downstream — backfill NULLs to False.
    backfills = [
        ("oauth_providers", "trust_email", "0"),
        ("oauth_providers", "allow_signup", "0"),
        ("oauth_providers", "auto_promote_admins", "1"),
        ("service_templates", "tls_skip_verify", "0"),
        ("refresh_tokens", "family_id", "jti"),  # legacy rows: own family
    ]
    for table, column, default in backfills:
        try:
            await conn.execute(sqlalchemy.text(
                f"UPDATE {table} SET {column} = {default} WHERE {column} IS NULL"
            ))
        except OperationalError as e:
            if "no such table" not in str(e).lower():
                logger.error("Backfill failed for %s.%s: %s", table, column, e)
                raise


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
