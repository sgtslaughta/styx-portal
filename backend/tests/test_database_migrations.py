import os
import stat

import pytest
import sqlalchemy
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import _run_migrations


@pytest.mark.asyncio
async def test_duplicate_column_is_ignored():
    """Test that adding a column that already exists is silently skipped."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create base tables with some columns pre-existing
        await conn.execute(sqlalchemy.text("CREATE TABLE instances (id TEXT, error_message TEXT)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE service_templates (id TEXT, owner_id TEXT, dind BOOLEAN)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE oauth_providers (id TEXT, trust_email BOOLEAN, allow_signup BOOLEAN)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE refresh_tokens (jti TEXT)"))

        # Should not raise on pre-existing columns
        await _run_migrations(conn)


@pytest.mark.asyncio
async def test_fresh_install_no_tables_does_not_raise():
    """Test that running migrations on fresh install with no tables doesn't raise."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # No tables exist
        await _run_migrations(conn)


@pytest.mark.asyncio
async def test_migrations_add_columns_to_instances():
    """Test that migrations add error_message and owner_id to instances table."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create minimal instances table
        await conn.execute(sqlalchemy.text("CREATE TABLE instances (id TEXT PRIMARY KEY)"))
        await conn.execute(sqlalchemy.text("INSERT INTO instances (id) VALUES ('test-1')"))

        # Run migrations
        await _run_migrations(conn)

        # Verify columns exist
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(instances)"))
        columns = {row[1] for row in result.fetchall()}
        assert "error_message" in columns
        assert "owner_id" in columns


@pytest.mark.asyncio
async def test_migrations_add_columns_to_service_templates():
    """Test that migrations add owner_id, dind, cap_add, security_opt, tls_skip_verify to service_templates."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create minimal service_templates table
        await conn.execute(sqlalchemy.text("CREATE TABLE service_templates (id TEXT PRIMARY KEY)"))

        # Run migrations
        await _run_migrations(conn)

        # Verify columns exist
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(service_templates)"))
        columns = {row[1] for row in result.fetchall()}
        assert "owner_id" in columns
        assert "dind" in columns
        assert "cap_add" in columns
        assert "security_opt" in columns
        assert "tls_skip_verify" in columns


@pytest.mark.asyncio
async def test_migrations_add_columns_to_oauth_providers():
    """Test that migrations add icon_url, trust_email, allow_signup, auto_promote_admins to oauth_providers."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create minimal oauth_providers table
        await conn.execute(sqlalchemy.text("CREATE TABLE oauth_providers (id TEXT PRIMARY KEY)"))

        # Run migrations
        await _run_migrations(conn)

        # Verify columns exist
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(oauth_providers)"))
        columns = {row[1] for row in result.fetchall()}
        assert "icon_url" in columns
        assert "trust_email" in columns
        assert "allow_signup" in columns
        assert "auto_promote_admins" in columns


@pytest.mark.asyncio
async def test_migrations_add_columns_to_refresh_tokens():
    """Test that migrations add family_id to refresh_tokens."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create minimal refresh_tokens table
        await conn.execute(sqlalchemy.text("CREATE TABLE refresh_tokens (jti TEXT PRIMARY KEY)"))

        # Run migrations
        await _run_migrations(conn)

        # Verify column exists
        result = await conn.execute(sqlalchemy.text("PRAGMA table_info(refresh_tokens)"))
        columns = {row[1] for row in result.fetchall()}
        assert "family_id" in columns


@pytest.mark.asyncio
async def test_backfill_oauth_providers_defaults():
    """Test that backfill sets trust_email and allow_signup to 0, auto_promote_admins to 1."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create oauth_providers table with data but without backfill columns
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE oauth_providers (id TEXT PRIMARY KEY, name TEXT)"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO oauth_providers (id, name) VALUES ('oauth-1', 'google')"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO oauth_providers (id, name) VALUES ('oauth-2', 'github')"
        ))

        # Run migrations
        await _run_migrations(conn)

        # Verify backfill values
        result = await conn.execute(sqlalchemy.text(
            "SELECT id, trust_email, allow_signup, auto_promote_admins FROM oauth_providers ORDER BY id"
        ))
        rows = result.fetchall()
        assert len(rows) == 2
        assert rows[0][1] == 0  # trust_email
        assert rows[0][2] == 0  # allow_signup
        assert rows[0][3] == 1  # auto_promote_admins
        assert rows[1][1] == 0
        assert rows[1][2] == 0
        assert rows[1][3] == 1


@pytest.mark.asyncio
async def test_backfill_service_templates_tls_skip_verify():
    """Test that backfill sets tls_skip_verify to 0."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create service_templates table with data but without tls_skip_verify
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE service_templates (id TEXT PRIMARY KEY, name TEXT)"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO service_templates (id, name) VALUES ('tpl-1', 'ubuntu')"
        ))

        # Run migrations
        await _run_migrations(conn)

        # Verify backfill value
        result = await conn.execute(sqlalchemy.text(
            "SELECT id, tls_skip_verify FROM service_templates"
        ))
        rows = result.fetchall()
        assert len(rows) == 1
        assert rows[0][1] == 0  # tls_skip_verify


@pytest.mark.asyncio
async def test_backfill_refresh_tokens_family_id():
    """Test that backfill sets family_id to jti for legacy rows."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # Create refresh_tokens table with data but without family_id
        await conn.execute(sqlalchemy.text(
            "CREATE TABLE refresh_tokens (jti TEXT PRIMARY KEY)"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO refresh_tokens (jti) VALUES ('token-1')"
        ))
        await conn.execute(sqlalchemy.text(
            "INSERT INTO refresh_tokens (jti) VALUES ('token-2')"
        ))

        # Run migrations
        await _run_migrations(conn)

        # Verify backfill values
        result = await conn.execute(sqlalchemy.text(
            "SELECT jti, family_id FROM refresh_tokens ORDER BY jti"
        ))
        rows = result.fetchall()
        assert len(rows) == 2
        assert rows[0][1] == "token-1"  # family_id should equal jti
        assert rows[1][1] == "token-2"


def test_restrict_db_perms_noop_for_memory(monkeypatch):
    """Test that _restrict_db_perms safely handles in-memory SQLite URLs."""
    from app import database
    monkeypatch.setattr(database.settings, "DATABASE_URL", "sqlite+aiosqlite://")
    database._restrict_db_perms()  # must not raise


def test_restrict_db_perms_sets_0600(tmp_path, monkeypatch):
    """Test that _restrict_db_perms sets SQLite file permissions to 0600."""
    from app import database
    f = tmp_path / "t.db"
    f.write_text("x")
    monkeypatch.setattr(database.settings, "DATABASE_URL", f"sqlite+aiosqlite:///{f}")
    database._restrict_db_perms()
    assert stat.S_IMODE(os.stat(f).st_mode) == 0o600
