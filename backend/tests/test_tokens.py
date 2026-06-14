import pytest
from unittest.mock import patch

from app.security import tokens


@pytest.fixture
def mock_settings():
    """Fixture that mocks Settings to have a valid JWT_SECRET."""
    with patch("app.security.tokens._settings") as mock:
        mock.jwt_secret_or_raise.return_value = "test-secret-key-for-testing"
        mock.ACCESS_TTL = 900
        mock.REFRESH_TTL = 604800
        yield mock


def test_access_roundtrip(mock_settings):
    t = tokens.create_access_token("user-1", "admin")
    claims = tokens.decode_token(t)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"
    assert claims["type"] == "access"


def test_refresh_has_jti(mock_settings):
    t, jti = tokens.create_refresh_token("user-1")
    claims = tokens.decode_token(t)
    assert claims["type"] == "refresh"
    assert claims["jti"] == jti


def test_expired_token_rejected(mock_settings):
    t = tokens.create_access_token("user-1", "user", ttl=-1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(t)


def test_tampered_token_rejected(mock_settings):
    t = tokens.create_access_token("user-1", "user")
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(t + "x")


def test_access_ttl_reads_settings():
    from app.services.settings_store import settings
    import app.security.tokens as t
    import jwt
    settings.reset_cache()
    settings._overrides["ACCESS_TTL"] = 123  # simulate a live override
    tok = t.create_access_token("u1", "user")
    claims = jwt.decode(tok, t._secret(), algorithms=[t._ALGO])
    assert claims["exp"] - claims["iat"] == 123
    settings.reset_cache()
