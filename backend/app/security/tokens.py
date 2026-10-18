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
    from app.services.settings_store import settings
    ttl = settings.get("ACCESS_TTL") if ttl is None else ttl
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),   # enables hard revocation on logout
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def create_refresh_token(user_id: str, ttl: int | None = None) -> tuple[str, str]:
    from app.services.settings_store import settings
    ttl = settings.get("REFRESH_TTL") if ttl is None else ttl
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


def create_proxy_token(user_id: str, family_id: str, ttl: int | None = None) -> str:
    """forwardAuth-only token (styx_proxy cookie). Bound to a refresh-token
    family: it dies with logout, rotation-reuse kill or password change."""
    from app.services.settings_store import settings
    ttl = settings.get("REFRESH_TTL") if ttl is None else ttl
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "proxy",
        "fam": family_id,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)
