import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config import Settings

_settings = Settings()
_ALGO = "HS256"


class TokenError(Exception):
    pass


def _secret() -> str:
    return _settings.jwt_secret_or_raise()


def create_access_token(user_id: str, role: str, ttl: int | None = None) -> str:
    ttl = _settings.ACCESS_TTL if ttl is None else ttl
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def create_refresh_token(user_id: str, ttl: int | None = None) -> tuple[str, str]:
    ttl = _settings.REFRESH_TTL if ttl is None else ttl
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user_id,
        "type": "refresh",
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO), jti


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGO])
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e
