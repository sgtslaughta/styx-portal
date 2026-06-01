# Native Auth + Multi-User + Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backend-owned native JWT authentication, per-user ownership of instances/templates with admin/user roles, and industry-standard security hardening to the internet-exposed Selkies Hub.

**Architecture:** FastAPI owns identity. JWT access (15m) + refresh (7d) tokens ride in httpOnly+Secure+SameSite=Strict cookies, protected by double-submit CSRF. A `get_current_user` dependency guards every router; lists filter by `owner_id` (admins bypass), mutations call `require_owner_or_admin`. First admin is created via a one-time setup wizard; further users are admin-invite-only. React frontend adds `react-router` with login/setup/invite pages and an admin Users tab.

**Tech Stack:** Python 3.12, FastAPI, SQLModel/async SQLite, `pyjwt`, `argon2-cffi`; React 19, Vite, React Query, react-router, zxcvbn.

---

## File Structure

**Backend new:** `app/security/{passwords,tokens,csrf,deps,setup_gate}.py`, `app/middleware/{security_headers,rate_limit}.py`, `app/routers/{auth,users}.py`.
**Backend modified:** `app/models.py`, `app/database.py`, `app/config.py`, `app/main.py`, `app/schemas.py`, every existing router, `tests/conftest.py`.
**Frontend new:** `src/auth/{AuthContext,ProtectedRoute}.tsx`, `src/pages/{LoginPage,SetupWizard,AcceptInvitePage}.tsx`, `src/components/system/users-panel.tsx`, `src/hooks/use-auth.ts`.
**Frontend modified:** `src/api/client.ts`, `src/App.tsx`, `src/main.tsx`.

---

## Task 1: Add backend dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add packages to dependencies**

In `backend/pyproject.toml`, add to the `dependencies` list:
```toml
    "pyjwt>=2.9.0",
    "argon2-cffi>=23.1.0",
```

- [ ] **Step 2: Install**

Run: `cd backend && .venv/bin/python -m pip install -e .`
Expected: installs `pyjwt`, `argon2-cffi` without error.

- [ ] **Step 3: Verify import**

Run: `cd backend && .venv/bin/python -c "import jwt, argon2; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "build(auth): add pyjwt and argon2-cffi"
```

---

## Task 2: Config additions

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add auth settings**

Add these fields to `Settings` in `backend/app/config.py` (after `AUTHENTIK_MIDDLEWARE`):
```python
    JWT_SECRET: str = ""
    ACCESS_TTL: int = 900          # 15 minutes
    REFRESH_TTL: int = 604800      # 7 days
    COOKIE_SECURE: bool = True
    COOKIE_DOMAIN: str | None = None
    RATE_LIMIT_AUTH: str = "5/60"        # 5 requests per 60s on /auth/*
    RATE_LIMIT_DEFAULT: str = "120/60"   # 120 requests per 60s otherwise
```

- [ ] **Step 2: Add fail-fast validator**

Add at the bottom of `Settings`, inside the class:
```python
    def jwt_secret_or_raise(self) -> str:
        if not self.JWT_SECRET:
            if self.COOKIE_SECURE:
                raise RuntimeError("JWT_SECRET must be set when COOKIE_SECURE=true")
            return "dev-insecure-secret-do-not-use-in-prod"
        return self.JWT_SECRET
```

- [ ] **Step 3: Verify**

Run: `cd backend && .venv/bin/python -c "from app.config import Settings; s=Settings(JWT_SECRET='x'); print(s.jwt_secret_or_raise())"`
Expected: `x`

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(auth): add JWT/cookie/rate-limit settings"
```

---

## Task 3: Password hashing (Argon2id)

**Files:**
- Create: `backend/app/security/__init__.py`
- Create: `backend/app/security/passwords.py`
- Test: `backend/tests/test_passwords.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_passwords.py`:
```python
from app.security.passwords import hash_password, verify_password


def test_hash_is_not_plaintext():
    h = hash_password("hunter2")
    assert h != "hunter2"
    assert h.startswith("$argon2")


def test_verify_correct_password():
    h = hash_password("hunter2")
    assert verify_password("hunter2", h) is True


def test_verify_wrong_password():
    h = hash_password("hunter2")
    assert verify_password("wrong", h) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_passwords.py -v`
Expected: FAIL — `ModuleNotFoundError: app.security.passwords`

- [ ] **Step 3: Write implementation**

Create empty `backend/app/security/__init__.py`.
Create `backend/app/security/passwords.py`:
```python
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    try:
        return _ph.verify(hashed, password)
    except (VerifyMismatchError, VerificationError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_passwords.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/__init__.py backend/app/security/passwords.py backend/tests/test_passwords.py
git commit -m "feat(auth): Argon2id password hashing"
```

---

## Task 4: JWT tokens

**Files:**
- Create: `backend/app/security/tokens.py`
- Test: `backend/tests/test_tokens.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_tokens.py`:
```python
import time
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/security/tokens.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && JWT_SECRET=test .venv/bin/python -m pytest tests/test_tokens.py -v`
Expected: PASS (4 passed)

Note: tests need `JWT_SECRET` set. Add to Task 16 conftest a default.

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/tokens.py backend/tests/test_tokens.py
git commit -m "feat(auth): JWT access/refresh tokens with jti"
```

---

## Task 5: User / Invite / RefreshToken models + owner_id

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_user_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_user_model.py`:
```python
from app.models import User, Invite, RefreshToken, Instance


def test_user_defaults():
    u = User(username="admin", password_hash="x")
    assert u.role == "user"
    assert u.is_active is True
    assert u.must_change_pw is False
    assert u.id


def test_invite_unused_by_default():
    inv = Invite(token_hash="abc", role="user", created_by="admin-id")
    assert inv.used_at is None


def test_instance_has_owner_field():
    inst = Instance(template_id="t", name="n", subdomain="s", owner_id="u1")
    assert inst.owner_id == "u1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_user_model.py -v`
Expected: FAIL — `ImportError: cannot import name 'User'`

- [ ] **Step 3: Write implementation**

In `backend/app/models.py`, add after the existing imports/helpers and before `ServiceTemplate`:
```python
class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True)
    username: str = Field(unique=True, index=True)
    email: str | None = Field(default=None, index=True)
    password_hash: str
    role: str = "user"  # admin | user
    is_active: bool = True
    must_change_pw: bool = False
    created_at: datetime = Field(default_factory=_now)
    last_login: datetime | None = None


class Invite(SQLModel, table=True):
    __tablename__ = "invites"

    id: str = Field(default_factory=_uuid, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    email: str | None = None
    role: str = "user"
    created_by: str = Field(foreign_key="users.id")
    expires_at: datetime | None = None
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    jti: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    expires_at: datetime
    revoked: bool = False
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=_now)
```

In the same file, add `owner_id` to `Instance` (after `id`/`template_id` block, e.g. after line 55):
```python
    owner_id: str | None = Field(default=None, foreign_key="users.id", index=True)
```
And to `ServiceTemplate` (after `id`):
```python
    owner_id: str | None = Field(default=None, foreign_key="users.id", index=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_user_model.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_user_model.py
git commit -m "feat(auth): User/Invite/RefreshToken models + owner_id"
```

---

## Task 6: Migration — owner_id columns

**Files:**
- Modify: `backend/app/database.py`

- [ ] **Step 1: Extend migrations list**

In `backend/app/database.py` `_run_migrations`, add to the `migrations` list:
```python
        ("instances", "owner_id", "TEXT"),
        ("service_templates", "owner_id", "TEXT"),
```

- [ ] **Step 2: Verify tables create cleanly**

Run: `cd backend && JWT_SECRET=test .venv/bin/python -c "import asyncio; from app.database import init_db; asyncio.run(init_db()); print('ok')"`
Expected: `ok` (no migration errors)

- [ ] **Step 3: Commit**

```bash
git add backend/app/database.py
git commit -m "feat(auth): migrate owner_id columns onto instances/templates"
```

---

## Task 7: Setup gate helper

**Files:**
- Create: `backend/app/security/setup_gate.py`
- Test: `backend/tests/test_setup_gate.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_setup_gate.py`:
```python
import pytest
from app.security.setup_gate import users_exist
from app.models import User
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_users_exist_false_when_empty(session):
    assert await users_exist(session) is False


@pytest.mark.asyncio
async def test_users_exist_true_after_insert(session):
    session.add(User(username="a", password_hash=hash_password("x")))
    await session.commit()
    assert await users_exist(session) is True
```

(The `session` fixture is defined in `conftest.py`, see Task 16.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_setup_gate.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/security/setup_gate.py`:
```python
from sqlmodel import select, func
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import User


async def users_exist(session: AsyncSession) -> bool:
    result = await session.exec(select(func.count()).select_from(User))
    return (result.one() or 0) > 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_setup_gate.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/setup_gate.py backend/tests/test_setup_gate.py
git commit -m "feat(auth): setup-gate users_exist helper"
```

---

## Task 8: CSRF double-submit

**Files:**
- Create: `backend/app/security/csrf.py`
- Test: `backend/tests/test_csrf.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_csrf.py`:
```python
from app.security.csrf import new_csrf_token, csrf_valid


def test_matching_tokens_valid():
    t = new_csrf_token()
    assert csrf_valid(cookie=t, header=t) is True


def test_mismatch_invalid():
    assert csrf_valid(cookie=new_csrf_token(), header=new_csrf_token()) is False


def test_missing_invalid():
    assert csrf_valid(cookie=None, header="x") is False
    assert csrf_valid(cookie="x", header=None) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_csrf.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/security/csrf.py`:
```python
import secrets

CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_valid(cookie: str | None, header: str | None) -> bool:
    if not cookie or not header:
        return False
    return secrets.compare_digest(cookie, header)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_csrf.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/csrf.py backend/tests/test_csrf.py
git commit -m "feat(auth): double-submit CSRF helpers"
```

---

## Task 9: Auth schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add request/response schemas**

Append to `backend/app/schemas.py` (use `from pydantic import BaseModel, Field` — add if absent):
```python
class SetupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str | None = None
    password: str = Field(min_length=12, max_length=256)


class LoginRequest(BaseModel):
    username: str
    password: str


class AcceptInviteRequest(BaseModel):
    token: str
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    role: str
    is_active: bool


class CreateInviteRequest(BaseModel):
    email: str | None = None
    role: str = "user"


class InviteOut(BaseModel):
    token: str
    expires_at: str | None
```

- [ ] **Step 2: Verify import**

Run: `cd backend && .venv/bin/python -c "from app.schemas import LoginRequest, UserOut; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(auth): auth request/response schemas"
```

---

## Task 10: Auth dependencies

**Files:**
- Create: `backend/app/security/deps.py`
- Test: `backend/tests/test_auth_deps.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_auth_deps.py`:
```python
import pytest
from fastapi import HTTPException
from app.security.deps import require_owner_or_admin
from app.models import User


def _user(role="user", uid="u1"):
    return User(id=uid, username="x", password_hash="h", role=role)


def test_owner_allowed():
    require_owner_or_admin("u1", _user(uid="u1"))  # no raise


def test_admin_allowed():
    require_owner_or_admin("someone-else", _user(role="admin", uid="u2"))


def test_other_user_denied():
    with pytest.raises(HTTPException) as e:
        require_owner_or_admin("owner-x", _user(uid="u9"))
    assert e.value.status_code == 403
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_deps.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/security/deps.py`:
```python
from fastapi import Depends, HTTPException, Request, status
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User
from app.security import tokens


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    raw = request.cookies.get("access_token")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin required")
    return user


def require_owner_or_admin(owner_id: str | None, user: User) -> None:
    if user.role == "admin":
        return
    if owner_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not the owner")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_deps.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/security/deps.py backend/tests/test_auth_deps.py
git commit -m "feat(auth): get_current_user / require_admin / require_owner_or_admin"
```

---

## Task 11: Security headers middleware

**Files:**
- Create: `backend/app/middleware/__init__.py`
- Create: `backend/app/middleware/security_headers.py`
- Test: `backend/tests/test_security_headers.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_security_headers.py`:
```python
def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert "Strict-Transport-Security" in r.headers
```

(The `client` fixture is in `conftest.py`, Task 16.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_security_headers.py -v`
Expected: FAIL — header missing / module not found.

- [ ] **Step 3: Write implementation**

Create empty `backend/app/middleware/__init__.py`.
Create `backend/app/middleware/security_headers.py`:
```python
from starlette.middleware.base import BaseHTTPMiddleware

_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = _CSP
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return resp
```

- [ ] **Step 4: Run test to verify it passes**

Wire it temporarily in Task 15; for now verify the import.
Run: `cd backend && .venv/bin/python -c "from app.middleware.security_headers import SecurityHeadersMiddleware; print('ok')"`
Expected: `ok`. (Test passes after Task 15 wiring.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/__init__.py backend/app/middleware/security_headers.py backend/tests/test_security_headers.py
git commit -m "feat(security): security headers middleware"
```

---

## Task 12: Rate limit middleware

**Files:**
- Create: `backend/app/middleware/rate_limit.py`
- Test: `backend/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_rate_limit.py`:
```python
from app.middleware.rate_limit import SlidingWindow


def test_allows_under_limit():
    w = SlidingWindow(limit=3, window=60)
    assert all(w.allow("ip1", now=t) for t in (0, 1, 2))


def test_blocks_over_limit():
    w = SlidingWindow(limit=3, window=60)
    for t in (0, 1, 2):
        w.allow("ip1", now=t)
    assert w.allow("ip1", now=3) is False


def test_window_slides():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip1", now=10) is False
    assert w.allow("ip1", now=61) is True


def test_keys_isolated():
    w = SlidingWindow(limit=1, window=60)
    assert w.allow("ip1", now=0) is True
    assert w.allow("ip2", now=0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write implementation**

Create `backend/app/middleware/rate_limit.py`:
```python
import time
from collections import defaultdict, deque

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SlidingWindow:
    def __init__(self, limit: int, window: int):
        self.limit = limit
        self.window = window
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, key: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        q = self._hits[key]
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


def _parse(spec: str) -> tuple[int, int]:
    limit, window = spec.split("/")
    return int(limit), int(window)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth_spec: str, default_spec: str):
        super().__init__(app)
        self._auth = SlidingWindow(*_parse(auth_spec))
        self._default = SlidingWindow(*_parse(default_spec))

    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        window = self._auth if request.url.path.startswith("/api/auth") else self._default
        if not window.allow(f"{ip}:{request.url.path.startswith('/api/auth')}"):
            return JSONResponse(
                {"detail": "Too many requests"},
                status_code=429,
                headers={"Retry-After": str(window.window)},
            )
        return await call_next(request)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_rate_limit.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/rate_limit.py backend/tests/test_rate_limit.py
git commit -m "feat(security): sliding-window rate limit middleware"
```

---

## Task 13: Auth router

**Files:**
- Create: `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_router.py` (added in Task 16 once `client` fixture exists)

- [ ] **Step 1: Write implementation**

Create `backend/app/routers/auth.py`:
```python
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, Invite, RefreshToken, Instance, ServiceTemplate
from app.schemas import SetupRequest, LoginRequest, AcceptInviteRequest, UserOut
from app.security import tokens
from app.security.passwords import hash_password, verify_password
from app.security.csrf import new_csrf_token, CSRF_COOKIE
from app.security.deps import get_current_user
from app.security.setup_gate import users_exist

router = APIRouter()
_settings = Settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _set_auth_cookies(resp: Response, access: str, refresh: str, csrf: str) -> None:
    common = dict(
        httponly=True,
        secure=_settings.COOKIE_SECURE,
        samesite="strict",
        domain=_settings.COOKIE_DOMAIN,
    )
    resp.set_cookie("access_token", access, max_age=_settings.ACCESS_TTL, **common)
    resp.set_cookie("refresh_token", refresh, max_age=_settings.REFRESH_TTL, **common)
    # CSRF cookie is readable by JS (double-submit) -> httponly False
    resp.set_cookie(
        CSRF_COOKIE, csrf, max_age=_settings.REFRESH_TTL,
        httponly=False, secure=_settings.COOKIE_SECURE,
        samesite="strict", domain=_settings.COOKIE_DOMAIN,
    )


def _clear_auth_cookies(resp: Response) -> None:
    for name in ("access_token", "refresh_token", CSRF_COOKIE):
        resp.delete_cookie(name, domain=_settings.COOKIE_DOMAIN)


async def _issue_session(resp: Response, session: AsyncSession, user: User, request: Request) -> None:
    access = tokens.create_access_token(user.id, user.role)
    refresh, jti = tokens.create_refresh_token(user.id)
    session.add(RefreshToken(
        jti=jti, user_id=user.id,
        expires_at=_now() + timedelta(seconds=_settings.REFRESH_TTL),
        user_agent=request.headers.get("user-agent"),
    ))
    user.last_login = _now()
    session.add(user)
    await session.commit()
    _set_auth_cookies(resp, access, refresh, new_csrf_token())


@router.get("/setup-required")
async def setup_required(session: AsyncSession = Depends(get_session)):
    return {"setup_required": not await users_exist(session)}


@router.post("/setup", response_model=UserOut, status_code=201)
async def setup(body: SetupRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user = User(username=body.username, email=body.email,
                password_hash=hash_password(body.password), role="admin")
    session.add(user)
    await session.flush()
    # backfill existing ownerless instances/templates to this admin
    await session.exec(update(Instance).where(Instance.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await session.exec(update(ServiceTemplate).where(ServiceTemplate.owner_id == None).values(owner_id=user.id))  # noqa: E711
    await _issue_session(response, session, user, request)
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User).where(User.username == body.username))
    user = result.first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    await _issue_session(response, session, user, request)
    return {"id": user.id, "username": user.username, "role": user.role,
            "must_change_pw": user.must_change_pw}


@router.post("/refresh")
async def refresh(request: Request, response: Response,
                  session: AsyncSession = Depends(get_session)):
    raw = request.cookies.get("refresh_token")
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        claims = tokens.decode_token(raw)
    except tokens.TokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if claims.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong token type")
    stored = await session.get(RefreshToken, claims["jti"])
    if not stored or stored.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    # rotation: revoke old, issue new
    stored.revoked = True
    session.add(stored)
    await _issue_session(response, session, user, request)
    return {"ok": True}


@router.post("/logout")
async def logout(request: Request, response: Response,
                 session: AsyncSession = Depends(get_session)):
    raw = request.cookies.get("refresh_token")
    if raw:
        try:
            claims = tokens.decode_token(raw)
            stored = await session.get(RefreshToken, claims.get("jti"))
            if stored:
                stored.revoked = True
                session.add(stored)
                await session.commit()
        except tokens.TokenError:
            pass
    _clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.post("/accept-invite", status_code=201)
async def accept_invite(body: AcceptInviteRequest, request: Request, response: Response,
                        session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(Invite).where(Invite.token_hash == _hash_token(body.token)))
    inv = result.first()
    if not inv or inv.used_at is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or used invite")
    if inv.expires_at and inv.expires_at < _now():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invite expired")
    exists = await session.exec(select(User).where(User.username == body.username))
    if exists.first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username taken")
    user = User(username=body.username, email=inv.email,
                password_hash=hash_password(body.password), role=inv.role)
    inv.used_at = _now()
    session.add_all([user, inv])
    await _issue_session(response, session, user, request)
    return {"id": user.id, "username": user.username, "role": user.role}
```

- [ ] **Step 2: Verify import**

Run: `cd backend && .venv/bin/python -c "from app.routers.auth import router; print(len(router.routes))"`
Expected: prints `8`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/auth.py
git commit -m "feat(auth): auth router (setup/login/refresh/logout/me/accept-invite)"
```

---

## Task 14: Users admin router

**Files:**
- Create: `backend/app/routers/users.py`

- [ ] **Step 1: Write implementation**

Create `backend/app/routers/users.py`:
```python
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import User, Invite
from app.schemas import UserOut, CreateInviteRequest, InviteOut
from app.security.deps import require_admin

router = APIRouter()
INVITE_TTL_HOURS = 72


@router.get("", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(User))
    return [UserOut(id=u.id, username=u.username, email=u.email,
                    role=u.role, is_active=u.is_active) for u in result.all()]


@router.post("/invites", response_model=InviteOut, status_code=201)
async def create_invite(body: CreateInviteRequest, admin: User = Depends(require_admin),
                        session: AsyncSession = Depends(get_session)):
    if body.role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=INVITE_TTL_HOURS)
    session.add(Invite(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        email=body.email, role=body.role, created_by=admin.id, expires_at=expires,
    ))
    await session.commit()
    return InviteOut(token=raw, expires_at=expires.isoformat())


@router.patch("/{user_id}/disable", response_model=UserOut)
async def disable_user(user_id: str, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot disable yourself")
    user.is_active = False
    session.add(user)
    await session.commit()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)


@router.patch("/{user_id}/role", response_model=UserOut)
async def change_role(user_id: str, role: str, admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    if role not in ("admin", "user"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid role")
    user = await session.get(User, user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    user.role = role
    session.add(user)
    await session.commit()
    return UserOut(id=user.id, username=user.username, email=user.email,
                   role=user.role, is_active=user.is_active)
```

- [ ] **Step 2: Verify import**

Run: `cd backend && .venv/bin/python -c "from app.routers.users import router; print(len(router.routes))"`
Expected: prints `4`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/users.py
git commit -m "feat(auth): admin users router (list/invite/disable/role)"
```

---

## Task 15: Wire main.py — middleware, CORS, CSRF enforcement, routers

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Remove admin-token block**

In `backend/app/main.py` `lifespan`, delete lines 69-78 (the `# Generate or load admin token` block through the `logger.warning(... ADMIN TOKEN ...)`). Remove now-unused `import secrets` (line 3) and `from pathlib import Path` if unused elsewhere (it is only used there).

- [ ] **Step 2: Add CSRF enforcement middleware function**

Add near the top of `main.py` after imports:
```python
from starlette.middleware.base import BaseHTTPMiddleware
from app.security.csrf import csrf_valid, CSRF_COOKIE, CSRF_HEADER, UNSAFE_METHODS

_CSRF_EXEMPT = {"/api/auth/login", "/api/auth/setup", "/api/auth/refresh", "/api/auth/accept-invite"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if request.method in UNSAFE_METHODS and request.url.path not in _CSRF_EXEMPT:
            if not csrf_valid(request.cookies.get(CSRF_COOKIE),
                              request.headers.get(CSRF_HEADER)):
                from fastapi.responses import JSONResponse
                return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
        return await call_next(request)
```

- [ ] **Step 3: Replace CORS block and register middleware + routers**

Replace the existing CORS block (`app.add_middleware(CORSMiddleware, ...)`, lines 200-206) with:
```python
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.rate_limit import RateLimitMiddleware

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    auth_spec=_settings.RATE_LIMIT_AUTH,
    default_spec=_settings.RATE_LIMIT_DEFAULT,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", f"https://{_settings.DOMAIN}"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
```

Then register routers near the existing `include_router` calls:
```python
from app.routers import auth as auth_router
from app.routers import users as users_router

app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])
```

- [ ] **Step 4: Run security-headers test (now wired)**

Run: `cd backend && JWT_SECRET=test .venv/bin/python -m pytest tests/test_security_headers.py -v`
Expected: PASS (after Task 16 fixtures exist; if running before, run it again at end of Task 16).

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(security): wire headers/CSRF/rate-limit middleware, tighten CORS, register auth routers, drop admin token"
```

---

## Task 16: Test fixtures (authed client) + protected-route tests

**Files:**
- Modify: `backend/tests/conftest.py`
- Create: `backend/tests/test_auth_router.py`

- [ ] **Step 1: Inspect existing conftest**

Run: `cd backend && cat tests/conftest.py`
Note the existing `session` and `client` fixtures and DB override pattern (reuse them).

- [ ] **Step 2: Ensure JWT_SECRET set for tests**

At the top of `backend/tests/conftest.py`, before app imports, add:
```python
import os
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")
```

- [ ] **Step 3: Add an authed-client fixture**

Append to `backend/tests/conftest.py` (adapt names to the existing `client` fixture's type — assumed `fastapi.testclient.TestClient`):
```python
import pytest


@pytest.fixture
def admin_client(client):
    """A TestClient that has completed setup and holds admin cookies."""
    r = client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery"})
    assert r.status_code == 201, r.text
    # propagate CSRF header from cookie for subsequent unsafe requests
    csrf = client.cookies.get("csrf_token")
    client.headers.update({"X-CSRF-Token": csrf})
    return client
```

- [ ] **Step 4: Write auth-router tests**

Create `backend/tests/test_auth_router.py`:
```python
def test_setup_required_initially_true(client):
    r = client.get("/api/auth/setup-required")
    assert r.json()["setup_required"] is True


def test_setup_creates_admin_and_locks(client):
    r = client.post("/api/auth/setup", json={
        "username": "admin", "password": "correct horse battery"})
    assert r.status_code == 201
    assert r.json()["role"] == "admin"
    # second setup attempt -> 404
    r2 = client.post("/api/auth/setup", json={
        "username": "x", "password": "another long password"})
    assert r2.status_code == 404


def test_me_after_setup(admin_client):
    r = admin_client.get("/api/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


def test_login_bad_credentials(admin_client):
    r = admin_client.post("/api/auth/login",
                          json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_unauthenticated_instances_401(client):
    r = client.get("/api/instances")
    assert r.status_code == 401


def test_logout_revokes_refresh(admin_client):
    assert admin_client.post("/api/auth/logout").status_code == 200
    # refresh cookie cleared -> refresh fails
    r = admin_client.post("/api/auth/refresh")
    assert r.status_code == 401
```

- [ ] **Step 5: Run tests**

Run: `cd backend && .venv/bin/python -m pytest tests/test_auth_router.py tests/test_security_headers.py tests/test_setup_gate.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_auth_router.py
git commit -m "test(auth): authed-client fixture + auth router/protected-route tests"
```

---

## Task 17: Protect existing routers + ownership filtering

**Files:**
- Modify: `backend/app/routers/instances.py`
- Modify: `backend/app/routers/templates.py`
- Modify: `backend/app/routers/registry.py`
- Modify: `backend/app/routers/images.py`
- Modify: `backend/app/main.py` (inline `/api/system/*` routes)
- Test: `backend/tests/test_ownership.py`

- [ ] **Step 1: Write the failing ownership test**

Create `backend/tests/test_ownership.py`:
```python
def _second_user(admin_client, client):
    inv = admin_client.post("/api/users/invites", json={"role": "user"}).json()
    # accept invite in a fresh client so cookies don't collide
    import fastapi.testclient  # noqa
    return inv["token"]


def test_user_sees_only_own_instances(admin_client, make_client):
    # admin creates an instance (owner=admin)
    # (use whatever create payload the existing tests use; minimal here)
    admin_inst = admin_client.get("/api/instances").json()
    # invite + accept as a second user
    token = admin_client.post("/api/users/invites", json={"role": "user"}).json()["token"]
    user = make_client()
    user.post("/api/auth/accept-invite",
              json={"token": token, "username": "bob", "password": "bobs long password"})
    user.headers.update({"X-CSRF-Token": user.cookies.get("csrf_token")})
    user_view = user.get("/api/instances")
    assert user_view.status_code == 200
    # bob owns nothing -> empty list, regardless of admin's instances
    assert user_view.json() == []
```

Add a `make_client` factory fixture to `conftest.py` that returns fresh `TestClient` instances bound to the same app/DB override (mirror the existing `client` fixture construction).

- [ ] **Step 2: Run to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ownership.py -v`
Expected: FAIL (routes not yet protected / not filtered).

- [ ] **Step 3: Add auth dep + ownership to instances router**

In `backend/app/routers/instances.py`:
- Add imports:
```python
from app.security.deps import get_current_user, require_owner_or_admin
from app.models import User
```
- In the list endpoint, add `user: User = Depends(get_current_user)` param and filter:
```python
    stmt = select(Instance)
    if user.role != "admin":
        stmt = stmt.where(Instance.owner_id == user.id)
    result = await session.exec(stmt)
```
- On create, set `owner_id=user.id` on the new `Instance`.
- On every by-id endpoint (start/stop/restart/recreate/pause/unpause/update/delete/status/keepalive/stats/logs/events/screenshot), add `user: User = Depends(get_current_user)`, load the instance, then call `require_owner_or_admin(instance.owner_id, user)` before acting.

- [ ] **Step 4: Add auth dep + ownership to templates router**

In `backend/app/routers/templates.py`: same pattern. List returns templates where `owner_id == user.id` OR `owner_id IS None` (shared) — admins see all:
```python
    stmt = select(ServiceTemplate)
    if user.role != "admin":
        stmt = stmt.where(
            (ServiceTemplate.owner_id == user.id) | (ServiceTemplate.owner_id == None)  # noqa: E711
        )
```
Create sets `owner_id=user.id`. Update/delete call `require_owner_or_admin(tmpl.owner_id, user)` (a `None`-owned shared template is admin-only to mutate: treat `None` owner as admin-only — `require_owner_or_admin(None, user)` denies non-admins, which is correct).

- [ ] **Step 5: Protect registry/images/system routes**

- `registry.py`, `images.py`: add `Depends(require_admin)` (registry pulls and image purge are admin-only).
- In `main.py`, add `user=Depends(require_admin)` to `/api/system/metrics`, `/api/system/metrics/history`, `/api/system/gpu`. Leave `/api/health` public. Add `from app.security.deps import require_admin`.

- [ ] **Step 6: Run ownership + full suite**

Run: `cd backend && .venv/bin/python -m pytest tests/test_ownership.py -v`
Expected: PASS.
Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: all green (update any pre-existing instance/template tests to use `admin_client`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ backend/app/main.py backend/tests/test_ownership.py backend/tests/conftest.py
git commit -m "feat(authz): protect all routers + per-user ownership filtering"
```

---

## Task 18: Update pre-existing tests to authenticate

**Files:**
- Modify: existing `backend/tests/test_*.py` that call protected routes

- [ ] **Step 1: Identify breakages**

Run: `cd backend && .venv/bin/python -m pytest -v 2>&1 | grep -E "FAILED|401|403"`
Expected: lists tests now hitting 401/403.

- [ ] **Step 2: Swap `client` → `admin_client`**

In each failing test that exercises instances/templates/registry/images/system, change the fixture parameter from `client` to `admin_client`. No logic changes.

- [ ] **Step 3: Run full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: all PASS (≥44 original + new).
Run: `cd backend && .venv/bin/python -m ruff check app/ tests/`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: authenticate existing tests via admin_client fixture"
```

---

## Task 19: Frontend API client — credentials, CSRF, 401 handling

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add CSRF + credentials to request()**

Replace the `request` function in `frontend/src/api/client.ts` with:
```typescript
const BASE = "/api";

function getCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string>),
  };
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrf = getCookie("csrf_token");
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers,
    ...init,
  });
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}
```

- [ ] **Step 2: Add auth API methods**

Add to the exported `api` object:
```typescript
  setupRequired: () => request<{ setup_required: boolean }>("/auth/setup-required"),
  setup: (data: { username: string; email?: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/setup", {
      method: "POST", body: JSON.stringify(data) }),
  login: (data: { username: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/login", {
      method: "POST", body: JSON.stringify(data) }),
  logout: () => request<{ ok: boolean }>("/auth/logout", { method: "POST" }),
  me: () => request<{ id: string; username: string; email: string | null; role: string }>("/auth/me"),
  acceptInvite: (data: { token: string; username: string; password: string }) =>
    request<{ id: string; username: string; role: string }>("/auth/accept-invite", {
      method: "POST", body: JSON.stringify(data) }),
  listUsers: () => request<{ id: string; username: string; email: string | null; role: string; is_active: boolean }[]>("/users"),
  createInvite: (data: { email?: string; role: string }) =>
    request<{ token: string; expires_at: string | null }>("/users/invites", {
      method: "POST", body: JSON.stringify(data) }),
  disableUser: (id: string) => request<unknown>(`/users/${id}/disable`, { method: "PATCH" }),
  changeRole: (id: string, role: string) =>
    request<unknown>(`/users/${id}/role?role=${role}`, { method: "PATCH" }),
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(auth): frontend client credentials + CSRF + 401 redirect + auth API"
```

---

## Task 20: Auth context + hook

**Files:**
- Create: `frontend/src/auth/AuthContext.tsx`
- Create: `frontend/src/hooks/use-auth.ts`

- [ ] **Step 1: Create AuthContext**

Create `frontend/src/auth/AuthContext.tsx`:
```tsx
import { createContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/api/client";

export type AuthUser = { id: string; username: string; email: string | null; role: string };

type AuthState = {
  user: AuthUser | null;
  loading: boolean;
  setupRequired: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

export const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setupRequired, setSetupRequired] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const s = await api.setupRequired();
      setSetupRequired(s.setup_required);
      if (!s.setup_required) {
        setUser(await api.me().catch(() => null));
      } else {
        setUser(null);
      }
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    await api.logout().catch(() => {});
    setUser(null);
    window.location.href = "/login";
  }

  useEffect(() => { refresh(); }, []);

  return (
    <AuthContext.Provider value={{ user, loading, setupRequired, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
```

- [ ] **Step 2: Create use-auth hook**

Create `frontend/src/hooks/use-auth.ts`:
```typescript
import { useContext } from "react";
import { AuthContext } from "@/auth/AuthContext";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/auth/AuthContext.tsx frontend/src/hooks/use-auth.ts
git commit -m "feat(auth): AuthProvider context + useAuth hook"
```

---

## Task 21: Router + ProtectedRoute + page shell

**Files:**
- Create: `frontend/src/auth/ProtectedRoute.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/App.tsx`

> Build the page visuals with the `frontend-design` skill; the code below is functional baseline to refine.

- [ ] **Step 1: ProtectedRoute**

Create `frontend/src/auth/ProtectedRoute.tsx`:
```tsx
import { type ReactNode } from "react";
import { Navigate } from "react-router";
import { useAuth } from "@/hooks/use-auth";

export function ProtectedRoute({ children, adminOnly = false }: { children: ReactNode; adminOnly?: boolean }) {
  const { user, loading, setupRequired } = useAuth();
  if (loading) return <div className="grid h-screen place-items-center">Loading…</div>;
  if (setupRequired) return <Navigate to="/setup" replace />;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/" replace />;
  return <>{children}</>;
}
```

- [ ] **Step 2: Wire router in main.tsx**

Modify `frontend/src/main.tsx` to wrap the app in `BrowserRouter` + `AuthProvider` and define routes. Example shape:
```tsx
import { BrowserRouter, Routes, Route } from "react-router";
import { AuthProvider } from "@/auth/AuthContext";
import { ProtectedRoute } from "@/auth/ProtectedRoute";
import App from "./App";
import { LoginPage } from "@/pages/LoginPage";
import { SetupWizard } from "@/pages/SetupWizard";
import { AcceptInvitePage } from "@/pages/AcceptInvitePage";

// inside render, replace <App/> with:
<BrowserRouter>
  <AuthProvider>
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/setup" element={<SetupWizard />} />
      <Route path="/accept-invite/:token" element={<AcceptInvitePage />} />
      <Route path="/*" element={<ProtectedRoute><App /></ProtectedRoute>} />
    </Routes>
  </AuthProvider>
</BrowserRouter>
```
(Keep the existing `QueryClientProvider` and theme provider wrappers outermost.)

- [ ] **Step 3: Add logout button + user badge to App header**

In `frontend/src/App.tsx` (or the header component it renders), import `useAuth` and render `user.username` + a logout button calling `logout()`. Show the admin Users tab only when `user.role === "admin"`.

- [ ] **Step 4: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/auth/ProtectedRoute.tsx frontend/src/main.tsx frontend/src/App.tsx
git commit -m "feat(auth): react-router shell + ProtectedRoute + header logout"
```

---

## Task 22: Login / Setup / Accept-Invite pages

**Files:**
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/SetupWizard.tsx`
- Create: `frontend/src/pages/AcceptInvitePage.tsx`

> Use the `frontend-design` skill for visual quality; match existing semantic-token theme. Functional baselines below.

- [ ] **Step 1: Add zxcvbn**

Run: `cd frontend && npm install zxcvbn @types/zxcvbn`

- [ ] **Step 2: LoginPage**

Create `frontend/src/pages/LoginPage.tsx`:
```tsx
import { useState } from "react";
import { useNavigate } from "react-router";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

export function LoginPage() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api.login({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="grid h-screen place-items-center">
      <form onSubmit={submit} className="w-80 space-y-3">
        <h1 className="text-xl font-semibold">Sign in</h1>
        <input className="w-full rounded border p-2" placeholder="Username"
               value={username} onChange={(e) => setU(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
               value={password} onChange={(e) => setP(e.target.value)} />
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button className="w-full rounded bg-blue-600 p-2 text-white">Sign in</button>
      </form>
    </div>
  );
}
```

- [ ] **Step 3: SetupWizard (with zxcvbn strength gate)**

Create `frontend/src/pages/SetupWizard.tsx`:
```tsx
import { useState } from "react";
import { useNavigate } from "react-router";
import zxcvbn from "zxcvbn";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

export function SetupWizard() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();
  const score = password ? zxcvbn(password).score : 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (score < 3) { setErr("Password too weak"); return; }
    try {
      await api.setup({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="grid h-screen place-items-center">
      <form onSubmit={submit} className="w-80 space-y-3">
        <h1 className="text-xl font-semibold">Create admin account</h1>
        <input className="w-full rounded border p-2" placeholder="Username"
               value={username} onChange={(e) => setU(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
               value={password} onChange={(e) => setP(e.target.value)} />
        <div className="h-1 rounded bg-gray-200">
          <div className="h-1 rounded bg-green-500" style={{ width: `${(score + 1) * 20}%` }} />
        </div>
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button className="w-full rounded bg-blue-600 p-2 text-white" disabled={score < 3}>
          Create admin
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4: AcceptInvitePage**

Create `frontend/src/pages/AcceptInvitePage.tsx`:
```tsx
import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import zxcvbn from "zxcvbn";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";

export function AcceptInvitePage() {
  const { token = "" } = useParams();
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const nav = useNavigate();
  const { refresh } = useAuth();
  const score = password ? zxcvbn(password).score : 0;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (score < 3) { setErr("Password too weak"); return; }
    try {
      await api.acceptInvite({ token, username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="grid h-screen place-items-center">
      <form onSubmit={submit} className="w-80 space-y-3">
        <h1 className="text-xl font-semibold">Accept invitation</h1>
        <input className="w-full rounded border p-2" placeholder="Username"
               value={username} onChange={(e) => setU(e.target.value)} />
        <input className="w-full rounded border p-2" type="password" placeholder="Password"
               value={password} onChange={(e) => setP(e.target.value)} />
        {err && <p className="text-sm text-red-500">{err}</p>}
        <button className="w-full rounded bg-blue-600 p-2 text-white" disabled={score < 3}>
          Join
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 5: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/ frontend/package.json frontend/package-lock.json
git commit -m "feat(auth): login/setup/accept-invite pages with zxcvbn gate"
```

---

## Task 23: Admin Users panel

**Files:**
- Create: `frontend/src/components/system/users-panel.tsx`
- Modify: `frontend/src/App.tsx` (add admin-only Users sub-tab under System)

- [ ] **Step 1: Users panel**

Create `frontend/src/components/system/users-panel.tsx`:
```tsx
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/api/client";

export function UsersPanel() {
  const qc = useQueryClient();
  const { data: users = [] } = useQuery({ queryKey: ["users"], queryFn: api.listUsers });
  const [inviteUrl, setInviteUrl] = useState<string | null>(null);

  const invite = useMutation({
    mutationFn: () => api.createInvite({ role: "user" }),
    onSuccess: (r) => setInviteUrl(`${location.origin}/accept-invite/${r.token}`),
  });
  const disable = useMutation({
    mutationFn: (id: string) => api.disableUser(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Users</h2>
        <button className="rounded bg-blue-600 px-3 py-1.5 text-white"
                onClick={() => invite.mutate()}>Generate invite</button>
      </div>
      {inviteUrl && (
        <div className="rounded border p-2 text-sm">
          Invite link (single-use, 72h): <code className="break-all">{inviteUrl}</code>
        </div>
      )}
      <table className="w-full text-sm">
        <thead><tr className="text-left"><th>User</th><th>Role</th><th>Active</th><th></th></tr></thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t">
              <td className="py-1">{u.username}</td>
              <td>{u.role}</td>
              <td>{u.is_active ? "yes" : "no"}</td>
              <td className="text-right">
                {u.is_active && (
                  <button className="text-red-500" onClick={() => disable.mutate(u.id)}>Disable</button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Mount under System tab (admin only)**

In `frontend/src/App.tsx`, where System content renders, conditionally include `<UsersPanel />` when `useAuth().user?.role === "admin"` (as a sub-tab or section). Import `UsersPanel`.

- [ ] **Step 3: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/system/users-panel.tsx frontend/src/App.tsx
git commit -m "feat(auth): admin Users panel (list/invite/disable)"
```

---

## Task 24: End-to-end verification + docs

**Files:**
- Modify: `.env.example`, `README.md`, `CLAUDE.md` (security note)

- [ ] **Step 1: Document new env vars**

Add to `.env.example`:
```env
# Auth (Phase 1 native auth)
JWT_SECRET=change-me-to-a-long-random-string
COOKIE_SECURE=true
```

- [ ] **Step 2: Run full backend suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -v && .venv/bin/python -m ruff check app/ tests/`
Expected: all green, no lint errors.

- [ ] **Step 3: Build frontend**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: succeeds.

- [ ] **Step 4: Manual e2e (compose)**

```bash
docker compose up -d --build
```
Then verify in a browser / curl:
- First visit → redirected to `/setup`; create admin (strong password).
- After setup, `/setup` → 404; existing instances now owned by admin.
- Log out → `/login`; log in succeeds.
- `curl -I https://<domain>/api/health` → shows `Content-Security-Policy`, `Strict-Transport-Security`, `X-Frame-Options: DENY`.
- Generate invite in admin Users panel → open link in private window → create second user → that user sees zero instances; admin sees all.
- Log out → `POST /api/auth/refresh` returns 401 (refresh revoked).
- Hit `/api/auth/login` 6× rapidly → 429 with `Retry-After`.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md CLAUDE.md
git commit -m "docs(auth): document JWT_SECRET/COOKIE_SECURE + Phase 1 auth"
```

---

## Self-Review notes (addressed)
- **Spec coverage:** native JWT (T3-4,13), httpOnly cookies+CSRF (T8,13,15,19), per-user ownership (T5-6,17), setup wizard (T13,22), invite-only (T13-14,22-23), security headers (T11,15), rate limit (T12,15), CORS tighten + admin-token removal (T15), SQLi audit (T6 note: migration uses static literals only), XSS (CSP T11), session-hijack defenses (refresh rotation/revoke T13). All covered.
- **Deferred (not in any task, intentional):** SSO/OAuth, admin tuneable settings, metrics dashboard, email verify, captcha.
- **Type consistency:** cookie names (`access_token`/`refresh_token`/`csrf_token`), header `X-CSRF-Token`, `UserOut` shape, and `require_owner_or_admin(owner_id, user)` signature are consistent across backend tasks and the frontend client.
