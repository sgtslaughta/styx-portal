import re
from dataclasses import dataclass
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import SystemSetting

_settings = Settings()
_RATE_RE = re.compile(r"^\d+/\d+$")


@dataclass
class SettingSpec:
    key: str
    group: str
    label: str
    help: str
    type: str
    config_attr: str | None = None
    default: Any = None
    min: int | None = None
    max: int | None = None


def _spec(*a, **k) -> SettingSpec:
    return SettingSpec(*a, **k)


_SPECS: list[SettingSpec] = [
    _spec("LOCKOUT_THRESHOLD", "brute_force", "Lockout threshold",
          "Failed logins per username before the account locks.", "int",
          "LOCKOUT_THRESHOLD", min=1, max=100),
    _spec("LOCKOUT_DURATION", "brute_force", "Lockout duration (s)",
          "How long an account stays locked, in seconds.", "int",
          "LOCKOUT_DURATION", min=30, max=86400),
    _spec("BAN_FAIL_THRESHOLD", "brute_force", "IP ban threshold",
          "Failed logins per IP within the window before the IP is banned.", "int",
          "BAN_FAIL_THRESHOLD", min=1, max=1000),
    _spec("BAN_FAIL_WINDOW", "brute_force", "IP ban window (s)",
          "Sliding window for counting per-IP failures, in seconds.", "int",
          "BAN_FAIL_WINDOW", min=30, max=86400),
    _spec("BAN_DURATION", "brute_force", "IP ban duration (s)",
          "How long a banned IP stays blocked, in seconds.", "int",
          "BAN_DURATION", min=60, max=604800),
    _spec("RATE_LIMIT_AUTH", "rate_limits", "Auth rate limit",
          "Requests/seconds for login endpoints, e.g. 5/60.", "rate",
          "RATE_LIMIT_AUTH"),
    _spec("RATE_LIMIT_DEFAULT", "rate_limits", "Default rate limit",
          "Requests/seconds for all other endpoints, e.g. 120/60.", "rate",
          "RATE_LIMIT_DEFAULT"),
    _spec("RATE_LIMIT_INSTANCE_CREATE", "rate_limits", "Instance-create rate limit",
          "Requests/seconds for instance creation per user, e.g. 10/3600.", "rate",
          "RATE_LIMIT_INSTANCE_CREATE"),
    _spec("TRAEFIK_RATELIMIT_AVERAGE", "rate_limits", "Proxy avg req/s",
          "Traefik average requests/second per IP.", "int",
          "TRAEFIK_RATELIMIT_AVERAGE", min=1, max=100000),
    _spec("TRAEFIK_RATELIMIT_BURST", "rate_limits", "Proxy burst",
          "Traefik burst per IP.", "int",
          "TRAEFIK_RATELIMIT_BURST", min=1, max=100000),
    _spec("ACCESS_TTL", "sessions", "Access token TTL (s)",
          "Lifetime of access tokens, in seconds.", "int",
          "ACCESS_TTL", min=60, max=86400),
    _spec("REFRESH_TTL", "sessions", "Refresh token TTL (s)",
          "Lifetime of refresh tokens, in seconds.", "int",
          "REFRESH_TTL", min=300, max=2592000),
    _spec("WORKSTATION_IDLE_TIMEOUT_S", "timeouts", "Workstation idle timeout (s)",
          "Disconnect an idle physical-workstation stream after this many seconds.", "int",
          "WORKSTATION_IDLE_TIMEOUT_S", min=60, max=86400),
    _spec("WORKSTATION_OFFLINE_AFTER_S", "timeouts", "Workstation offline-after (s)",
          "Mark a workstation offline after this many seconds without a heartbeat.", "int",
          "WORKSTATION_OFFLINE_AFTER_S", min=30, max=3600),
    _spec("MAX_INSTANCES_PER_USER", "quota", "Max instances per user",
          "Per-user instance cap; 0 = unlimited. Admins are exempt.", "int",
          "MAX_INSTANCES_PER_USER", min=0, max=1000),
    _spec("PASSWORD_MIN_LENGTH", "password_policy", "Minimum length",
          "Minimum password length.", "int",
          "PASSWORD_MIN_LENGTH", min=8, max=256),
    _spec("PASSWORD_REQUIRE_UPPER", "password_policy", "Require uppercase",
          "Require at least one uppercase letter.", "bool", "PASSWORD_REQUIRE_UPPER"),
    _spec("PASSWORD_REQUIRE_LOWER", "password_policy", "Require lowercase",
          "Require at least one lowercase letter.", "bool", "PASSWORD_REQUIRE_LOWER"),
    _spec("PASSWORD_REQUIRE_DIGIT", "password_policy", "Require digit",
          "Require at least one digit.", "bool", "PASSWORD_REQUIRE_DIGIT"),
    _spec("PASSWORD_REQUIRE_SYMBOL", "password_policy", "Require symbol",
          "Require at least one non-alphanumeric symbol.", "bool", "PASSWORD_REQUIRE_SYMBOL"),
]

SCHEMA: dict[str, SettingSpec] = {s.key: s for s in _SPECS}

_GROUP_LABELS = {
    "brute_force": "Brute-force protection",
    "rate_limits": "Rate limits",
    "sessions": "Sessions & tokens",
    "timeouts": "Timeouts",
    "quota": "Quotas",
    "password_policy": "Password policy",
}

_TRAEFIK_KEYS = {"TRAEFIK_RATELIMIT_AVERAGE", "TRAEFIK_RATELIMIT_BURST"}


class SettingsService:
    def __init__(self):
        self._overrides: dict[str, Any] = {}

    def reset_cache(self) -> None:
        self._overrides.clear()

    def _seed(self, key: str) -> Any:
        spec = SCHEMA[key]
        if spec.config_attr is not None:
            return getattr(_settings, spec.config_attr)
        return spec.default

    def get(self, key: str) -> Any:
        if key not in SCHEMA:
            raise KeyError(key)
        return self._overrides.get(key, self._seed(key))

    def _validate(self, spec: SettingSpec, value: Any) -> None:
        if spec.type == "int":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{spec.key} must be an integer")
            if spec.min is not None and value < spec.min:
                raise ValueError(f"{spec.key} must be >= {spec.min}")
            if spec.max is not None and value > spec.max:
                raise ValueError(f"{spec.key} must be <= {spec.max}")
        elif spec.type == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{spec.key} must be a boolean")
        elif spec.type == "rate":
            if not isinstance(value, str) or not _RATE_RE.match(value):
                raise ValueError(f"{spec.key} must look like '5/60'")

    async def set(self, session: AsyncSession, key: str, value: Any, actor_id: str | None) -> None:
        if key not in SCHEMA:
            raise KeyError(key)
        self._validate(SCHEMA[key], value)
        from app.models import SystemSetting
        from datetime import datetime, timezone
        row = await session.get(SystemSetting, key)
        if row:
            row.value = value
            row.updated_by = actor_id
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
        else:
            session.add(SystemSetting(key=key, value=value, updated_by=actor_id))
        self._overrides[key] = value
        if key in _TRAEFIK_KEYS:
            from app.services.route_writer import refresh_routes_from_db
            await refresh_routes_from_db(session)

    async def reset(self, session: AsyncSession, key: str, actor_id: str | None) -> None:
        if key not in SCHEMA:
            raise KeyError(key)
        from app.models import SystemSetting
        row = await session.get(SystemSetting, key)
        if row:
            await session.delete(row)
        self._overrides.pop(key, None)
        if key in _TRAEFIK_KEYS:
            from app.services.route_writer import refresh_routes_from_db
            await refresh_routes_from_db(session)

    async def reload(self, session: AsyncSession) -> None:
        result = await session.exec(select(SystemSetting))
        self._overrides = {r.key: r.value for r in result.all() if r.key in SCHEMA}

    def effective(self) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for spec in _SPECS:
            groups.setdefault(spec.group, []).append({
                "key": spec.key, "label": spec.label, "help": spec.help,
                "type": spec.type, "value": self.get(spec.key),
                "default": self._seed(spec.key),
                "min": spec.min, "max": spec.max,
            })
        return [{"group": g, "label": _GROUP_LABELS.get(g, g), "settings": rows}
                for g, rows in groups.items()]


settings = SettingsService()
