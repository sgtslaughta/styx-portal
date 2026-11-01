import re
from dataclasses import dataclass
from typing import Any, Callable

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import SystemSetting
from app.security.crypto import decrypt_secret, encrypt_secret

_settings = Settings()
_RATE_RE = re.compile(r"^\d+/\d+$")


class JsonValueError(ValueError):
    """Invalid structured (json) setting value; surfaced as 422."""


_DEFAULT_SIZE_PRESETS = [
    {"id": "light", "label": "Light", "cpus": 2, "memory_gb": 2, "gpu": False},
    {"id": "standard", "label": "Standard", "cpus": 4, "memory_gb": 4, "gpu": False},
    {"id": "heavy", "label": "Heavy", "cpus": 6, "memory_gb": 8, "gpu": True},
]


def _num(v: Any, lo: int, hi: int) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and lo <= v <= hi


def _validate_size_presets(value: Any) -> None:
    if not isinstance(value, list) or not 1 <= len(value) <= 6:
        raise JsonValueError("CONTAINER_SIZE_PRESETS must be a list of 1 to 6 presets")
    keys = {"id", "label", "cpus", "memory_gb", "gpu"}
    ids = set()
    for p in value:
        if not isinstance(p, dict) or set(p) != keys:
            raise JsonValueError("each preset needs exactly: id, label, cpus, memory_gb, gpu")
        if not (isinstance(p["id"], str) and p["id"] and isinstance(p["label"], str) and p["label"]):
            raise JsonValueError("preset id and label must be non-empty strings")
        if not _num(p["cpus"], 1, 64):
            raise JsonValueError("preset cpus must be 1 to 64")
        if not _num(p["memory_gb"], 1, 512):
            raise JsonValueError("preset memory_gb must be 1 to 512")
        if not isinstance(p["gpu"], bool):
            raise JsonValueError("preset gpu must be a boolean")
        if p["id"] in ids:
            raise JsonValueError("preset ids must be unique")
        ids.add(p["id"])


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
    choices: tuple[str, ...] | None = None
    pattern: str | None = None
    validator: Callable[[Any], None] | None = None


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
    _spec("MATRIX_SESSION_MAX_HOURS", "sessions", "Card session max age (h)",
          "Absolute lifetime of a sign-in-card (session-only) login, in hours.", "int",
          "MATRIX_SESSION_MAX_HOURS", min=1, max=168),
    _spec("WORKSTATION_IDLE_TIMEOUT_S", "timeouts", "Workstation idle timeout (s)",
          "Disconnect an idle physical-workstation stream after this many seconds.", "int",
          "WORKSTATION_IDLE_TIMEOUT_S", min=60, max=86400),
    _spec("WORKSTATION_IDLE_WARN_LEAD_S", "timeouts", "Workstation idle warning lead (s)",
          "Seconds before idle disconnect to show the client countdown warning. "
          "Clamped below half the idle timeout.", "int",
          "WORKSTATION_IDLE_WARN_LEAD_S", min=5, max=3600),
    _spec("WORKSTATION_IDLE_TIMEOUT_ENABLED", "timeouts", "Workstation idle timeout enabled",
          "Master switch for workstation idle timeout. Off ⇒ seats never time out "
          "(no client warning and no server disconnect).", "bool",
          "WORKSTATION_IDLE_TIMEOUT_ENABLED"),
    _spec("WORKSTATION_OFFLINE_AFTER_S", "timeouts", "Workstation offline-after (s)",
          "Mark a workstation offline after this many seconds without a heartbeat.", "int",
          "WORKSTATION_OFFLINE_AFTER_S", min=30, max=3600),
    _spec("WORKSTATION_SEAT_WIDTH", "workstation_features", "Seat width (px)",
          "Default headless GNOME seat width.", "int",
          "WORKSTATION_SEAT_WIDTH", min=800, max=7680),
    _spec("WORKSTATION_SEAT_HEIGHT", "workstation_features", "Seat height (px)",
          "Default headless GNOME seat height.", "int",
          "WORKSTATION_SEAT_HEIGHT", min=600, max=4320),
    _spec("MAX_INSTANCES_PER_USER", "quota", "Max instances per user",
          "Per-user instance cap; 0 = unlimited. Admins are exempt.", "int",
          "MAX_INSTANCES_PER_USER", min=0, max=1000),
    _spec("CONTAINER_SIZE_PRESETS", "quota", "Container size presets",
          "Light / Standard / Heavy choices offered when launching a container.", "json",
          default=_DEFAULT_SIZE_PRESETS, validator=_validate_size_presets),
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
    _spec("WORKSTATION_TRANSPORT", "webrtc", "Default stream transport",
          "Transport for workstation streams unless a workstation overrides it. WebRTC is lower latency; "
          "from networks that block peer-to-peer UDP it needs a TURN relay (below).", "enum",
          default="websockets", choices=("websockets", "webrtc")),
    _spec("WEBRTC_TURN_PROVIDER", "webrtc", "TURN provider",
          "Relay for WebRTC when a direct connection is blocked. none = direct/STUN only; "
          "cloudflare = Cloudflare Realtime TURN (billed per GB, 1,000 GB/month free); "
          "generic = your own TURN server (e.g. coturn).", "enum",
          default="none", choices=("none", "cloudflare", "generic")),
    _spec("CLOUDFLARE_TURN_TOKEN_ID", "webrtc", "Cloudflare TURN token ID",
          "Cloudflare dashboard > Realtime > TURN Server > Create (name it e.g. Styx-Portal). "
          "Paste the 'Turn Token ID' shown after creation.", "secret"),
    _spec("CLOUDFLARE_TURN_API_TOKEN", "webrtc", "Cloudflare TURN API token",
          "The 'API Token' shown with the Turn Token ID when you create the TURN key. "
          "Shown once: copy it then. Stored encrypted; never displayed again here.", "secret"),
    _spec("CLOUDFLARE_ACCOUNT_ID", "webrtc", "Cloudflare account ID",
          "Optional, for actual usage. Dashboard: Ctrl/Cmd+K > 'Copy account ID' (or Workers & Pages > "
          "Account Details > Account ID).", "str", default=""),
    _spec("CLOUDFLARE_ANALYTICS_TOKEN", "webrtc", "Cloudflare analytics token",
          "Optional. My Profile > API Tokens > Create Token > Create Custom Token; permission "
          "Account > Account Analytics > Read, Account Resources: your account. Shown once. "
          "Enables actual usage on the cost card and a budget based on Cloudflare's own figure.",
          "secret"),
    _spec("TURN_HOST", "webrtc", "TURN host", "Hostname or IP of your TURN server (e.g. coturn), reachable from both browsers and workstations.", "str", default=""),
    _spec("TURN_PORT", "webrtc", "TURN port", "Usually 3478 (UDP/TCP) or 5349 / 443 with TLS.", "int",
          default=3478, min=1, max=65535),
    _spec("TURN_PROTOCOL", "webrtc", "TURN protocol", "udp is best for latency; tcp only if UDP is blocked between browser and relay.", "enum",
          default="udp", choices=("udp", "tcp")),
    _spec("TURN_TLS", "webrtc", "TURN over TLS", "turns: (TLS) — gets through firewalls that only allow HTTPS; use with port 5349 or 443.",
          "bool", default=False),
    _spec("TURN_SHARED_SECRET", "webrtc", "TURN shared secret",
          "coturn: the static-auth-secret from turnserver.conf (with use-auth-secret). Preferred over a "
          "fixed username/password: credentials are short-lived.", "secret"),
    _spec("TURN_USERNAME", "webrtc", "TURN username", "Only if your TURN server uses a fixed user (coturn: user=name:password). Leave empty with a shared secret.", "str", default=""),
    _spec("TURN_PASSWORD", "webrtc", "TURN password", "Password for the fixed TURN user above.", "secret"),
    _spec("WEBRTC_MAX_SESSION_H", "webrtc", "WebRTC max session (h)",
          "Hard cap on a WebRTC session regardless of input; 0 = off.", "int",
          default=8, min=0, max=72),
    _spec("TURN_FREE_GB_MONTH", "webrtc", "TURN free GB / month",
          "Monthly free relay allowance used by the cost estimate.", "int",
          default=1000, min=0, max=1000000),
    _spec("TURN_BUDGET_GB", "webrtc", "TURN budget (GB / month)",
          "When this month's relayed total reaches it, every workstation falls back to "
          "WebSockets (no TURN) until the next month or until it is raised; 0 = no limit.",
          "int", default=900, min=0, max=1000000),
    _spec("AGENT_AUTO_UPDATE", "workstation_features", "Auto-update workstation agents",
          "Outdated agents update themselves on their next check-in; a failed update rolls back "
          "and is not retried until an admin asks again.", "bool", default=False),
    _spec("TURN_USD_PER_GB", "webrtc", "TURN price (USD/GB)",
          "Price per GB beyond the free allowance, e.g. 0.05.", "str",
          default="0.05", pattern=r"^\d+(\.\d+)?$"),
]

SCHEMA: dict[str, SettingSpec] = {s.key: s for s in _SPECS}

_GROUP_LABELS = {
    "brute_force": "Brute-force protection",
    "rate_limits": "Rate limits",
    "sessions": "Sessions & tokens",
    "timeouts": "Timeouts",
    "workstation_features": "Workstation features",
    "quota": "Quotas",
    "password_policy": "Password policy",
    "webrtc": "WebRTC / TURN",
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
        return "" if spec.type == "secret" else spec.default

    def get(self, key: str) -> Any:
        """Effective value; secrets come back as decrypted plaintext ("" if unset)."""
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
            if not isinstance(value, str) or not _RATE_RE.fullmatch(value):
                raise ValueError(f"{spec.key} must look like '5/60'")
        elif spec.type == "enum":
            if value not in (spec.choices or ()):
                raise ValueError(f"{spec.key} must be one of {', '.join(spec.choices or ())}")
        elif spec.type == "json":
            if spec.validator:
                spec.validator(value)
        elif spec.type in ("str", "secret"):
            if not isinstance(value, str) or len(value) > 512:
                raise ValueError(f"{spec.key} must be a string of at most 512 characters")
            if spec.pattern and not re.fullmatch(spec.pattern, value):
                raise ValueError(f"{spec.key} has an invalid format")

    async def set(self, session: AsyncSession, key: str, value: Any, actor_id: str | None) -> None:
        if key not in SCHEMA:
            raise KeyError(key)
        spec = SCHEMA[key]
        self._validate(spec, value)
        if spec.type == "secret" and value == "":
            return await self.reset(session, key, actor_id)
        stored = encrypt_secret(value) if spec.type == "secret" else value
        from app.models import SystemSetting
        from datetime import datetime, timezone
        row = await session.get(SystemSetting, key)
        if row:
            row.value = stored
            row.updated_by = actor_id
            row.updated_at = datetime.now(timezone.utc)
            session.add(row)
        else:
            session.add(SystemSetting(key=key, value=stored, updated_by=actor_id))
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
        self._overrides = {}
        for r in result.all():
            if r.key not in SCHEMA:
                continue
            if SCHEMA[r.key].type == "secret":
                try:
                    self._overrides[r.key] = decrypt_secret(r.value)
                except Exception:  # undecryptable (JWT_SECRET changed) -> treat as unset
                    continue
            else:
                self._overrides[r.key] = r.value

    def effective(self) -> list[dict]:
        groups: dict[str, list[dict]] = {}
        for spec in _SPECS:
            row = {
                "key": spec.key, "label": spec.label, "help": spec.help,
                "type": spec.type, "value": self.get(spec.key),
                "default": self._seed(spec.key),
                "min": spec.min, "max": spec.max,
            }
            if spec.type == "secret":   # plaintext never leaves the service
                row.update(value=None, default=None, is_set=bool(self.get(spec.key)))
            elif spec.type == "enum":
                row["choices"] = list(spec.choices or ())
            groups.setdefault(spec.group, []).append(row)
        return [{"group": g, "label": _GROUP_LABELS.get(g, g), "settings": rows}
                for g, rows in groups.items()]


settings = SettingsService()
