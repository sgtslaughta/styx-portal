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


def create_access_token(user_id: str, role: str, ttl: int | None = None, tv: int = 0) -> str:
    from app.services.settings_store import settings
    ttl = settings.get("ACCESS_TTL") if ttl is None else ttl
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "tv": tv,                   # user.token_version at issue; mismatch = revoked
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


DEVICE_TTL = 180 * 86400


def create_device_token(user_id: str, tv: int) -> str:
    """Trusted-device cookie: lets the real owner past the lockout/throttle brakes."""
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "type": "device", "tv": tv, "rnd": uuid.uuid4().hex,
                       "iat": now, "exp": now + timedelta(seconds=DEVICE_TTL)},
                      _secret(), algorithm=_ALGO)


def device_rnd(raw: str | None, user) -> str | None:
    """The token's rnd if it is a valid device token for this very user, else None."""
    if not raw or user is None:
        return None
    try:
        c = decode_token(raw)
    except TokenError:
        return None
    if (c.get("type") == "device" and c.get("sub") == user.id
            and c.get("tv", 0) == user.token_version):
        return c.get("rnd")
    return None


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGO])
    except jwt.PyJWTError as e:
        raise TokenError(str(e)) from e


def create_proxy_token(user_id: str, family_id: str, ttl: int | None = None, tv: int = 0) -> str:
    """forwardAuth-only token (styx_proxy cookie). Bound to a refresh-token
    family: it dies with logout, rotation-reuse kill or password change."""
    from app.services.settings_store import settings
    ttl = settings.get("REFRESH_TTL") if ttl is None else ttl
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "type": "proxy",
        "fam": family_id,
        "tv": tv,
        "jti": str(uuid.uuid4()),
        "iat": now,
        "exp": now + timedelta(seconds=ttl),
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)
