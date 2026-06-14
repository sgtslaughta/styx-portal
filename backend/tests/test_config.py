import json
import stat

import pytest

from app.config import Settings, PLACEHOLDER_SECRETS


def test_default_settings():
    settings = Settings(DOMAIN="test.local")
    assert settings.DOMAIN == "test.local"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./data/styx-portal.db"
    assert settings.DOCKER_SOCKET == "unix:///var/run/docker.sock"
    assert settings.DOCKER_NETWORK == "styx-portal"
    assert settings.SELKIES_DEFAULT_PORT == 3001


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("DOMAIN", "example.com")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///custom.db")
    settings = Settings()
    assert settings.DOMAIN == "example.com"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///custom.db"


def test_screenshot_interval_default():
    s = Settings()
    assert s.SCREENSHOT_INTERVAL_SECONDS == 30


def test_jwt_settings_defaults():
    """Test JWT and rate-limit settings have expected defaults."""
    # Use model_fields to check declared defaults (not env-influenced runtime values).
    # conftest.py sets JWT_SECRET, COOKIE_SECURE, RATE_LIMIT_AUTH, RATE_LIMIT_DEFAULT as env vars
    # for test runs, so checking Settings() would fail. Instead, check the class defaults.
    assert Settings.model_fields["JWT_SECRET"].default == ""
    assert Settings.model_fields["ACCESS_TTL"].default == 900
    assert Settings.model_fields["REFRESH_TTL"].default == 604800
    assert Settings.model_fields["COOKIE_SECURE"].default is True
    assert Settings.model_fields["COOKIE_DOMAIN"].default is None
    assert Settings.model_fields["RATE_LIMIT_AUTH"].default == "5/60"
    assert Settings.model_fields["RATE_LIMIT_DEFAULT"].default == "120/60"


def test_jwt_secret_or_raise_with_secret():
    """Test jwt_secret_or_raise returns provided secret."""
    secret = "a" * 32  # 32 chars minimum
    s = Settings(JWT_SECRET=secret)
    assert s.jwt_secret_or_raise() == secret


def test_jwt_secret_or_raise_empty_with_secure_false(tmp_path):
    """Test jwt_secret_or_raise generates a secret when JWT_SECRET empty and COOKIE_SECURE=False."""
    s = _settings(tmp_path, JWT_SECRET="", COOKIE_SECURE=False)
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32  # Should generate, not use old dev fallback


def test_jwt_secret_or_raise_empty_with_secure_true_generates(tmp_path):
    """Test jwt_secret_or_raise generates a secret when JWT_SECRET empty and COOKIE_SECURE=True."""
    s = _settings(tmp_path, JWT_SECRET="", COOKIE_SECURE=True)
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32  # Should generate, not raise


def _settings(tmp_path, **kw):
    kw.setdefault("SECRETS_FILE", str(tmp_path / "secrets.json"))
    return Settings(_env_file=None, **kw)


def test_autogenerates_secret_when_unset(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="")
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32
    data = json.loads((tmp_path / "secrets.json").read_text())
    assert data["jwt_secret"] == secret


def test_generated_secret_persists_across_instances(tmp_path):
    path = str(tmp_path / "secrets.json")
    a = Settings(_env_file=None, JWT_SECRET="", SECRETS_FILE=path)
    b = Settings(_env_file=None, JWT_SECRET="", SECRETS_FILE=path)
    assert a.jwt_secret_or_raise() == b.jwt_secret_or_raise()


def test_secrets_file_mode_0600(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="")
    s.jwt_secret_or_raise()
    mode = stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode)
    assert mode == 0o600


def test_env_secret_wins_over_file(tmp_path):
    (tmp_path / "secrets.json").write_text(json.dumps({"jwt_secret": "f" * 40}))
    s = _settings(tmp_path, JWT_SECRET="e" * 40)
    assert s.jwt_secret_or_raise() == "e" * 40


def test_rejects_short_secret(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="short")
    with pytest.raises(RuntimeError, match="32"):
        s.jwt_secret_or_raise()


@pytest.mark.parametrize("placeholder", sorted(PLACEHOLDER_SECRETS))
def test_rejects_placeholder_secret(tmp_path, placeholder):
    s = _settings(tmp_path, JWT_SECRET=placeholder)
    with pytest.raises(RuntimeError, match="placeholder"):
        s.jwt_secret_or_raise()


def test_no_dev_fallback_secret(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="", COOKIE_SECURE=False)
    assert s.jwt_secret_or_raise() != "dev-insecure-secret-do-not-use-in-prod"


def test_corrupt_secrets_file_regenerates(tmp_path):
    """Test that corrupt JSON in secrets.json is detected and regenerated."""
    p = tmp_path / "secrets.json"
    p.write_text("{not json")
    s = _settings(tmp_path, JWT_SECRET="")
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32
    assert json.loads(p.read_text())["jwt_secret"] == secret


def test_short_persisted_secret_regenerates(tmp_path):
    """Test that persisted secret under 32 chars triggers regeneration."""
    p = tmp_path / "secrets.json"
    p.write_text(json.dumps({"jwt_secret": "tiny"}))
    s = _settings(tmp_path, JWT_SECRET="")
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32
    assert json.loads(p.read_text())["jwt_secret"] == secret


def test_server_lan_url_falls_back_to_domain():
    from app.config import Settings
    s = Settings(DOMAIN="example.com", SERVER_LAN_URL="")
    assert s.server_lan_url() == "https://example.com"
    s2 = Settings(SERVER_LAN_URL="https://192.168.1.10/")
    assert s2.server_lan_url() == "https://192.168.1.10"


def test_brute_force_defaults():
    from app.config import Settings
    s = Settings()
    assert s.LOCKOUT_THRESHOLD == 10
    assert s.LOCKOUT_DURATION == 900
    assert s.BAN_FAIL_THRESHOLD == 20
    assert s.BAN_FAIL_WINDOW == 600
    assert s.BAN_DURATION == 3600
    assert s.BAN_CACHE_TTL == 30
    assert s.TRAEFIK_RATELIMIT_AVERAGE == 100
    assert s.TRAEFIK_RATELIMIT_BURST == 50
