import pytest
from app.services.settings_store import settings, SCHEMA


def test_schema_excludes_secrets():
    for forbidden in ("JWT_SECRET", "DATABASE_URL", "DOCKER_SOCKET", "DEPLOY_MODE"):
        assert forbidden not in SCHEMA


def test_get_returns_seed_default_when_no_override():
    settings.reset_cache()
    assert settings.get("LOCKOUT_THRESHOLD") == 10


def test_get_unknown_key_raises():
    with pytest.raises(KeyError):
        settings.get("NOPE")


async def test_set_overrides_and_persists(session):
    settings.reset_cache()
    await settings.set(session, "LOCKOUT_THRESHOLD", 5, actor_id="a")
    await session.commit()
    assert settings.get("LOCKOUT_THRESHOLD") == 5
    from app.models import SystemSetting
    assert (await session.get(SystemSetting, "LOCKOUT_THRESHOLD")).value == 5


async def test_set_validates_int_bounds(session):
    settings.reset_cache()
    with pytest.raises(ValueError):
        await settings.set(session, "LOCKOUT_THRESHOLD", 0, actor_id="a")


async def test_set_validates_rate_format(session):
    settings.reset_cache()
    with pytest.raises(ValueError):
        await settings.set(session, "RATE_LIMIT_AUTH", "notarate", actor_id="a")


async def test_reset_restores_seed(session):
    settings.reset_cache()
    await settings.set(session, "LOCKOUT_THRESHOLD", 5, actor_id="a")
    await session.commit()
    await settings.reset(session, "LOCKOUT_THRESHOLD", actor_id="a")
    await session.commit()
    assert settings.get("LOCKOUT_THRESHOLD") == 10


async def test_reload_loads_persisted_overrides(session):
    from app.models import SystemSetting
    session.add(SystemSetting(key="MAX_INSTANCES_PER_USER", value=9))
    await session.commit()
    settings.reset_cache()
    await settings.reload(session)
    assert settings.get("MAX_INSTANCES_PER_USER") == 9


def test_effective_lists_groups_with_metadata():
    settings.reset_cache()
    eff = settings.effective()
    keys = {row["key"] for g in eff for row in g["settings"]}
    assert "LOCKOUT_THRESHOLD" in keys and "PASSWORD_MIN_LENGTH" in keys
