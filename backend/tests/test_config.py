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
