# Admin Settings + User Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Frontend tasks additionally invoke the frontend-design skill.

**Goal:** Expose safe server behavioral settings in the admin panel (runtime-editable, env-seeded, applied live) and close user-management gaps (unlock, reset-password, force-change, delete-if-empty, self change-password, enforced password policy).

**Architecture:** A new `SettingsService` reads from a `system_settings` KV table, falling back to `config.py` env seeds, gated by an allowlist SCHEMA (secrets/infra structurally excluded). Use-time read-points switch from frozen `_settings.X` to `settings.get("X")` so edits apply with no restart; Traefik knobs trigger a `routes.yml` rewrite. New admin API + settings tab edit the store; user-management endpoints + a self change-password flow + password-policy enforcement close the gaps.

**Tech Stack:** FastAPI, SQLModel, async SQLite, pytest + httpx AsyncClient; React 19 + Vite + TanStack Query + sonner + shadcn/ui.

**Spec:** `docs/superpowers/specs/2026-06-14-admin-settings-and-user-management-design.md`

---

## File Structure

- `backend/app/config.py` — MODIFY: add 5 `PASSWORD_*` policy fields.
- `backend/app/models.py` — MODIFY: new `SystemSetting` table.
- `backend/app/services/settings_store.py` — CREATE: `SettingSpec`, `SCHEMA`, `SettingsService`, singleton `settings`.
- `backend/app/routers/system_settings.py` — CREATE: admin GET/PATCH/reset endpoints.
- `backend/app/security/passwords.py` — MODIFY: `PasswordPolicy`, `validate_password`, `current_policy`.
- `backend/app/security/tokens.py` — MODIFY: live `ACCESS_TTL`/`REFRESH_TTL`.
- `backend/app/middleware/rate_limit.py` — MODIFY: live rate-limit specs.
- `backend/app/routers/auth.py` — MODIFY: live lockout/ban reads; self `change-password`; policy at setup/accept-invite.
- `backend/app/services/abuse.py` — read-points stay; auth.py sets live thresholds (no signature change).
- `backend/app/routers/instances.py` — MODIFY: live quota.
- `backend/app/services/route_writer.py` — MODIFY: live Traefik knobs.
- `backend/app/services/workstations.py` — MODIFY: live offline/idle reads.
- `backend/app/routers/users.py` — MODIFY: expand list; unlock/reset/force-change/delete endpoints.
- `backend/app/schemas.py` — MODIFY: expand `UserOut`; settings + password-change + reset schemas.
- `backend/app/main.py` — MODIFY: register router; warm settings cache; drop frozen middleware specs.
- `backend/tests/...` — CREATE/MODIFY test files per task.
- `frontend/src/api/client.ts` — MODIFY: settings + user-action + change-password methods.
- `frontend/src/components/system/system-settings-panel.tsx` — CREATE.
- `frontend/src/components/system/users-panel.tsx` — MODIFY.
- `frontend/src/components/settings/nav-config.tsx` — MODIFY: add Settings section.
- `frontend/src/pages/ChangePasswordPage.tsx` (or dialog) — CREATE; `LoginPage.tsx` redirect on `must_change_pw`.

---

# PHASE 1 — Settings store core

### Task 1: Password-policy config fields

**Files:**
- Modify: `backend/app/config.py` (after `TRAEFIK_RATELIMIT_BURST`)
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_config.py`:

```python
def test_password_policy_defaults():
    from app.config import Settings
    s = Settings()
    assert s.PASSWORD_MIN_LENGTH == 12
    assert s.PASSWORD_REQUIRE_UPPER is False
    assert s.PASSWORD_REQUIRE_LOWER is False
    assert s.PASSWORD_REQUIRE_DIGIT is False
    assert s.PASSWORD_REQUIRE_SYMBOL is False
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_config.py::test_password_policy_defaults -v`

- [ ] **Step 3: Add fields** — in `backend/app/config.py`, after the `TRAEFIK_RATELIMIT_BURST` line:

```python
    # --- Password policy ---
    PASSWORD_MIN_LENGTH: int = 12
    PASSWORD_REQUIRE_UPPER: bool = False
    PASSWORD_REQUIRE_LOWER: bool = False
    PASSWORD_REQUIRE_DIGIT: bool = False
    PASSWORD_REQUIRE_SYMBOL: bool = False
```

- [ ] **Step 4: Run, expect PASS** — same command.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(config): password policy settings"
```

---

### Task 2: SystemSetting table

**Files:**
- Modify: `backend/app/models.py` (after the `BannedIP` class)
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_models.py`:

```python
async def test_system_setting_roundtrip(session):
    from app.models import SystemSetting
    session.add(SystemSetting(key="LOCKOUT_THRESHOLD", value=7, updated_by="admin-id"))
    await session.commit()
    got = await session.get(SystemSetting, "LOCKOUT_THRESHOLD")
    assert got.value == 7
    assert got.updated_by == "admin-id"
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_models.py::test_system_setting_roundtrip -v`

- [ ] **Step 3: Add model** — in `backend/app/models.py`, immediately after the `BannedIP` class:

```python
class SystemSetting(SQLModel, table=True):
    __tablename__ = "system_settings"

    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now)
    updated_by: str | None = None
```

(`Any`, `Column`, `JSON`, `datetime`, `_now` are already imported in models.py.)

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models.py
git commit -m "feat(models): SystemSetting KV table"
```

---

### Task 3: SettingsService + SCHEMA

**Files:**
- Create: `backend/app/services/settings_store.py`
- Test: `backend/tests/test_settings_store.py`

- [ ] **Step 1: Failing tests** — create `backend/tests/test_settings_store.py`:

```python
import pytest
from app.services.settings_store import settings, SCHEMA


def test_schema_excludes_secrets():
    # secrets/infra must never be exposable
    for forbidden in ("JWT_SECRET", "DATABASE_URL", "DOCKER_SOCKET", "DEPLOY_MODE"):
        assert forbidden not in SCHEMA


def test_get_returns_seed_default_when_no_override():
    # no override set -> falls back to config seed (LOCKOUT_THRESHOLD default 10)
    settings.reset_cache()
    assert settings.get("LOCKOUT_THRESHOLD") == 10


def test_get_unknown_key_raises():
    with pytest.raises(KeyError):
        settings.get("NOPE")


async def test_set_overrides_and_persists(session):
    settings.reset_cache()
    await settings.set(session, "LOCKOUT_THRESHOLD", 5, actor_id="a")
    await session.commit()
    assert settings.get("LOCKOUT_THRESHOLD") == 5
    from app.models import SystemSetting
    assert (await session.get(SystemSetting, "LOCKOUT_THRESHOLD")).value == 5


async def test_set_validates_int_bounds(session):
    settings.reset_cache()
    with pytest.raises(ValueError):
        await settings.set(session, "LOCKOUT_THRESHOLD", 0, actor_id="a")   # min 1


async def test_set_validates_rate_format(session):
    settings.reset_cache()
    with pytest.raises(ValueError):
        await settings.set(session, "RATE_LIMIT_AUTH", "notarate", actor_id="a")


async def test_reset_restores_seed(session):
    settings.reset_cache()
    await settings.set(session, "LOCKOUT_THRESHOLD", 5, actor_id="a")
    await session.commit()
    await settings.reset(session, "LOCKOUT_THRESHOLD", actor_id="a")
    await session.commit()
    assert settings.get("LOCKOUT_THRESHOLD") == 10


async def test_reload_loads_persisted_overrides(session):
    from app.models import SystemSetting
    session.add(SystemSetting(key="MAX_INSTANCES_PER_USER", value=9))
    await session.commit()
    settings.reset_cache()
    await settings.reload(session)
    assert settings.get("MAX_INSTANCES_PER_USER") == 9


def test_effective_lists_groups_with_metadata():
    settings.reset_cache()
    eff = settings.effective()
    keys = {row["key"] for g in eff for row in g["settings"]}
    assert "LOCKOUT_THRESHOLD" in keys and "PASSWORD_MIN_LENGTH" in keys
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_settings_store.py -v` (No module).

- [ ] **Step 3: Implement** — create `backend/app/services/settings_store.py`:

```python
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
    type: str                       # "int" | "bool" | "rate"
    config_attr: str | None = None  # name in Settings; None for keys with a literal default
    default: Any = None             # used when config_attr is None
    min: int | None = None
    max: int | None = None


def _spec(*a, **k) -> SettingSpec:
    return SettingSpec(*a, **k)


# Allowlist. ONLY keys here are readable/writable through the store/API.
# Secrets and infra (JWT_SECRET, DATABASE_URL, DOCKER_*, DEPLOY_MODE, paths) are
# deliberately absent and therefore structurally unreachable.
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

# Keys whose effect lives in the Traefik dynamic config; changing them must
# rewrite routes.yml to apply live.
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
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_settings_store.py -v`

- [ ] **Step 5: ruff** — `.venv/bin/python -m ruff check app/services/settings_store.py tests/test_settings_store.py`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/settings_store.py backend/tests/test_settings_store.py
git commit -m "feat(settings): SettingsService + allowlist SCHEMA"
```

---

### Task 4: Cache warm-up + test reset fixture

**Files:**
- Modify: `backend/app/main.py` (lifespan, after `await init_db()`)
- Modify: `backend/tests/conftest.py` (extend the existing autouse reset fixture)

- [ ] **Step 1: Warm cache in lifespan** — in `backend/app/main.py`, in the `lifespan` function right after `await init_db()`, add:

```python
    from app.services.settings_store import settings as _settings_store
    async with async_session() as _s:
        await _settings_store.reload(_s)
```

- [ ] **Step 2: Reset settings cache per test** — in `backend/tests/conftest.py`, extend the existing `_reset_abuse_state` autouse fixture body (add these lines before `yield`):

```python
    from app.services.settings_store import settings as _settings_store
    _settings_store.reset_cache()
```

- [ ] **Step 3: Run sanity** — `.venv/bin/python -m pytest tests/test_settings_store.py tests/test_startup.py -v` → PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/tests/conftest.py
git commit -m "feat(settings): warm cache at startup; reset between tests"
```

---

# PHASE 2 — All-live read-point refactor

### Task 5: Live lockout/ban reads in login

**Files:**
- Modify: `backend/app/routers/auth.py` (login handler)
- Test: `backend/tests/test_auth_lockout.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_auth_lockout.py`:

```python
async def test_lockout_threshold_is_live(client, session):
    # lower the threshold to 3 at runtime; the 4th wrong attempt must lock
    from app.services.settings_store import settings
    await settings.set(session, "LOCKOUT_THRESHOLD", 3, actor_id=None)
    await session.commit()
    await _make_user(session)
    for _ in range(3):
        r = await client.post("/api/auth/login",
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 401, r.text
    r = await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    assert r.status_code == 423
```

- [ ] **Step 2: Run, expect FAIL** — threshold still hard-bound to config 10.
  `.venv/bin/python -m pytest tests/test_auth_lockout.py::test_lockout_threshold_is_live -v`

- [ ] **Step 3: Switch reads to the store** — in `backend/app/routers/auth.py`, add near the top imports:

```python
from app.services.settings_store import settings as sys_settings
```

In the `login` handler, replace the lockout/ban section so it reads live values. Replace:

```python
            if user.failed_count >= _settings.LOCKOUT_THRESHOLD:
                user.locked_until = _now() + timedelta(seconds=_settings.LOCKOUT_DURATION)
                user.failed_count = 0
            session.add(user)
        # Per-IP abuse detector -> proxy ban (L3).
        if fail_tracker.record(ip):
            await ban_ip(session, ip, "brute-force: failed logins",
                         _settings.BAN_DURATION)
```

with:

```python
            if user.failed_count >= sys_settings.get("LOCKOUT_THRESHOLD"):
                user.locked_until = _now() + timedelta(seconds=sys_settings.get("LOCKOUT_DURATION"))
                user.failed_count = 0
            session.add(user)
        # Per-IP abuse detector -> proxy ban (L3). Thresholds are live-tunable.
        fail_tracker.threshold = sys_settings.get("BAN_FAIL_THRESHOLD")
        fail_tracker.window = sys_settings.get("BAN_FAIL_WINDOW")
        if fail_tracker.record(ip):
            await ban_ip(session, ip, "brute-force: failed logins",
                         sys_settings.get("BAN_DURATION"))
```

(`fail_tracker.threshold`/`window` are plain attributes on `IpFailTracker`; setting them before `record()` makes the existing class honor live values with no signature change.)

- [ ] **Step 4: Run, expect PASS** — the live test plus the whole file:
  `.venv/bin/python -m pytest tests/test_auth_lockout.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_lockout.py
git commit -m "feat(auth): read lockout/ban thresholds live from settings"
```

---

### Task 6: Live token TTLs

**Files:**
- Modify: `backend/app/security/tokens.py`, `backend/app/routers/auth.py` (`_issue_session`)
- Test: `backend/tests/test_tokens.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_tokens.py`:

```python
def test_access_ttl_reads_settings(monkeypatch):
    from app.services.settings_store import settings
    from app import security
    import app.security.tokens as t
    settings.reset_cache()
    settings._overrides["ACCESS_TTL"] = 123  # simulate a live override
    import jwt
    tok = t.create_access_token("u1", "user")
    claims = jwt.decode(tok, t._secret(), algorithms=[t._ALGO])
    assert claims["exp"] - claims["iat"] == 123
    settings.reset_cache()
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_tokens.py::test_access_ttl_reads_settings -v`

- [ ] **Step 3: Read TTLs live** — in `backend/app/security/tokens.py`, change the two default assignments:

```python
def create_access_token(user_id: str, role: str, ttl: int | None = None) -> str:
    from app.services.settings_store import settings
    ttl = settings.get("ACCESS_TTL") if ttl is None else ttl
```

```python
def create_refresh_token(user_id: str, ttl: int | None = None) -> tuple[str, str]:
    from app.services.settings_store import settings
    ttl = settings.get("REFRESH_TTL") if ttl is None else ttl
```

(Import inside the functions to avoid an import cycle at module load.)

In `backend/app/routers/auth.py` `_issue_session`, change the RefreshToken expiry:

```python
        expires_at=_now() + timedelta(seconds=sys_settings.get("REFRESH_TTL")),
```

(`sys_settings` was imported in Task 5.)

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_tokens.py tests/test_auth_router.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/tokens.py backend/app/routers/auth.py backend/tests/test_tokens.py
git commit -m "feat(auth): read token TTLs live from settings"
```

---

### Task 7: Live instance quota

**Files:**
- Modify: `backend/app/routers/instances.py` (line ~277)
- Test: `backend/tests/test_instance_quota.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_instance_quota.py` (follow the file's existing fixtures for creating a member + template; mirror its existing quota test, but set the limit live):

```python
async def test_quota_is_live(member_client, session):
    from app.services.settings_store import settings
    await settings.set(session, "MAX_INSTANCES_PER_USER", 0, actor_id=None)  # 0 = unlimited
    await session.commit()
    # With unlimited set live, creating beyond the old default must NOT 429/400 on quota.
    # (Assert by checking settings.get reflects 0 — the create path now reads it.)
    assert settings.get("MAX_INSTANCES_PER_USER") == 0
```

  (If the existing test file already exercises the create path with a low limit, prefer adding a live-override variant there; the assertion above is the minimum that proves the read switched.)

- [ ] **Step 2: Run, expect FAIL** if asserting via create path; PASS-after-impl for the settings read. Run:
  `.venv/bin/python -m pytest tests/test_instance_quota.py::test_quota_is_live -v`

- [ ] **Step 3: Switch the read** — in `backend/app/routers/instances.py`, near the top add (if not already present a settings import):

```python
from app.services.settings_store import settings as sys_settings
```

  and change line ~277 from:

```python
        quota = _settings.MAX_INSTANCES_PER_USER
```

  to:

```python
        quota = sys_settings.get("MAX_INSTANCES_PER_USER")
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_instance_quota.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/instances.py backend/tests/test_instance_quota.py
git commit -m "feat(instances): read per-user quota live from settings"
```

---

### Task 8: Live rate-limit middleware

**Files:**
- Modify: `backend/app/middleware/rate_limit.py`, `backend/app/main.py`
- Test: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_rate_limit.py`:

```python
def test_middleware_reads_live_spec():
    from app.middleware.rate_limit import RateLimitMiddleware
    mw = RateLimitMiddleware(app=None)
    w1 = mw._window_for("3/60")
    assert w1.limit == 3 and w1.window == 60
    # same spec returns the same memoized window; new spec returns a new one
    assert mw._window_for("3/60") is w1
    assert mw._window_for("9/60").limit == 9
```

- [ ] **Step 2: Run, expect FAIL** — `RateLimitMiddleware.__init__` currently requires specs and has no `_window_for`.
  `.venv/bin/python -m pytest tests/test_rate_limit.py::test_middleware_reads_live_spec -v`

- [ ] **Step 3: Make the middleware read live** — replace `RateLimitMiddleware` in `backend/app/middleware/rate_limit.py` with:

```python
class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._windows: dict[str, SlidingWindow] = {}

    def _window_for(self, spec: str) -> SlidingWindow:
        w = self._windows.get(spec)
        if w is None:
            w = SlidingWindow(*_parse(spec))
            self._windows[spec] = w
        return w

    async def dispatch(self, request: Request, call_next):
        if is_rate_limit_exempt(request.url.path):
            return await call_next(request)
        from app.services.settings_store import settings
        ip = client_ip_from_headers(request)
        strict = is_strict_auth(request.method, request.url.path)
        spec = settings.get("RATE_LIMIT_AUTH") if strict else settings.get("RATE_LIMIT_DEFAULT")
        window = self._window_for(spec)
        if not window.allow(f"{ip}:{strict}"):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(window.window)},
            )
        return await call_next(request)
```

  In `backend/app/main.py`, change the middleware registration to drop the frozen specs:

```python
app.add_middleware(RateLimitMiddleware)
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_rate_limit.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/app/main.py backend/tests/test_rate_limit.py
git commit -m "feat(rate-limit): middleware reads specs live from settings"
```

---

### Task 9: Live Traefik knobs + workstation timeouts

**Files:**
- Modify: `backend/app/services/route_writer.py`, `backend/app/services/workstations.py`
- Test: `backend/tests/test_route_writer.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_route_writer.py`:

```python
def test_ratelimit_middleware_uses_live_settings(monkeypatch):
    from app.services.settings_store import settings
    settings.reset_cache()
    settings._overrides["TRAEFIK_RATELIMIT_AVERAGE"] = 7
    settings._overrides["TRAEFIK_RATELIMIT_BURST"] = 3
    cfg = build_routes_config([], "example.com", "tunnel")
    rl = cfg["http"]["middlewares"]["styx-ratelimit"]["rateLimit"]
    assert rl["average"] == 7 and rl["burst"] == 3
    settings.reset_cache()
```

- [ ] **Step 2: Run, expect FAIL** — route_writer still reads `_settings.TRAEFIK_RATELIMIT_*`.
  `.venv/bin/python -m pytest tests/test_route_writer.py::test_ratelimit_middleware_uses_live_settings -v`

- [ ] **Step 3: Switch route_writer reads** — in `backend/app/services/route_writer.py`, where `styx-ratelimit` is built, replace the two `_settings.TRAEFIK_RATELIMIT_*` reads with the live store:

```python
        "styx-ratelimit": {
            "rateLimit": {
                "average": _sys_settings.get("TRAEFIK_RATELIMIT_AVERAGE"),
                "burst": _sys_settings.get("TRAEFIK_RATELIMIT_BURST"),
            }
        },
```

  and add near the top of `route_writer.py` (after the existing imports):

```python
from app.services.settings_store import settings as _sys_settings
```

- [ ] **Step 4: Switch workstation reads** — in `backend/app/services/workstations.py`, add the same import at the top:

```python
from app.services.settings_store import settings as _sys_settings
```

  Replace line ~181 `_settings.WORKSTATION_OFFLINE_AFTER_S` with `_sys_settings.get("WORKSTATION_OFFLINE_AFTER_S")`. Then grep the backend for any `_settings.WORKSTATION_IDLE_TIMEOUT_S` use and replace each with `_sys_settings.get("WORKSTATION_IDLE_TIMEOUT_S")`:

```bash
grep -rn "WORKSTATION_IDLE_TIMEOUT_S\|WORKSTATION_OFFLINE_AFTER_S" backend/app --include=*.py | grep "_settings\."
```

  (Replace each hit that reads from `_settings` with the `_sys_settings.get(...)` equivalent; leave `config.py` itself unchanged.)

- [ ] **Step 5: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_route_writer.py tests/test_workstation_monitor.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_writer.py backend/app/services/workstations.py backend/tests/test_route_writer.py
git commit -m "feat(settings): live Traefik rate-limit + workstation timeouts"
```

---

# PHASE 3 — Settings admin API + tab

### Task 10: system_settings router

**Files:**
- Create: `backend/app/routers/system_settings.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_system_settings_api.py`

- [ ] **Step 1: Failing tests** — create `backend/tests/test_system_settings_api.py`:

```python
async def test_get_settings_requires_admin(client):
    r = await client.get("/api/system-settings")
    assert r.status_code in (401, 403)


async def test_admin_gets_grouped_settings(admin_client):
    r = await admin_client.get("/api/system-settings")
    assert r.status_code == 200
    groups = r.json()
    keys = {s["key"] for g in groups for s in g["settings"]}
    assert "LOCKOUT_THRESHOLD" in keys


async def test_admin_patch_and_reset(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"LOCKOUT_THRESHOLD": 4})
    assert r.status_code == 200, r.text
    g = await admin_client.get("/api/system-settings")
    val = next(s["value"] for grp in g.json() for s in grp["settings"]
               if s["key"] == "LOCKOUT_THRESHOLD")
    assert val == 4
    r2 = await admin_client.post("/api/system-settings/LOCKOUT_THRESHOLD/reset")
    assert r2.status_code == 200


async def test_patch_rejects_unknown_key(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"NOPE": 1})
    assert r.status_code == 400


async def test_patch_rejects_out_of_bounds(admin_client):
    r = await admin_client.patch("/api/system-settings", json={"LOCKOUT_THRESHOLD": 0})
    assert r.status_code == 400
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_system_settings_api.py -v` (404s).

- [ ] **Step 3: Implement router** — create `backend/app/routers/system_settings.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.settings_store import settings, SCHEMA

router = APIRouter()


@router.get("")
async def get_settings(admin: User = Depends(require_admin)):
    return settings.effective()


@router.patch("")
async def patch_settings(body: dict, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    if not body:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No settings provided")
    for key in body:
        if key not in SCHEMA:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {key}")
    try:
        for key, value in body.items():
            await settings.set(session, key, value, actor_id=admin.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    await audit_request(session, request, "settings.update", user_id=admin.id,
                        detail={"keys": sorted(body.keys())})
    await session.commit()
    return settings.effective()


@router.post("/{key}/reset")
async def reset_setting(key: str, request: Request,
                        admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    if key not in SCHEMA:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown setting: {key}")
    await settings.reset(session, key, actor_id=admin.id)
    await audit_request(session, request, "settings.reset", user_id=admin.id,
                        detail={"key": key})
    await session.commit()
    return settings.effective()
```

  Register in `backend/app/main.py` (with the other routers):

```python
from app.routers import system_settings as system_settings_router
app.include_router(system_settings_router.router, prefix="/api/system-settings", tags=["system-settings"])
```

  (Add the import next to the existing router imports at the top of main.py; add the `include_router` line next to the others.)

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_system_settings_api.py -v`

- [ ] **Step 5: ruff + commit**

```bash
.venv/bin/python -m ruff check app/routers/system_settings.py tests/test_system_settings_api.py
git add backend/app/routers/system_settings.py backend/app/main.py backend/tests/test_system_settings_api.py
git commit -m "feat(api): admin system-settings GET/PATCH/reset"
```

---

### Task 11: Settings panel (frontend)

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/components/system/system-settings-panel.tsx`
- Modify: `frontend/src/components/settings/nav-config.tsx`

**Invoke the `frontend-design` skill for this task** to keep visual quality consistent with the existing panels.

- [ ] **Step 1: Add API methods** — in `frontend/src/api/client.ts`, add to the `api` object (match the existing `request<T>` style):

```ts
  getSystemSettings: () =>
    request<{ group: string; label: string; settings: {
      key: string; label: string; help: string; type: "int" | "bool" | "rate";
      value: number | boolean | string; default: number | boolean | string;
      min: number | null; max: number | null }[] }[]>("/system-settings"),
  updateSystemSettings: (changes: Record<string, number | boolean | string>) =>
    request("/system-settings", { method: "PATCH", body: JSON.stringify(changes) }),
  resetSystemSetting: (key: string) =>
    request(`/system-settings/${key}/reset`, { method: "POST" }),
```

- [ ] **Step 2: Build the panel** — create `frontend/src/components/system/system-settings-panel.tsx`. Requirements (reuse the `UsersPanel` card/table idioms, `Card`/`Button`/`Input`/`Switch` from `@/components/ui`, TanStack Query, and `sonner` toasts):
  - `useQuery({ queryKey: ["system-settings"], queryFn: api.getSystemSettings })`.
  - Render one `Card` per group (`label`). Inside, one row per setting: `label` + help tooltip, and an editor by `type` — `int` → number `Input` (enforce `min`/`max` client-side), `bool` → `Switch`, `rate` → text `Input` with pattern `^\d+/\d+$`.
  - Track local edits in component state seeded from the query; a per-group **Save** button calls `api.updateSystemSettings(changedKeysForGroup)` via `useMutation`, then `qc.invalidateQueries({ queryKey: ["system-settings"] })` and `toast.success`. On error `toast.error(e.message)`.
  - A per-row **Reset to default** (shown when `value !== default`) calls `api.resetSystemSetting(key)`.
  - Client validation mirrors `min`/`max`/rate-pattern; block Save and show inline message when invalid.

- [ ] **Step 3: Register the nav section** — in `frontend/src/components/settings/nav-config.tsx`:
  - import `SlidersHorizontal` from `lucide-react` and `SystemSettingsPanel` from `@/components/system/system-settings-panel`.
  - Add to the `administration` category's `sections` array:

```tsx
      { id: "settings", label: "Settings", icon: SlidersHorizontal,
        description: "Tune security, rate limits, timeouts, and password policy.",
        tooltip: "Server behavioral settings (applied live)", Component: SystemSettingsPanel },
```

- [ ] **Step 4: Type-check** — `cd frontend && npx tsc --noEmit` → no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/system/system-settings-panel.tsx frontend/src/components/settings/nav-config.tsx
git commit -m "feat(ui): admin Settings panel for server behavioral knobs"
```

---

# PHASE 4 — Password policy

### Task 12: validate_password + current_policy

**Files:**
- Modify: `backend/app/security/passwords.py`
- Test: `backend/tests/test_passwords.py`

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_passwords.py`:

```python
def test_validate_password_length():
    from app.security.passwords import validate_password, PasswordPolicy
    p = PasswordPolicy(min_length=12, require_upper=False, require_lower=False,
                       require_digit=False, require_symbol=False)
    import pytest
    with pytest.raises(ValueError):
        validate_password("short", p)
    validate_password("x" * 12, p)  # ok


def test_validate_password_classes():
    from app.security.passwords import validate_password, PasswordPolicy
    import pytest
    p = PasswordPolicy(min_length=4, require_upper=True, require_lower=True,
                       require_digit=True, require_symbol=True)
    with pytest.raises(ValueError):
        validate_password("abcd", p)            # missing upper/digit/symbol
    validate_password("Ab1!", p)                # satisfies all
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_passwords.py -k validate_password -v`

- [ ] **Step 3: Implement** — append to `backend/app/security/passwords.py`:

```python
import re
from dataclasses import dataclass


@dataclass
class PasswordPolicy:
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_symbol: bool


def validate_password(password: str, policy: PasswordPolicy) -> None:
    """Raise ValueError listing every unmet rule; return None if compliant."""
    problems: list[str] = []
    if len(password) < policy.min_length:
        problems.append(f"at least {policy.min_length} characters")
    if policy.require_upper and not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if policy.require_lower and not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if policy.require_digit and not re.search(r"\d", password):
        problems.append("a digit")
    if policy.require_symbol and not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")
    if problems:
        raise ValueError("Password must contain " + ", ".join(problems) + ".")


def current_policy() -> PasswordPolicy:
    from app.services.settings_store import settings
    return PasswordPolicy(
        min_length=settings.get("PASSWORD_MIN_LENGTH"),
        require_upper=settings.get("PASSWORD_REQUIRE_UPPER"),
        require_lower=settings.get("PASSWORD_REQUIRE_LOWER"),
        require_digit=settings.get("PASSWORD_REQUIRE_DIGIT"),
        require_symbol=settings.get("PASSWORD_REQUIRE_SYMBOL"),
    )
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_passwords.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/passwords.py backend/tests/test_passwords.py
git commit -m "feat(passwords): policy dataclass + validate_password"
```

---

### Task 13: Enforce policy at setup + accept-invite

**Files:**
- Modify: `backend/app/routers/auth.py` (`setup`, `accept_invite`), `backend/app/schemas.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_auth_router.py`:

```python
async def test_setup_enforces_password_policy(client, session):
    from app.services.settings_store import settings
    await settings.set(session, "PASSWORD_REQUIRE_DIGIT", True, actor_id=None)
    await settings.set(session, "PASSWORD_MIN_LENGTH", 12, actor_id=None)
    await session.commit()
    r = await client.post("/api/auth/setup",
                          json={"username": "admin", "password": "no-digits-here!"})
    assert r.status_code == 422, r.text
```

- [ ] **Step 2: Run, expect FAIL** — setup currently ignores policy.
  `.venv/bin/python -m pytest tests/test_auth_router.py::test_setup_enforces_password_policy -v`

- [ ] **Step 3: Relax the static schema minimum + enforce policy** — in `backend/app/schemas.py`, change `SetupRequest.password` and `AcceptInviteRequest.password` to not hard-pin a 12-min (policy now governs):

```python
    password: str = Field(min_length=8, max_length=256)
```

  In `backend/app/routers/auth.py`, add the import:

```python
from app.security.passwords import hash_password, verify_password, validate_password, current_policy
```

  (Replace the existing `from app.security.passwords import hash_password, verify_password` line.)

  In `setup`, before `user = User(...)`, add:

```python
    try:
        validate_password(body.password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
```

  In `accept_invite`, before the password is hashed into the new `User`, add the same 4-line guard.

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_auth_router.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/app/schemas.py backend/tests/test_auth_router.py
git commit -m "feat(auth): enforce password policy at setup + accept-invite"
```

---

# PHASE 5 — User management backend

### Task 14: Expand UserOut + list_users

**Files:**
- Modify: `backend/app/schemas.py` (`UserOut`), `backend/app/routers/users.py` (`list_users`), and the other `UserOut(...)` constructions in users.py + `auth.py` `me`.
- Test: `backend/tests/test_users_role.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_users_role.py`:

```python
async def test_list_users_includes_status_fields(admin_client, session):
    from app.models import User
    from app.security.passwords import hash_password
    from datetime import datetime, timezone, timedelta
    session.add(User(username="lockme", password_hash=hash_password("x" * 12),
                     locked_until=datetime.now(timezone.utc) + timedelta(minutes=5),
                     failed_count=3))
    await session.commit()
    r = await admin_client.get("/api/users")
    row = next(u for u in r.json() if u["username"] == "lockme")
    assert row["failed_count"] == 3
    assert row["locked_until"] is not None
    assert "last_login" in row
```

- [ ] **Step 2: Run, expect FAIL** — `UserOut` lacks the fields.
  `.venv/bin/python -m pytest tests/test_users_role.py::test_list_users_includes_status_fields -v`

- [ ] **Step 3: Expand schema + constructions** — in `backend/app/schemas.py`, change `UserOut`:

```python
class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool
    last_login: str | None = None
    locked_until: str | None = None
    failed_count: int = 0
```

  Add a helper at the bottom of `backend/app/routers/users.py` and use it everywhere a `UserOut` is built in that file:

```python
def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id, username=u.username, email=u.email, role=u.role,
        is_active=u.is_active,
        last_login=u.last_login.isoformat() if u.last_login else None,
        locked_until=u.locked_until.isoformat() if u.locked_until else None,
        failed_count=u.failed_count,
    )
```

  Replace the `UserOut(...)` constructions in `list_users`, `disable_user`, `change_role` with `_user_out(u)` / `_user_out(user)`. (Leave `auth.py` `me`'s `UserOut(...)` as-is — the extra fields default and are harmless; do not change auth.py here.)

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_users_role.py tests/test_auth_router.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/users.py backend/tests/test_users_role.py
git commit -m "feat(users): expose last_login/locked_until/failed_count"
```

---

### Task 15: Unlock user

**Files:**
- Modify: `backend/app/routers/users.py`
- Test: `backend/tests/test_user_admin_actions.py` (new)

- [ ] **Step 1: Failing test** — create `backend/tests/test_user_admin_actions.py`:

```python
from datetime import datetime, timezone, timedelta
from app.models import User
from app.security.passwords import hash_password


async def _mk(session, name="target"):
    u = User(username=name, password_hash=hash_password("x" * 12))
    session.add(u)
    await session.commit()
    return u


async def test_unlock_clears_lock(admin_client, session):
    u = await _mk(session)
    u.failed_count = 9
    u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=5)
    session.add(u)
    await session.commit()
    r = await admin_client.post(f"/api/users/{u.id}/unlock")
    assert r.status_code == 200, r.text
    await session.refresh(u)
    assert u.failed_count == 0 and u.locked_until is None


async def test_unlock_requires_admin(client, session):
    u = await _mk(session, "t2")
    r = await client.post(f"/api/users/{u.id}/unlock")
    assert r.status_code in (401, 403)
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_user_admin_actions.py -k unlock -v`

- [ ] **Step 3: Implement** — in `backend/app/routers/users.py`, add:

```python
@router.post("/{user_id}/unlock", response_model=UserOut)
async def unlock_user(user_id: str, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user.failed_count = 0
    user.locked_until = None
    session.add(user)
    await audit_request(session, request, "user.unlock", user_id=admin.id, resource=user.id)
    await session.commit()
    return _user_out(user)
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_user_admin_actions.py -k unlock -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/users.py backend/tests/test_user_admin_actions.py
git commit -m "feat(users): admin unlock endpoint"
```

---

### Task 16: Admin reset password (one-time temp)

**Files:**
- Modify: `backend/app/routers/users.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_user_admin_actions.py`

- [ ] **Step 1: Failing test** — append to `backend/tests/test_user_admin_actions.py`:

```python
async def test_reset_password_returns_temp_and_rotates(admin_client, session):
    from app.models import RefreshToken
    from app.security.passwords import verify_password
    u = await _mk(session, "resetme")
    session.add(RefreshToken(jti="j1", user_id=u.id, family_id="j1",
                             expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
    await session.commit()
    r = await admin_client.post(f"/api/users/{u.id}/reset-password")
    assert r.status_code == 200, r.text
    temp = r.json()["temp_password"]
    assert len(temp) >= 12
    await session.refresh(u)
    assert u.must_change_pw is True
    assert verify_password(temp, u.password_hash)
    tok = await session.get(RefreshToken, "j1")
    assert tok.revoked is True
```

- [ ] **Step 2: Run, expect FAIL** — `.venv/bin/python -m pytest tests/test_user_admin_actions.py -k reset_password -v`

- [ ] **Step 3: Implement** — add a response schema to `backend/app/schemas.py`:

```python
class TempPasswordOut(BaseModel):
    temp_password: str
```

  In `backend/app/routers/users.py` add imports + endpoint. At the top, extend imports:

```python
from app.models import User, Invite, RefreshToken
from app.schemas import UserOut, CreateInviteRequest, InviteOut, TempPasswordOut
from app.security.passwords import hash_password
from app.security.passwords import current_policy
from sqlmodel import select, update
```

  (Merge with the existing `from sqlmodel import select` import — make it `select, update`.)

  Add a temp-password generator and the endpoint:

```python
def _gen_temp_password(policy) -> str:
    # Build a password that always satisfies the active policy.
    import secrets, string
    base = secrets.token_urlsafe(max(policy.min_length, 16))
    return f"A{base}a9!"[: max(policy.min_length + 4, 20)]


@router.post("/{user_id}/reset-password", response_model=TempPasswordOut)
async def reset_password(user_id: str, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    temp = _gen_temp_password(current_policy())
    user.password_hash = hash_password(temp)
    user.must_change_pw = True
    user.failed_count = 0
    user.locked_until = None
    session.add(user)
    await session.exec(update(RefreshToken)
                       .where(RefreshToken.user_id == user.id)
                       .values(revoked=True))
    await audit_request(session, request, "user.reset_password", user_id=admin.id,
                        resource=user.id)
    await session.commit()
    return TempPasswordOut(temp_password=temp)
```

  (Note: the audit detail intentionally never contains the temp password.)

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_user_admin_actions.py -k reset_password -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/users.py backend/app/schemas.py backend/tests/test_user_admin_actions.py
git commit -m "feat(users): admin reset-password (one-time temp, rotates tokens)"
```

---

### Task 17: Force password change

**Files:**
- Modify: `backend/app/routers/users.py`
- Test: `backend/tests/test_user_admin_actions.py`

- [ ] **Step 1: Failing test** — append:

```python
async def test_force_password_change(admin_client, session):
    u = await _mk(session, "forceme")
    r = await admin_client.post(f"/api/users/{u.id}/force-password-change")
    assert r.status_code == 200, r.text
    await session.refresh(u)
    assert u.must_change_pw is True
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — add to `backend/app/routers/users.py`:

```python
@router.post("/{user_id}/force-password-change", response_model=UserOut)
async def force_password_change(user_id: str, request: Request,
                                admin: User = Depends(require_admin),
                                session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user.must_change_pw = True
    session.add(user)
    await audit_request(session, request, "user.force_password_change",
                        user_id=admin.id, resource=user.id)
    await session.commit()
    return _user_out(user)
```

- [ ] **Step 4: Run, expect PASS.**

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/users.py backend/tests/test_user_admin_actions.py
git commit -m "feat(users): force-password-change endpoint"
```

---

### Task 18: Delete user (if owns nothing)

**Files:**
- Modify: `backend/app/routers/users.py`
- Test: `backend/tests/test_user_admin_actions.py`

- [ ] **Step 1: Failing tests** — append:

```python
async def test_delete_blocked_when_owns_instances(admin_client, session):
    from app.models import Instance, ServiceTemplate
    u = await _mk(session, "owner")
    tmpl = ServiceTemplate(name="t-own", display_name="t", image="img", owner_id=u.id)
    session.add(tmpl)
    await session.commit()
    session.add(Instance(template_id=tmpl.id, owner_id=u.id, name="i", subdomain="own-i"))
    await session.commit()
    r = await admin_client.delete(f"/api/users/{u.id}")
    assert r.status_code == 409, r.text


async def test_delete_empty_user_ok(admin_client, session):
    u = await _mk(session, "empty")
    r = await admin_client.delete(f"/api/users/{u.id}")
    assert r.status_code == 200, r.text
    assert await session.get(User, u.id) is None


async def test_cannot_delete_self(admin_client, session):
    from sqlmodel import select
    me = (await session.exec(select(User).where(User.username == "admin"))).first()
    r = await admin_client.delete(f"/api/users/{me.id}")
    assert r.status_code == 400
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — add to `backend/app/routers/users.py` (imports already include `select`, `update`, `Instance`? add `Instance, ServiceTemplate, FederatedIdentity` to the models import):

```python
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate, FederatedIdentity
```

```python
@router.delete("/{user_id}")
async def delete_user(user_id: str, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete yourself")
    if user.role == "admin":
        admins = (await session.exec(select(User).where(
            User.role == "admin", User.is_active == True))).all()  # noqa: E712
        if len(admins) <= 1:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete the last admin")
    inst = (await session.exec(select(Instance).where(Instance.owner_id == user.id))).all()
    tmpls = (await session.exec(select(ServiceTemplate).where(ServiceTemplate.owner_id == user.id))).all()
    if inst or tmpls:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"User owns {len(inst)} instance(s) and {len(tmpls)} template(s); "
                   "reassign or remove them first.")
    await session.exec(update(RefreshToken).where(RefreshToken.user_id == user.id).values(revoked=True))
    fids = (await session.exec(select(FederatedIdentity).where(FederatedIdentity.user_id == user.id))).all()
    for f in fids:
        await session.delete(f)
    await session.delete(user)
    await audit_request(session, request, "user.delete", user_id=admin.id, resource=user_id)
    await session.commit()
    return {"ok": True}
```

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_user_admin_actions.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/users.py backend/tests/test_user_admin_actions.py
git commit -m "feat(users): delete user when they own no resources"
```

---

### Task 19: Self change-password

**Files:**
- Modify: `backend/app/routers/auth.py`, `backend/app/schemas.py`
- Test: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Failing tests** — append to `backend/tests/test_auth_router.py`:

```python
async def test_change_password_success(member_client, session):
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "correct horse battery staple",
                                       "new_password": "NewLongEnough123!"})
    assert r.status_code == 200, r.text
    # must_change_pw cleared
    from app.models import User
    from sqlmodel import select
    u = (await session.exec(select(User).where(User.username == "member"))).first()
    assert u.must_change_pw is False


async def test_change_password_wrong_old(member_client):
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "wrong",
                                       "new_password": "NewLongEnough123!"})
    assert r.status_code == 401


async def test_change_password_weak_new(member_client, session):
    from app.services.settings_store import settings
    await settings.set(session, "PASSWORD_REQUIRE_SYMBOL", True, actor_id=None)
    await session.commit()
    r = await member_client.post("/api/auth/change-password",
                                 json={"old_password": "correct horse battery staple",
                                       "new_password": "NoSymbolsHere123"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run, expect FAIL.**

- [ ] **Step 3: Implement** — add schema to `backend/app/schemas.py`:

```python
class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=256)
```

  In `backend/app/routers/auth.py` import it (extend the existing schemas import) and add the endpoint (place it after `me`):

```python
@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response,
                          session: AsyncSession = Depends(get_session),
                          user: User = Depends(get_current_user)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    try:
        validate_password(body.new_password, current_policy())
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    user.password_hash = hash_password(body.new_password)
    user.must_change_pw = False
    session.add(user)
    # Rotate sessions: revoke all of the user's refresh tokens, then issue a fresh one.
    await session.exec(update(RefreshToken)
                       .where(RefreshToken.user_id == user.id)
                       .values(revoked=True))
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.password_change", user_id=user.id)
    await session.commit()
    return {"ok": True}
```

  (`update`, `RefreshToken`, `get_current_user`, `validate_password`, `current_policy`, `hash_password`, `verify_password` are imported already per earlier tasks; add `ChangePasswordRequest` to the `from app.schemas import ...` line.)

- [ ] **Step 4: Run, expect PASS** — `.venv/bin/python -m pytest tests/test_auth_router.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/app/schemas.py backend/tests/test_auth_router.py
git commit -m "feat(auth): self change-password with policy + token rotation"
```

---

# PHASE 6 — User management frontend

### Task 20: Users panel actions

**Files:**
- Modify: `frontend/src/api/client.ts`, `frontend/src/components/system/users-panel.tsx`

**Invoke the `frontend-design` skill for this task.**

- [ ] **Step 1: Add API methods** — in `frontend/src/api/client.ts`, extend `listUsers`'s return type to include `last_login: string | null; locked_until: string | null; failed_count: number;` and add:

```ts
  unlockUser: (id: string) => request(`/users/${id}/unlock`, { method: "POST" }),
  resetUserPassword: (id: string) =>
    request<{ temp_password: string }>(`/users/${id}/reset-password`, { method: "POST" }),
  forcePasswordChange: (id: string) =>
    request(`/users/${id}/force-password-change`, { method: "POST" }),
  deleteUser: (id: string) => request(`/users/${id}`, { method: "DELETE" }),
  changePassword: (old_password: string, new_password: string) =>
    request("/auth/change-password", { method: "POST",
      body: JSON.stringify({ old_password, new_password }) }),
```

- [ ] **Step 2: Extend the panel** — in `frontend/src/components/system/users-panel.tsx`, building on the existing table:
  - Add a **Locked** badge in the Status cell when `u.locked_until` parses to a future date; show an **Unlock** button (`api.unlockUser`) that invalidates `["users"]` + `toast`.
  - Add a **last login** column rendering `u.last_login` (humanized or `—`).
  - Add a **Reset password** action opening a dialog (reuse `@/components/ui/dialog`) that calls `api.resetUserPassword(id)` and shows the returned `temp_password` once with a copy button (mirror the existing invite-URL copy idiom).
  - Add a **Force password change** action (`api.forcePasswordChange`).
  - Add a **Delete** action guarded by `ConfirmDialog` (`@/components/common/confirm-dialog`); on the 409 response surface the server message via `toast.error(e.message)`.
  - All mutations: `onError: (e: Error) => toast.error(e.message)` and invalidate `["users"]` on success.

- [ ] **Step 3: Type-check** — `cd frontend && npx tsc --noEmit` → no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/system/users-panel.tsx
git commit -m "feat(ui): user unlock/reset/force-change/delete + last-login"
```

---

### Task 21: Self change-password screen + forced-change redirect

**Files:**
- Create: `frontend/src/pages/ChangePasswordPage.tsx`
- Modify: `frontend/src/pages/LoginPage.tsx`, the app router (where routes are registered).

**Invoke the `frontend-design` skill for this task.**

- [ ] **Step 1: Build the page** — create `frontend/src/pages/ChangePasswordPage.tsx`: a centered form (reuse `PasswordInput`, `Button`, the `LoginPage` visual shell) with Old / New / Confirm fields; calls `api.changePassword(old, neu)`; on success `toast.success` and navigate to `/`; on error `toast.error(e.message)` (422 policy message surfaces verbatim). Show the password-policy hints by fetching nothing — just a static helper line ("Use a strong password meeting the server policy.").

- [ ] **Step 2: Wire forced change** — `api.login` already returns `must_change_pw`. In `frontend/src/pages/LoginPage.tsx`, after a successful `api.login(...)`, if the response has `must_change_pw === true`, `nav("/change-password")` instead of the normal target. Register the `/change-password` route in the app router next to `/login` (authenticated; if your router guards by auth, place it inside the authed area but reachable while `must_change_pw`).

- [ ] **Step 3: Type-check** — `cd frontend && npx tsc --noEmit` → no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/ChangePasswordPage.tsx frontend/src/pages/LoginPage.tsx
git commit -m "feat(ui): self change-password screen + forced-change redirect"
```

---

# PHASE 7 — Verification

### Task 22: Full verification

- [ ] **Step 1: Backend suite** — `cd backend && .venv/bin/python -m pytest -q` → all pass.
- [ ] **Step 2: Lint** — `cd backend && .venv/bin/python -m ruff check app/ tests/` → clean.
- [ ] **Step 3: Frontend types** — `cd frontend && npx tsc --noEmit` → clean. (Note: `npm run build` needs `npm install` first if `vitest`/`@testing-library/jest-dom` type-defs are missing in this environment.)
- [ ] **Step 4: Live smoke** — boot the app against a throwaway DB; verify: PATCH `/api/system-settings {"LOCKOUT_THRESHOLD":3}` then drive 4 bad logins → 423 (live setting applied without restart); unlock endpoint clears it; reset-password returns a temp password and the old refresh token is revoked; `/api/auth/change-password` rotates the session.
- [ ] **Step 5: Finish the branch** — use the `superpowers:finishing-a-development-branch` skill.

---

## Self-Review Notes

- **Spec coverage:** Component 1 (store) → Tasks 2,3,4; Component 2 (all-live) → Tasks 5,6,7,8,9; Component 3 (settings API+tab) → Tasks 10,11; Component 4 (user mgmt) → Tasks 14–18 + self-change 19; Component 5 (password policy) → Tasks 1,12,13 (+ enforcement at change/reset inside 16/19). Secret-exclusion verified by `test_schema_excludes_secrets` (Task 3).
- **Type consistency:** `settings.get/set/reset/reload/effective/reset_cache`, `SCHEMA`, `SettingSpec`, `PasswordPolicy`, `validate_password`, `current_policy`, `_user_out`, `TempPasswordOut`, `ChangePasswordRequest` — names identical across tasks and tests.
- **Live-read safety:** `tokens.py` and `rate_limit.py` import `settings_store` lazily inside functions to avoid an import cycle (settings_store imports config + models only). `set()` imports `route_writer` lazily for the same reason.
- **Known interaction:** changing `RATE_LIMIT_*` creates a fresh `SlidingWindow` for the new spec (counters reset) — acceptable and noted. Traefik knobs apply via a `routes.yml` rewrite triggered in `settings.set`.
- **No frozen-default leak:** `main.py` middleware registration drops `auth_spec`/`default_spec` (Task 8) so nothing reads the boot-time value after the refactor.
