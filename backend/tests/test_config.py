from app.config import Settings


def test_default_settings():
    settings = Settings(DOMAIN="test.local")
    assert settings.DOMAIN == "test.local"
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./data/selkies-hub.db"
    assert settings.DOCKER_SOCKET == "unix:///var/run/docker.sock"
    assert settings.DOCKER_NETWORK == "selkies-hub"
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
    s = Settings(JWT_SECRET="test-secret")
    assert s.jwt_secret_or_raise() == "test-secret"


def test_jwt_secret_or_raise_empty_with_secure_false():
    """Test jwt_secret_or_raise returns dev secret when COOKIE_SECURE=False."""
    s = Settings(JWT_SECRET="", COOKIE_SECURE=False)
    assert s.jwt_secret_or_raise() == "dev-insecure-secret-do-not-use-in-prod"


def test_jwt_secret_or_raise_empty_with_secure_true_raises():
    """Test jwt_secret_or_raise raises RuntimeError when JWT_SECRET empty and COOKIE_SECURE=True."""
    s = Settings(JWT_SECRET="", COOKIE_SECURE=True)
    try:
        s.jwt_secret_or_raise()
        assert False, "Expected RuntimeError"
    except RuntimeError as e:
        assert "JWT_SECRET must be set when COOKIE_SECURE=true" in str(e)
