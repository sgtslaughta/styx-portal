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

_TEMPLATE_COLUMN_DDL = {
    "shared": "BOOLEAN DEFAULT 0",
    "restart_policy": "TEXT DEFAULT 'no'",
    "read_only_rootfs": "BOOLEAN DEFAULT 0",
    "tmpfs": "JSON DEFAULT '[]'",
    "extra_hosts": "JSON DEFAULT '{}'",
    "ulimits": "JSON DEFAULT '[]'",
    "extra_ports": "JSON DEFAULT '[]'",
    "entrypoint": "JSON",
    "command": "JSON",
    "devices": "JSON DEFAULT '[]'",
    "privileged": "BOOLEAN DEFAULT 0",
    "extra_docker_args": "JSON DEFAULT '{}'",
}


def _ensure_template_columns(conn) -> None:
    """Add missing columns to service_templates table. Works with both sqlite3 and SQLAlchemy connections."""
    # Handle both raw sqlite3 and SQLAlchemy connections
    # Check if this is an async SQLAlchemy connection (has run_sync method)
    if hasattr(conn, 'run_sync'):
        # This is an async SQLAlchemy connection - this case is handled in async wrapper
        raise TypeError("Use _ensure_template_columns_async for SQLAlchemy async connections")

    # Raw sqlite3 connection
    existing = {r[1] for r in conn.execute("PRAGMA table_info(service_templates)")}
    for col, ddl in _TEMPLATE_COLUMN_DDL.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE service_templates ADD COLUMN {col} {ddl}")
    conn.commit()


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
        ("service_templates", "shared", "BOOLEAN DEFAULT 0"),
        ("service_templates", "restart_policy", "TEXT DEFAULT 'no'"),
        ("service_templates", "read_only_rootfs", "BOOLEAN DEFAULT 0"),
        ("service_templates", "tmpfs", "JSON DEFAULT '[]'"),
        ("service_templates", "extra_hosts", "JSON DEFAULT '{}'"),
        ("service_templates", "ulimits", "JSON DEFAULT '[]'"),
        ("service_templates", "extra_ports", "JSON DEFAULT '[]'"),
        ("service_templates", "entrypoint", "JSON"),
        ("service_templates", "command", "JSON"),
        ("service_templates", "devices", "JSON DEFAULT '[]'"),
        ("service_templates", "privileged", "BOOLEAN DEFAULT 0"),
        ("service_templates", "extra_docker_args", "JSON DEFAULT '{}'"),
        ("oauth_providers", "icon_url", "TEXT"),
        ("oauth_providers", "trust_email", "BOOLEAN"),
        ("oauth_providers", "allow_signup", "BOOLEAN"),
        ("oauth_providers", "auto_promote_admins", "BOOLEAN"),
        ("refresh_tokens", "family_id", "TEXT"),
        ("workstations", "active_connections", "INTEGER"),
        ("workstations", "occupied_by", "TEXT"),
        ("workstations", "occupied_at", "TIMESTAMP"),
        ("workstations", "disconnect_pending", "BOOLEAN"),
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
        ("workstations", "active_connections", "0"),
        ("workstations", "disconnect_pending", "0"),
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
