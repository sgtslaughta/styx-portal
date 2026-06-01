import pytest
from app.security import tokens


def test_access_roundtrip():
    t = tokens.create_access_token("user-1", "admin")
    claims = tokens.decode_token(t)
    assert claims["sub"] == "user-1"
    assert claims["role"] == "admin"
    assert claims["type"] == "access"


def test_refresh_has_jti():
    t, jti = tokens.create_refresh_token("user-1")
    claims = tokens.decode_token(t)
    assert claims["type"] == "refresh"
    assert claims["jti"] == jti


def test_expired_token_rejected():
    t = tokens.create_access_token("user-1", "user", ttl=-1)
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(t)


def test_tampered_token_rejected():
    t = tokens.create_access_token("user-1", "user")
    with pytest.raises(tokens.TokenError):
        tokens.decode_token(t + "x")
