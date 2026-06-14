# Brute-Force Protection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add layered login brute-force protection — Traefik proxy rate-limit, per-username lockout, and an app-driven Traefik IP denylist (forwardAuth ban-gate) — on top of the existing in-memory IP rate limiter.

**Architecture:** Four layers. L1: native Traefik `rateLimit` middleware (coarse flood wall). L2: per-username failed-attempt lockout persisted on `User`. L3: per-IP abuse detector writes `banned_ip` rows; a `GET /api/auth/ban-check` endpoint (backed by an in-memory cache) is wired as a Traefik forwardAuth middleware so banned IPs are refused at the proxy. L4: keep the transient 5/60 window in-memory; persist only the durable lockout + ban state in SQLite.

**Tech Stack:** FastAPI, SQLModel, async SQLite (aiosqlite), Traefik v3 dynamic config (YAML via `route_writer.py`), pytest + httpx AsyncClient.

**Spec:** `docs/superpowers/specs/2026-06-13-brute-force-protection-design.md`

---

## File Structure

- `backend/app/config.py` — MODIFY: new lockout/ban/rate-limit settings (ints).
- `backend/app/models.py` — MODIFY: `User.failed_count`, `User.locked_until`; new `BannedIP` table.
- `backend/app/database.py` — MODIFY: migration + backfill for the new `User` columns.
- `backend/app/services/abuse.py` — CREATE: `IpFailTracker`, `BanCache`, `ban_ip()`, module singletons `fail_tracker` / `ban_cache`.
- `backend/app/routers/auth.py` — MODIFY: lockout logic + abuse detector in `login`; new `GET /ban-check`.
- `backend/app/middleware/rate_limit.py` — MODIFY: bypass `/api/auth/ban-check` from the app rate limiter.
- `backend/app/services/route_writer.py` — MODIFY: emit `styx-ratelimit` + `ip-ban-gate` middlewares, attach to `api`/`frontend` (+ `-lan`) routers.
- `backend/tests/conftest.py` — MODIFY: autouse fixture resetting the abuse singletons between tests.
- `backend/tests/test_abuse.py` — CREATE: unit tests for tracker/cache/ban_ip.
- `backend/tests/test_auth_lockout.py` — CREATE: lockout + ban + ban-check integration tests.
- `backend/tests/test_config.py` — MODIFY: assert new defaults.
- `backend/tests/test_route_writer.py` — MODIFY: assert new middlewares emitted/attached.
- `frontend/src/lib/auth-errors.ts` — MODIFY: friendly messages for 423 / 403.

---

### Task 1: Config settings

**Files:**
- Modify: `backend/app/config.py:36` (after `RATE_LIMIT_INSTANCE_CREATE`)
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_config.py`:

```python
def test_brute_force_defaults():
    from app.config import Settings
    s = Settings()
    assert s.LOCKOUT_THRESHOLD == 10
    assert s.LOCKOUT_DURATION == 900
    assert s.BAN_FAIL_THRESHOLD == 20
    assert s.BAN_FAIL_WINDOW == 600
    assert s.BAN_DURATION == 3600
    assert s.BAN_CACHE_TTL == 30
    assert s.TRAEFIK_RATELIMIT_AVERAGE == 100
    assert s.TRAEFIK_RATELIMIT_BURST == 50
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py::test_brute_force_defaults -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'LOCKOUT_THRESHOLD'`

- [ ] **Step 3: Add the settings**

In `backend/app/config.py`, immediately after the line
`    RATE_LIMIT_INSTANCE_CREATE: str = "10/3600"  # 10 creates per hour per user`
insert:

```python
    # --- Brute-force protection ---
    LOCKOUT_THRESHOLD: int = 10           # failed logins per username before lock
    LOCKOUT_DURATION: int = 900           # lock duration seconds (15 min)
    BAN_FAIL_THRESHOLD: int = 20          # failed logins per IP in window before ban
    BAN_FAIL_WINDOW: int = 600            # abuse-detector window seconds (10 min)
    BAN_DURATION: int = 3600              # IP ban duration seconds (1 h)
    BAN_CACHE_TTL: int = 30               # ban-set cache refresh interval seconds
    TRAEFIK_RATELIMIT_AVERAGE: int = 100  # L1 proxy avg req/s per IP
    TRAEFIK_RATELIMIT_BURST: int = 50     # L1 proxy burst per IP
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py::test_brute_force_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(config): brute-force protection settings"
```

---

### Task 2: User lockout fields + BannedIP model + migration

**Files:**
- Modify: `backend/app/models.py:28` (User), add `BannedIP` after `User`
- Modify: `backend/app/database.py:108` (migrations list), `:131` (backfills list)
- Test: `backend/tests/test_user_model.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_user_model.py`:

```python
async def test_user_lockout_defaults(session):
    from app.models import User
    from app.security.passwords import hash_password
    u = User(username="lockme", password_hash=hash_password("x"))
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert u.failed_count == 0
    assert u.locked_until is None


async def test_banned_ip_roundtrip(session):
    from datetime import datetime, timezone, timedelta
    from app.models import BannedIP
    now = datetime.now(timezone.utc)
    session.add(BannedIP(ip="203.0.113.9", reason="test",
                         banned_at=now, expires_at=now + timedelta(hours=1)))
    await session.commit()
    got = await session.get(BannedIP, "203.0.113.9")
    assert got is not None
    assert got.reason == "test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_user_model.py::test_user_lockout_defaults tests/test_user_model.py::test_banned_ip_roundtrip -v`
Expected: FAIL (`User` has no `failed_count`; cannot import `BannedIP`)

- [ ] **Step 3: Add the model fields and table**

In `backend/app/models.py`, in `class User`, after the line `    last_login: datetime | None = None` add:

```python
    failed_count: int = 0
    locked_until: datetime | None = None
```

Then, immediately after the `User` class (before `class Invite`), add:

```python
class BannedIP(SQLModel, table=True):
    __tablename__ = "banned_ip"

    ip: str = Field(primary_key=True)
    reason: str = ""
    banned_at: datetime = Field(default_factory=_now)
    expires_at: datetime
```

- [ ] **Step 4: Add the migration for existing DBs**

In `backend/app/database.py`, inside `_run_migrations`, append to the `migrations` list (after the `workstations` entries, before the closing `]` at line ~108):

```python
        ("users", "failed_count", "INTEGER DEFAULT 0"),
        ("users", "locked_until", "TIMESTAMP"),
```

And append to the `backfills` list (after the `workstations` entries):

```python
        ("users", "failed_count", "0"),
```

(The new `banned_ip` table is created automatically by `SQLModel.metadata.create_all` in `init_db`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_user_model.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/database.py backend/tests/test_user_model.py
git commit -m "feat(models): User lockout fields + BannedIP table"
```

---

### Task 3: Abuse service (tracker, ban cache, ban writer)

**Files:**
- Create: `backend/app/services/abuse.py`
- Test: `backend/tests/test_abuse.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_abuse.py`:

```python
from datetime import datetime, timezone, timedelta

import pytest

from app.services.abuse import IpFailTracker, BanCache, ban_ip
from app.models import BannedIP


def test_fail_tracker_fires_at_threshold():
    t = IpFailTracker(threshold=3, window=600)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=1) is False
    assert t.record("ip1", now=2) is True   # 3rd fail crosses


def test_fail_tracker_clears_after_fire():
    t = IpFailTracker(threshold=2, window=600)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=1) is True
    # window cleared on fire -> next fail starts fresh, does not re-fire immediately
    assert t.record("ip1", now=2) is False


def test_fail_tracker_window_slides():
    t = IpFailTracker(threshold=2, window=60)
    assert t.record("ip1", now=0) is False
    assert t.record("ip1", now=61) is False  # first hit aged out


def test_fail_tracker_keys_isolated():
    t = IpFailTracker(threshold=2, window=60)
    assert t.record("ip1", now=0) is False
    assert t.record("ip2", now=0) is False


async def test_ban_ip_inserts_and_updates(session):
    now = datetime.now(timezone.utc)
    await ban_ip(session, "203.0.113.5", "brute-force", 3600, now=now)
    await session.commit()
    row = await session.get(BannedIP, "203.0.113.5")
    assert row.expires_at == now + timedelta(seconds=3600)
    # second ban updates the same row, not a duplicate
    later = now + timedelta(seconds=10)
    await ban_ip(session, "203.0.113.5", "again", 60, now=later)
    await session.commit()
    row2 = await session.get(BannedIP, "203.0.113.5")
    assert row2.reason == "again"
    assert row2.expires_at == later + timedelta(seconds=60)


async def test_ban_cache_reports_active_and_expired(session):
    now = datetime.now(timezone.utc)
    await ban_ip(session, "198.51.100.2", "x", 3600, now=now)
    await session.commit()
    cache = BanCache(ttl=30)
    # active ban
    assert await cache.is_banned(session, "198.51.100.2", now=now, mono=0.0) is True
    # unrelated IP
    assert await cache.is_banned(session, "10.0.0.1", now=now, mono=0.0) is False
    # after expiry, a refresh drops the row -> no longer banned
    future = now + timedelta(hours=2)
    cache.invalidate()
    assert await cache.is_banned(session, "198.51.100.2", now=future, mono=100.0) is False


async def test_ban_cache_invalidate_forces_refresh(session):
    now = datetime.now(timezone.utc)
    cache = BanCache(ttl=9999)
    assert await cache.is_banned(session, "192.0.2.1", now=now, mono=0.0) is False
    await ban_ip(session, "192.0.2.1", "x", 3600, now=now)
    await session.commit()
    # without invalidate the long TTL would hide the new ban
    cache.invalidate()
    assert await cache.is_banned(session, "192.0.2.1", now=now, mono=1.0) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_abuse.py -v`
Expected: FAIL (`No module named 'app.services.abuse'`)

- [ ] **Step 3: Implement the service**

Create `backend/app/services/abuse.py`:

```python
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.models import BannedIP

_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IpFailTracker:
    """In-memory per-IP failed-login counter over a sliding window.

    record() returns True exactly when an IP first reaches the threshold,
    signalling the caller to persist a ban. The IP's window is cleared on that
    event so it does not re-fire on every subsequent failure.
    """

    def __init__(self, threshold: int, window: int):
        self.threshold = threshold
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)

    def record(self, ip: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[ip]
        q.append(now)
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.threshold:
            q.clear()
            return True
        return False

    def reset(self) -> None:
        self._hits.clear()


class BanCache:
    """In-memory snapshot of active IP bans, refreshed from the DB on a TTL.

    is_banned() is a dict lookup on the hot forward-auth path. invalidate()
    forces the next is_banned() to refresh — used right after writing a ban so
    it takes effect immediately.
    """

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._bans: dict[str, datetime] = {}
        self._loaded_at: float | None = None

    def invalidate(self) -> None:
        self._loaded_at = None

    async def refresh(self, session: AsyncSession, now: datetime | None = None) -> None:
        now = now or _now()
        result = await session.exec(select(BannedIP).where(BannedIP.expires_at > now))
        self._bans = {b.ip: b.expires_at for b in result.all()}

    async def is_banned(self, session: AsyncSession, ip: str,
                        now: datetime | None = None,
                        mono: float | None = None) -> bool:
        now = now or _now()
        mono = time.monotonic() if mono is None else mono
        if self._loaded_at is None or mono - self._loaded_at >= self.ttl:
            await self.refresh(session, now)
            self._loaded_at = mono
        exp = self._bans.get(ip)
        return exp is not None and exp > now


async def ban_ip(session: AsyncSession, ip: str, reason: str, duration: int,
                 now: datetime | None = None) -> None:
    now = now or _now()
    expires = now + timedelta(seconds=duration)
    existing = await session.get(BannedIP, ip)
    if existing:
        existing.reason = reason
        existing.banned_at = now
        existing.expires_at = expires
        session.add(existing)
    else:
        session.add(BannedIP(ip=ip, reason=reason, banned_at=now, expires_at=expires))


# Module singletons shared by the login flow and the ban-check endpoint.
fail_tracker = IpFailTracker(_settings.BAN_FAIL_THRESHOLD, _settings.BAN_FAIL_WINDOW)
ban_cache = BanCache(_settings.BAN_CACHE_TTL)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_abuse.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/abuse.py backend/tests/test_abuse.py
git commit -m "feat(abuse): IP fail tracker, ban cache, ban writer"
```

---

### Task 4: Reset abuse singletons between tests

**Files:**
- Modify: `backend/tests/conftest.py` (add an autouse fixture)

The `fail_tracker` and `ban_cache` are module singletons; their in-memory state would leak across tests. Reset them before each test.

- [ ] **Step 1: Add the autouse fixture**

In `backend/tests/conftest.py`, after the `session_fixture` definition (around line 33), add:

```python
@pytest.fixture(autouse=True)
def _reset_abuse_state():
    from app.services.abuse import fail_tracker, ban_cache
    fail_tracker.reset()
    ban_cache._bans.clear()
    ban_cache._loaded_at = None
    yield
```

- [ ] **Step 2: Run the abuse + rate-limit suites to confirm no regressions**

Run: `cd backend && .venv/bin/python -m pytest tests/test_abuse.py tests/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/conftest.py
git commit -m "test: reset abuse singletons between tests"
```

---

### Task 5: Per-username lockout in login

**Files:**
- Modify: `backend/app/routers/auth.py:13` (imports), `:136-150` (login)
- Test: `backend/tests/test_auth_lockout.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_auth_lockout.py`:

```python
import pytest


async def _make_user(session, name="victim", pw="correct horse battery staple"):
    from app.models import User
    from app.security.passwords import hash_password
    session.add(User(username=name, password_hash=hash_password(pw),
                     role="member", is_active=True))
    await session.commit()


async def test_lockout_after_threshold(client, session):
    await _make_user(session)
    # 10 wrong attempts -> 401 each; 11th is locked even with the WRONG password
    for _ in range(10):
        r = await client.post("/api/auth/login",
                              json={"username": "victim", "password": "nope"})
        assert r.status_code == 401, r.text
    r = await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    assert r.status_code == 423
    assert r.headers.get("Retry-After")


async def test_lockout_blocks_correct_password(client, session):
    await _make_user(session)
    for _ in range(10):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    # even the RIGHT password is refused while locked
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 423


async def test_success_resets_failed_count(client, session):
    from app.models import User
    from sqlmodel import select
    await _make_user(session)
    for _ in range(3):
        await client.post("/api/auth/login",
                          json={"username": "victim", "password": "nope"})
    r = await client.post("/api/auth/login",
                          json={"username": "victim",
                                "password": "correct horse battery staple"})
    assert r.status_code == 200
    u = (await session.exec(select(User).where(User.username == "victim"))).first()
    assert u.failed_count == 0
    assert u.locked_until is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_lockout.py -v`
Expected: FAIL (lockout returns 401 forever, never 423)

- [ ] **Step 3: Add imports**

In `backend/app/routers/auth.py`, add after line 21 (`from app.services.audit import audit_request`):

```python
from app.middleware.rate_limit import client_ip_from_headers
from app.services.abuse import fail_tracker, ban_cache, ban_ip
```

- [ ] **Step 4: Rewrite the login handler**

Replace the `login` function body (`backend/app/routers/auth.py:136-150`) with:

```python
@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    ip = client_ip_from_headers(request)
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()

    # Per-username lockout: refuse before checking the password.
    if user and user.locked_until and user.locked_until > _now():
        await audit_request(session, request, "auth.login_locked", user_id=user.id)
        await session.commit()
        retry = int((user.locked_until - _now()).total_seconds())
        raise HTTPException(
            status.HTTP_423_LOCKED, "Account temporarily locked",
            headers={"Retry-After": str(max(retry, 1))},
        )

    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        if user:
            user.failed_count += 1
            if user.failed_count >= _settings.LOCKOUT_THRESHOLD:
                user.locked_until = _now() + timedelta(seconds=_settings.LOCKOUT_DURATION)
                user.failed_count = 0
            session.add(user)
        # Per-IP abuse detector -> proxy ban (L3).
        if fail_tracker.record(ip):
            await ban_ip(session, ip, "brute-force: failed logins",
                         _settings.BAN_DURATION)
            ban_cache.invalidate()
        await audit_request(session, request, "auth.login_failed",
                            detail={"username": body.username})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    # Success: clear lockout state.
    user.failed_count = 0
    user.locked_until = None
    session.add(user)
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.login", user_id=user.id)
    await session.commit()
    return {"id": user.id, "username": user.username, "role": user.role,
            "must_change_pw": user.must_change_pw}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_lockout.py -v`
Expected: PASS

- [ ] **Step 6: Run the existing auth suite (no regressions)**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_router.py tests/test_auth_refresh_reuse.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_lockout.py
git commit -m "feat(auth): per-username lockout + IP abuse detector on login"
```

---

### Task 6: Ban-check endpoint

**Files:**
- Modify: `backend/app/routers/auth.py` (add endpoint after `login`)
- Test: `backend/tests/test_auth_lockout.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_auth_lockout.py`:

```python
async def test_ban_check_allows_unbanned(client):
    r = await client.get("/api/auth/ban-check")
    assert r.status_code == 200


async def test_ban_check_blocks_banned_ip(client, session):
    from app.services.abuse import ban_ip, ban_cache
    await ban_ip(session, "1.2.3.4", "test", 3600)
    await session.commit()
    ban_cache.invalidate()
    # client IP arrives via X-Forwarded-For (trusted behind the proxy)
    r = await client.get("/api/auth/ban-check",
                         headers={"X-Forwarded-For": "1.2.3.4"})
    assert r.status_code == 403
    # a different IP is still allowed
    r2 = await client.get("/api/auth/ban-check",
                          headers={"X-Forwarded-For": "5.6.7.8"})
    assert r2.status_code == 200


async def test_brute_force_bans_ip_after_threshold(client, session):
    from app.models import BannedIP
    await _make_user(session)
    # 20 failed logins from one IP -> ban row written
    for _ in range(20):
        await client.post("/api/auth/login",
                          headers={"X-Forwarded-For": "9.9.9.9"},
                          json={"username": "victim", "password": "nope"})
    row = await session.get(BannedIP, "9.9.9.9")
    assert row is not None
```

Note: the default `BAN_FAIL_THRESHOLD` is 20 and `LOCKOUT_THRESHOLD` is 10 — after 10 fails the user is locked (423), but those still count as IP failures via `fail_tracker.record`, so 20 IP failures still accrue and trigger the ban. The lockout 423 path does NOT record an IP failure (it returns before the fail branch); to reach 20 IP-recorded failures the test relies on the first 10 (401) plus continued attempts. Because the user locks at 10, attempts 11–20 hit the 423 branch and do NOT increment the tracker. **Therefore use a fresh username per attempt** to keep every attempt on the 401 path:

Replace the loop in `test_brute_force_bans_ip_after_threshold` with:

```python
    for i in range(20):
        await client.post("/api/auth/login",
                          headers={"X-Forwarded-For": "9.9.9.9"},
                          json={"username": f"nobody{i}", "password": "nope"})
    row = await session.get(BannedIP, "9.9.9.9")
    assert row is not None
```

(Unknown usernames take the 401 path every time, so all 20 are recorded against the IP.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_lockout.py::test_ban_check_allows_unbanned tests/test_auth_lockout.py::test_ban_check_blocks_banned_ip tests/test_auth_lockout.py::test_brute_force_bans_ip_after_threshold -v`
Expected: FAIL (`/ban-check` → 404)

- [ ] **Step 3: Add the endpoint**

In `backend/app/routers/auth.py`, immediately after the `login` function, add:

```python
@router.get("/ban-check")
async def ban_check(request: Request, session: AsyncSession = Depends(get_session)):
    """Traefik forwardAuth target: 403 if the client IP is banned, else 200.

    Called per-request by the proxy; backed by an in-memory ban cache so the
    hot path is a dict lookup, not a DB query.
    """
    ip = client_ip_from_headers(request)
    if await ban_cache.is_banned(session, ip):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access temporarily blocked")
    return Response(status_code=status.HTTP_200_OK)
```

(`Response` is already imported on line 6.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_lockout.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/tests/test_auth_lockout.py
git commit -m "feat(auth): GET /ban-check forwardAuth endpoint"
```

---

### Task 7: Exempt ban-check from the app rate limiter

**Files:**
- Modify: `backend/app/middleware/rate_limit.py:67-77` (dispatch)
- Test: `backend/tests/test_rate_limit.py` (append)

The proxy calls `/api/auth/ban-check` on every request; counting those against the per-IP default bucket would false-trip 429 on busy pages. Bypass that exact path.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_rate_limit.py`:

```python
def test_ban_check_is_exempt():
    from app.middleware.rate_limit import is_rate_limit_exempt
    assert is_rate_limit_exempt("/api/auth/ban-check") is True
    assert is_rate_limit_exempt("/api/auth/login") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py::test_ban_check_is_exempt -v`
Expected: FAIL (`cannot import name 'is_rate_limit_exempt'`)

- [ ] **Step 3: Add the exemption**

In `backend/app/middleware/rate_limit.py`, after `is_strict_auth` (line 58), add:

```python
_EXEMPT_PATHS = frozenset({"/api/auth/ban-check"})


def is_rate_limit_exempt(path: str) -> bool:
    return path in _EXEMPT_PATHS
```

Then in `RateLimitMiddleware.dispatch`, add a bypass as the first lines of the method (before resolving `ip`):

```python
    async def dispatch(self, request: Request, call_next):
        if is_rate_limit_exempt(request.url.path):
            return await call_next(request)
        ip = client_ip_from_headers(request)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(rate-limit): exempt /ban-check from app limiter"
```

---

### Task 8: Traefik rateLimit + ip-ban-gate middlewares

**Files:**
- Modify: `backend/app/services/route_writer.py:36-70` (middlewares + routers)
- Test: `backend/tests/test_route_writer.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_route_writer.py` (uses the existing `build_routes_config` import in that file):

```python
def test_emits_ratelimit_and_ban_gate_middlewares():
    cfg = build_routes_config([], "example.com", "tunnel")
    mw = cfg["http"]["middlewares"]
    assert mw["styx-ratelimit"]["rateLimit"]["average"] == 100
    assert mw["styx-ratelimit"]["rateLimit"]["burst"] == 50
    assert mw["ip-ban-gate"]["forwardAuth"]["address"] == \
        "http://backend:8000/api/auth/ban-check"


def test_api_router_has_ban_gate_and_ratelimit():
    cfg = build_routes_config([], "example.com", "tunnel")
    api_mw = cfg["http"]["routers"]["api"]["middlewares"]
    assert "ip-ban-gate" in api_mw
    assert "styx-ratelimit" in api_mw
    fe_mw = cfg["http"]["routers"]["frontend"]["middlewares"]
    assert "styx-ratelimit" in fe_mw
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer.py::test_emits_ratelimit_and_ban_gate_middlewares tests/test_route_writer.py::test_api_router_has_ban_gate_and_ratelimit -v`
Expected: FAIL (`KeyError: 'styx-ratelimit'` / `'middlewares'`)

- [ ] **Step 3: Emit the middlewares**

In `backend/app/services/route_writer.py`, in `build_routes_config`, extend the initial `middlewares` dict (currently lines 36-47) by adding two entries:

```python
    middlewares: dict = {
        "unavailable-rewrite": {
            "replacePath": {"path": "/api/instance-unavailable"}
        },
        "instance-unavailable-errors": {
            "errors": {
                "status": ["500-599"],
                "service": "api",
                "query": "/api/instance-unavailable",
            }
        },
        "styx-ratelimit": {
            "rateLimit": {
                "average": _settings.TRAEFIK_RATELIMIT_AVERAGE,
                "burst": _settings.TRAEFIK_RATELIMIT_BURST,
            }
        },
        "ip-ban-gate": {
            "forwardAuth": {
                "address": "http://backend:8000/api/auth/ban-check"
            }
        },
    }
```

- [ ] **Step 4: Attach to the frontend + api routers**

In the same function, in the `config` dict's `routers`, add a `middlewares` key to `frontend` and `api`:

```python
                "frontend": {
                    "rule": f"Host(`{domain}`)",
                    "service": "frontend",
                    "priority": 1,
                    "middlewares": ["styx-ratelimit"],
                    **_router_transport(deploy_mode, domain),
                },
                "api": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/api`)",
                    "service": "api",
                    "priority": 100,
                    "middlewares": ["ip-ban-gate", "styx-ratelimit"],
                    **_router_transport(deploy_mode, domain),
                },
```

- [ ] **Step 5: Attach to the LAN routers**

Still in `build_routes_config`, in the `if lan_serving:` block near the end (lines ~214-218), update the two `_lan_router` calls to pass middleware lists:

```python
    if lan_serving:
        config["http"]["routers"]["api-lan"] = _lan_router(
            "PathPrefix(`/api`)", "api", 100, ["ip-ban-gate", "styx-ratelimit"])
        config["http"]["routers"]["frontend-lan"] = _lan_router(
            "PathPrefix(`/`)", "frontend", 1, ["styx-ratelimit"])
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer.py tests/test_route_writer_workstations.py tests/test_route_writer_extra_ports.py -v`
Expected: PASS (existing route_writer tests still green)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/route_writer.py backend/tests/test_route_writer.py
git commit -m "feat(traefik): rateLimit + ip-ban-gate middlewares on api/frontend"
```

---

### Task 9: Frontend friendly messages for 423 / 403

**Files:**
- Modify: `frontend/src/lib/auth-errors.ts`

- [ ] **Step 1: Read the current mapper**

Run: `cat frontend/src/lib/auth-errors.ts`
Identify `friendlyLoginError(message: string)` and how it matches statuses/strings.

- [ ] **Step 2: Add the two cases**

Add handling so that:
- A **423** / "locked" response shows: `"Account temporarily locked after too many attempts. Try again in a few minutes."`
- A **403** / "blocked" response shows: `"Access from your network is temporarily blocked. Try again later."`

Match the existing style in that file (it already maps the 429 "Too many attempts" case — follow the same pattern, whether it switches on status code or on substrings of the error message). If the function only receives a message string, key off the substrings `"locked"` and `"blocked"` respectively; the backend bodies are `"Account temporarily locked"` and `"Access temporarily blocked"`.

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/auth-errors.ts
git commit -m "feat(login): friendly messages for lockout (423) and ban (403)"
```

---

### Task 10: Full verification

- [ ] **Step 1: Run the entire backend suite**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: all pass (existing + new).

- [ ] **Step 2: Lint**

Run: `cd backend && .venv/bin/python -m ruff check app/ tests/`
Expected: no errors.

- [ ] **Step 3: Frontend type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: success.

- [ ] **Step 4: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to merge/PR.

---

## Self-Review Notes

- **Spec coverage:** L1 Traefik rateLimit → Task 8. L2 per-username lockout → Tasks 2,5. L3 abuse detector + banned_ip + ban-check + forwardAuth → Tasks 2,3,5,6,8. L4 persistence (in-memory window + DB lockout/bans) → Tasks 2,3 (no window persistence by design). Config → Task 1. Frontend messages → Task 9. Rate-limit bypass for ban-check → Task 7.
- **Type consistency:** `IpFailTracker.record(ip, now)`, `BanCache.is_banned(session, ip, now, mono)` / `.refresh` / `.invalidate`, `ban_ip(session, ip, reason, duration, now)`, singletons `fail_tracker` / `ban_cache` — names identical across abuse.py, auth.py, conftest, and tests.
- **Lockout vs ban interaction (verified):** a real user locks at 10 fails (423) and stops incrementing the IP tracker; the 20/10min IP ban is driven by continued 401-path failures (e.g. username rotation), which is exactly the brute-force pattern the ban targets. Test 6 uses fresh usernames to exercise this deterministically.
- **No routing loop:** Traefik forwardAuth calls `http://backend:8000/api/auth/ban-check` directly (bypasses Traefik routers), so the `ip-ban-gate` middleware on the `api` router does not recurse.
