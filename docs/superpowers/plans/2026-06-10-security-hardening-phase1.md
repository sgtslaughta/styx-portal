# Security Hardening Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Secure-by-default deployment per spec `docs/superpowers/specs/2026-06-10-security-hardening-phase1-design.md`: auto-generated secrets, hardened containers, socket proxy, dual TLS mode, auth/authz fixes, audit logging.

**Architecture:** Backend changes are TDD'd against the existing pytest suite (in-memory SQLite, mocked Docker). Infra changes (compose/traefik/nginx/Dockerfile) are config-only and verified via a manual smoke checklist at the end. Tasks 1–14 backend, 15–20 infra/frontend.

**Tech Stack:** FastAPI, SQLModel, pytest, docker-py, Traefik v3.4, docker-socket-proxy, nginx.

**Conventions:**
- All commands run from `backend/` unless stated: `cd /home/user/code/remote-access/backend`
- Test: `.venv/bin/python -m pytest <path> -v` — full suite + `.venv/bin/python -m ruff check app/ tests/` before each commit.
- Commit messages: Conventional Commits, end body with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: JWT_SECRET auto-generation + validation

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py` (create)

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_config.py
import json
import stat

import pytest

from app.config import Settings, PLACEHOLDER_SECRETS


def _settings(tmp_path, **kw):
    kw.setdefault("SECRETS_FILE", str(tmp_path / "secrets.json"))
    return Settings(_env_file=None, **kw)


def test_autogenerates_secret_when_unset(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="")
    secret = s.jwt_secret_or_raise()
    assert len(secret) >= 32
    data = json.loads((tmp_path / "secrets.json").read_text())
    assert data["jwt_secret"] == secret


def test_generated_secret_persists_across_instances(tmp_path):
    path = str(tmp_path / "secrets.json")
    a = Settings(_env_file=None, JWT_SECRET="", SECRETS_FILE=path)
    b = Settings(_env_file=None, JWT_SECRET="", SECRETS_FILE=path)
    assert a.jwt_secret_or_raise() == b.jwt_secret_or_raise()


def test_secrets_file_mode_0600(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="")
    s.jwt_secret_or_raise()
    mode = stat.S_IMODE((tmp_path / "secrets.json").stat().st_mode)
    assert mode == 0o600


def test_env_secret_wins_over_file(tmp_path):
    (tmp_path / "secrets.json").write_text(json.dumps({"jwt_secret": "f" * 40}))
    s = _settings(tmp_path, JWT_SECRET="e" * 40)
    assert s.jwt_secret_or_raise() == "e" * 40


def test_rejects_short_secret(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="short")
    with pytest.raises(RuntimeError, match="32"):
        s.jwt_secret_or_raise()


@pytest.mark.parametrize("placeholder", sorted(PLACEHOLDER_SECRETS))
def test_rejects_placeholder_secret(tmp_path, placeholder):
    s = _settings(tmp_path, JWT_SECRET=placeholder)
    with pytest.raises(RuntimeError, match="placeholder"):
        s.jwt_secret_or_raise()


def test_no_dev_fallback_secret(tmp_path):
    s = _settings(tmp_path, JWT_SECRET="", COOKIE_SECURE=False)
    assert s.jwt_secret_or_raise() != "dev-insecure-secret-do-not-use-in-prod"
```

- [ ] **Step 2: Run, verify fails** — `pytest tests/test_config.py -v` → ImportError `PLACEHOLDER_SECRETS` / `SECRETS_FILE`.

- [ ] **Step 3: Implement** — replace `jwt_secret_or_raise` in `backend/app/config.py`:

```python
import json
import logging
import secrets as _secrets
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger("styx-portal")

PLACEHOLDER_SECRETS = {
    "change-me-to-a-long-random-string-min-32-bytes",
    "dev-insecure-secret-do-not-use-in-prod",
}


class Settings(BaseSettings):
    # ... existing fields unchanged ...
    SECRETS_FILE: str = "/app/data/secrets.json"

    def jwt_secret_or_raise(self) -> str:
        if self.JWT_SECRET:
            if self.JWT_SECRET in PLACEHOLDER_SECRETS:
                raise RuntimeError(
                    "JWT_SECRET is a placeholder value. Generate a real one: "
                    "openssl rand -base64 48"
                )
            if len(self.JWT_SECRET) < 32:
                raise RuntimeError(
                    f"JWT_SECRET must be at least 32 characters (got {len(self.JWT_SECRET)}). "
                    "Generate one: openssl rand -base64 48"
                )
            return self.JWT_SECRET
        return self._load_or_create_secret()

    def _load_or_create_secret(self) -> str:
        path = Path(self.SECRETS_FILE)
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("jwt_secret"):
                return data["jwt_secret"]
        else:
            data = {}
        secret = _secrets.token_urlsafe(48)
        data["jwt_secret"] = secret
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)
        logger.warning(
            "JWT_SECRET not set — generated one and saved to %s. "
            "Back this file up; losing it logs everyone out and invalidates "
            "stored OAuth client secrets.", path,
        )
        return secret
```

Keep `oauth_redirect_base()` and `model_config` as-is. Update the boot-time failure message in `backend/app/main.py:87-94` — drop the `COOKIE_SECURE=false` advice (no longer relevant):

```python
    try:
        _settings.jwt_secret_or_raise()
    except RuntimeError as e:
        logger.critical("FATAL: %s", e)
        raise
```

- [ ] **Step 4: Run** — `pytest tests/test_config.py -v` → PASS. Full suite: some tests may rely on `JWT_SECRET` env or `COOKIE_SECURE=false` fallback — check `tests/conftest.py`; if tests now write `/app/data/secrets.json`, set `SECRETS_FILE` to a tmp path in conftest fixture env.

- [ ] **Step 5: Commit** — `git add -A backend && git commit -m "feat(security): auto-generate JWT_SECRET, reject weak/placeholder secrets"`

---

### Task 2: Migration error surfacing

**Files:**
- Modify: `backend/app/database.py:27-56`
- Test: `backend/tests/test_database_migrations.py` (create)

- [ ] **Step 1: Failing test**

```python
# backend/tests/test_database_migrations.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import _run_migrations


@pytest.mark.asyncio
async def test_duplicate_column_is_ignored():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        import sqlalchemy
        await conn.execute(sqlalchemy.text("CREATE TABLE instances (id TEXT, error_message TEXT)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE service_templates (id TEXT)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE oauth_providers (id TEXT)"))
        await conn.execute(sqlalchemy.text("CREATE TABLE refresh_tokens (jti TEXT)"))
        await _run_migrations(conn)  # must not raise on pre-existing error_message


@pytest.mark.asyncio
async def test_missing_table_does_not_raise_but_logs(caplog):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        with caplog.at_level("WARNING"):
            await _run_migrations(conn)  # no tables yet — fresh install
    # fresh-install "no such table" is expected and silent or warned, never fatal
```

- [ ] **Step 2: Run, verify fails** (current code passes test 1 — test 2 may pass too; the real change is below. If both pass, keep tests as regression and proceed.)

- [ ] **Step 3: Implement** — replace the bare `except Exception: pass` blocks:

```python
import logging
logger = logging.getLogger("styx-portal")

async def _run_migrations(conn):
    """Add missing columns to existing tables."""
    import sqlalchemy
    from sqlalchemy.exc import OperationalError

    migrations = [
        ("instances", "error_message", "TEXT"),
        ("instances", "owner_id", "TEXT"),
        ("service_templates", "owner_id", "TEXT"),
        ("service_templates", "dind", "BOOLEAN"),
        ("service_templates", "cap_add", "TEXT"),
        ("service_templates", "security_opt", "TEXT"),
        ("service_templates", "tls_skip_verify", "BOOLEAN"),
        ("oauth_providers", "icon_url", "TEXT"),
        ("oauth_providers", "trust_email", "BOOLEAN"),
        ("oauth_providers", "allow_signup", "BOOLEAN"),
        ("oauth_providers", "auto_promote_admins", "BOOLEAN"),
        ("refresh_tokens", "family_id", "TEXT"),
    ]
    for table, column, col_type in migrations:
        try:
            await conn.execute(sqlalchemy.text(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            ))
        except OperationalError as e:
            msg = str(e).lower()
            # expected on fresh installs / re-runs; anything else is a real failure
            if "duplicate column" not in msg and "no such table" not in msg:
                logger.error("Migration failed for %s.%s: %s", table, column, e)
                raise

    backfills = [
        ("oauth_providers", "trust_email", "0"),
        ("oauth_providers", "allow_signup", "0"),
        ("oauth_providers", "auto_promote_admins", "1"),
        ("service_templates", "tls_skip_verify", "0"),
        ("refresh_tokens", "family_id", "jti"),  # legacy rows: own family
    ]
    for table, column, default in backfills:
        try:
            await conn.execute(sqlalchemy.text(
                f"UPDATE {table} SET {column} = {default} WHERE {column} IS NULL"
            ))
        except OperationalError as e:
            if "no such table" not in str(e).lower():
                logger.error("Backfill failed for %s.%s: %s", table, column, e)
                raise
```

(Note: this pre-adds columns for Tasks 4, 7, 11, 13 — single migration list, one place.)

- [ ] **Step 4: Run** — `pytest tests/test_database_migrations.py -v` then full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(db): surface migration failures, add phase-1 columns"`

---

### Task 3: AuditLog model + helper + admin API

**Files:**
- Modify: `backend/app/models.py` (append model)
- Create: `backend/app/services/audit.py`
- Modify: `backend/app/main.py` (router not needed — add endpoint to new router), Create: `backend/app/routers/audit.py`
- Test: `backend/tests/test_audit.py` (create)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_audit.py
import pytest
from sqlmodel import select

from app.models import AuditLog
from app.services.audit import audit


@pytest.mark.asyncio
async def test_audit_writes_row(session):  # `session` fixture from conftest
    await audit(session, "auth.login", user_id="u1", actor_ip="1.2.3.4",
                resource="u1", detail={"ok": True})
    await session.commit()
    rows = (await session.exec(select(AuditLog))).all()
    assert rows[0].action == "auth.login"
    assert rows[0].detail == {"ok": True}


@pytest.mark.asyncio
async def test_audit_redacts_secret_keys(session):
    await audit(session, "provider.update", detail={"client_secret": "x", "name": "g"})
    await session.commit()
    row = (await session.exec(select(AuditLog))).first()
    assert row.detail["client_secret"] == "[redacted]"
    assert row.detail["name"] == "g"


def test_audit_list_requires_admin(client):  # non-admin client fixture
    r = client.get("/api/audit")
    assert r.status_code in (401, 403)
```

(Adapt fixture names to `tests/conftest.py` — it already provides a DB session override and authed clients for other router tests; reuse the same fixtures used in `tests/test_users_router.py`.)

- [ ] **Step 2: Run, verify fails** — ImportError.

- [ ] **Step 3: Implement.**

`backend/app/models.py` — append:

```python
class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_log"

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_now, index=True)
    user_id: str | None = Field(default=None, index=True)
    actor_ip: str | None = None
    action: str = Field(index=True)
    resource: str | None = None
    detail: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
```

`backend/app/services/audit.py`:

```python
"""Append-only audit trail. Call sites must commit (or be committed by caller)."""
from fastapi import Request

from app.middleware.rate_limit import client_ip_from_headers
from app.models import AuditLog

_REDACT_KEYS = {"client_secret", "password", "token", "secret", "authorization"}


def _redact(detail: dict | None) -> dict | None:
    if not detail:
        return detail
    return {k: ("[redacted]" if k.lower() in _REDACT_KEYS else v)
            for k, v in detail.items()}


async def audit(session, action: str, *, user_id: str | None = None,
                actor_ip: str | None = None, resource: str | None = None,
                detail: dict | None = None) -> None:
    session.add(AuditLog(action=action, user_id=user_id, actor_ip=actor_ip,
                         resource=resource, detail=_redact(detail)))


async def audit_request(session, request: Request, action: str, *,
                        user_id: str | None = None, resource: str | None = None,
                        detail: dict | None = None) -> None:
    await audit(session, action, user_id=user_id, resource=resource,
                detail=detail, actor_ip=client_ip_from_headers(request))
```

`backend/app/routers/audit.py`:

```python
from fastapi import APIRouter, Depends, Query
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import AuditLog, User
from app.security.deps import require_admin

router = APIRouter()


@router.get("")
async def list_audit(
    limit: int = Query(100, le=500),
    offset: int = 0,
    action: str | None = None,
    user_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return (await session.exec(stmt)).all()
```

`backend/app/main.py` — register after the other routers:

```python
from app.routers import audit as audit_router
app.include_router(audit_router.router, prefix="/api/audit", tags=["audit"])
```

- [ ] **Step 4: Run** — `pytest tests/test_audit.py -v` + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): audit log table, helper, admin read API"`

---

### Task 4: Refresh-token families + reuse detection (RFC 9700)

**Files:**
- Modify: `backend/app/models.py:44-52` (RefreshToken), `backend/app/routers/auth.py`
- Test: `backend/tests/test_auth_refresh_reuse.py` (create)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_auth_refresh_reuse.py
# Reuse the login/client fixtures from tests/test_auth_router.py (conftest).
from sqlmodel import select
from app.models import RefreshToken, AuditLog


def _login(client):
    r = client.post("/api/auth/login", json={"username": "admin", "password": "Str0ng-passw0rd!"})
    assert r.status_code == 200
    return client.cookies.get("refresh_token")


def test_rotation_keeps_family(client, session_sync):
    first = _login(client)
    client.post("/api/auth/refresh")
    tokens = session_sync.exec(select(RefreshToken)).all()
    assert len({t.family_id for t in tokens}) == 1


def test_reuse_of_rotated_token_revokes_family(client, session_sync):
    old_refresh = _login(client)
    r1 = client.post("/api/auth/refresh")
    assert r1.status_code == 200
    # replay the OLD (now rotated) refresh token
    client.cookies.set("refresh_token", old_refresh)
    r2 = client.post("/api/auth/refresh")
    assert r2.status_code == 401
    tokens = session_sync.exec(select(RefreshToken)).all()
    assert all(t.revoked for t in tokens)
    actions = [a.action for a in session_sync.exec(select(AuditLog)).all()]
    assert "auth.refresh_reuse" in actions
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement.**

`models.py` RefreshToken — add field:

```python
class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"

    jti: str = Field(primary_key=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    family_id: str = Field(default="", index=True)
    expires_at: datetime
    revoked: bool = False
    user_agent: str | None = None
    created_at: datetime = Field(default_factory=_now)
```

`routers/auth.py` — thread `family_id` through `_issue_session` and detect reuse in `refresh`:

```python
async def _issue_session(resp: Response, session: AsyncSession, user: User,
                         request: Request, family_id: str | None = None) -> None:
    access = tokens.create_access_token(user.id, user.role)
    refresh, jti = tokens.create_refresh_token(user.id)
    session.add(RefreshToken(
        jti=jti, user_id=user.id,
        family_id=family_id or jti,
        expires_at=_now() + timedelta(seconds=_settings.REFRESH_TTL),
        user_agent=request.headers.get("user-agent"),
    ))
    user.last_login = _now()
    session.add(user)
    await session.commit()
    _set_auth_cookies(resp, access, refresh, new_csrf_token())
```

`refresh` endpoint — replace the `stored or revoked` check:

```python
    stored = await session.get(RefreshToken, claims["jti"])
    if not stored:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    if stored.revoked:
        # RFC 9700: replay of a rotated token — assume theft, kill the family
        await session.exec(
            update(RefreshToken)
            .where(RefreshToken.family_id == stored.family_id)
            .values(revoked=True)
        )
        await audit_request(session, request, "auth.refresh_reuse",
                            user_id=stored.user_id, resource=stored.family_id)
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh revoked")
    user = await session.get(User, claims["sub"])
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User inactive")
    stored.revoked = True
    session.add(stored)
    await _issue_session(response, session, user, request, family_id=stored.family_id)
    return {"ok": True}
```

Add imports to `auth.py`: `from app.services.audit import audit_request`.

Also add login audit (success + failure) in `login`:

```python
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        await audit_request(session, request, "auth.login_failed",
                            detail={"username": body.username})
        await session.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    await _issue_session(response, session, user, request)
    await audit_request(session, request, "auth.login", user_id=user.id)
    await session.commit()
```

- [ ] **Step 4: Run** — new file + `tests/test_auth_router.py` + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): refresh-token families with RFC 9700 reuse detection"`

---

### Task 5: CSRF on refresh + accept-invite; anonymous CSRF bootstrap

**Files:**
- Modify: `backend/app/main.py:31` (`_CSRF_EXEMPT`), `backend/app/routers/auth.py`
- Modify: `frontend/src/pages/AcceptInvitePage.tsx` (mount hook), `frontend/src/api/client.ts` if needed
- Test: `backend/tests/test_csrf_refresh.py` (create)

Frontend `client.ts:44-45` already attaches `X-CSRF-Token` to every request when the `csrf_token` cookie exists, so authenticated refresh keeps working once the exemption is dropped. Accept-invite is anonymous → needs a CSRF cookie issued before POST.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_csrf_refresh.py
def test_refresh_without_csrf_header_rejected(client):
    client.post("/api/auth/login", json={"username": "admin", "password": "Str0ng-passw0rd!"})
    client.headers.pop("X-CSRF-Token", None)
    r = client.post("/api/auth/refresh")
    assert r.status_code == 403


def test_csrf_bootstrap_sets_cookie(client):
    r = client.get("/api/auth/csrf")
    assert r.status_code == 200
    assert "csrf_token" in r.cookies


def test_accept_invite_without_csrf_rejected(client):
    r = client.post("/api/auth/accept-invite",
                    json={"token": "x", "username": "u", "password": "p"})
    assert r.status_code == 403
```

(Check how existing CSRF tests in the suite drive the header — `tests/` has CSRF coverage for other endpoints; mirror its client usage.)

- [ ] **Step 2: Run, verify fails** (refresh/accept-invite currently exempt → 200/400 not 403; `/csrf` → 404).

- [ ] **Step 3: Implement.**

`main.py:31`:

```python
_CSRF_EXEMPT = {"/api/auth/login", "/api/auth/setup"}
```

`routers/auth.py` — add bootstrap endpoint (GET = safe method, not CSRF-checked):

```python
@router.get("/csrf")
async def csrf_bootstrap(response: Response):
    """Issue an anonymous CSRF cookie so pre-auth POSTs (accept-invite) can
    pass the double-submit check."""
    response.set_cookie(
        CSRF_COOKIE, new_csrf_token(), max_age=600,
        httponly=False, secure=_settings.COOKIE_SECURE,
        samesite="strict", domain=_settings.COOKIE_DOMAIN,
    )
    return {"ok": True}
```

`frontend/src/pages/AcceptInvitePage.tsx` — on mount, fetch the cookie:

```tsx
useEffect(() => {
  void fetch("/api/auth/csrf", { credentials: "include" });
}, []);
```

(Place alongside the page's existing imports; `useEffect` from react.)

- [ ] **Step 4: Run** — backend suite PASS; `cd frontend && npx tsc --noEmit` clean.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): CSRF-protect refresh and accept-invite, add anonymous CSRF bootstrap"`

---

### Task 6: Account linking always requires verified email

**Files:**
- Modify: `backend/app/services/federation.py:124-127`, `backend/app/routers/auth.py:216`
- Test: `backend/tests/test_federation.py` (extend — file exists with federation tests)

- [ ] **Step 1: Failing test** (append to existing federation test file, reusing its `OAuthIdentity` construction pattern):

```python
@pytest.mark.asyncio
async def test_link_rejects_unverified_email_even_with_trust_email(session, user):
    identity = OAuthIdentity(sub="s1", email="a@b.c", email_verified=False, claims={})
    with pytest.raises(EmailUnverified):
        await link_identity(session, user, "google", identity, trust_email=True)
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement** — `federation.py`:

```python
async def link_identity(session: AsyncSession, user: User, provider_name: str,
                        identity: OAuthIdentity) -> None:
    # Linking is account takeover surface (COAT): always require a verified
    # email regardless of the provider's trust_email login setting.
    if not identity.email_verified:
        raise EmailUnverified("IdP did not provide a verified email")
    ...
```

Drop the `trust_email` param; update the call site `routers/auth.py:216`:

```python
        await federation.link_identity(session, user, name, identity)
```

Audit the link in `link_callback` after success:

```python
        await audit_request(session, request, "sso.link", user_id=user.id,
                            resource=name, detail={"email": identity.email})
        await session.commit()
```

And in `unlink_provider` before `return`:

```python
    await audit_request(session, request, "sso.unlink", user_id=user.id, resource=name)
    await session.commit()
```

(`unlink_provider` needs `request: Request` added to its signature.)

- [ ] **Step 4: Run** — federation + oauth router tests + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(sso): always require verified email for account linking"`

---

### Task 7: `auto_promote_admins` toggle + elevation audit

**Files:**
- Modify: `backend/app/models.py` (OAuthProvider), `backend/app/services/federation.py`, `backend/app/routers/oauth.py:73-75`, `backend/app/schemas.py:135,151,167` (ProviderCreate/Update/Out blocks), `backend/app/routers/oauth_admin.py:36-37,74-75` (mirror `allow_signup` plumbing)
- Test: `backend/tests/test_federation.py` (extend)

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.asyncio
async def test_no_elevation_when_auto_promote_disabled(session):
    # invite for role=user; claims contain admin group; auto_promote=False
    user = await resolve_identity(
        session, "authentik", _identity(groups=["admins"]),
        role_map={"admin_group": "admins"}, allow_signup=True,
        auto_promote_admins=False,
    )
    assert user.role == "user"


@pytest.mark.asyncio
async def test_elevation_is_audited(session):
    user = await resolve_identity(
        session, "authentik", _identity(groups=["admins"]),
        role_map={"admin_group": "admins"}, allow_signup=True,
        auto_promote_admins=True,
    )
    assert user.role == "admin"
    rows = (await session.exec(select(AuditLog))).all()
    assert any(r.action == "user.role_change" and r.detail.get("via") == "idp_group"
               for r in rows)
```

(Adapt `_identity(...)` helper to the existing test file's identity factory.)

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement.**

`models.py` OAuthProvider — add after `allow_signup`:

```python
    auto_promote_admins: bool = True   # IdP admin-group claim elevates role
```

`federation.py` — `resolve_identity` and `_signup_role` gain the flag:

```python
async def resolve_identity(session, provider_name, identity, role_map=None,
                           trust_email=False, allow_signup=False,
                           auto_promote_admins=True) -> User:
```

- branch 3 (invite): `role = _elevate(invite.role, identity.claims, role_map) if auto_promote_admins else invite.role`
- branch 4 (signup): pass through to `_signup_role(identity.claims, role_map, auto_promote_admins)`; in `_signup_role`, when `auto_promote_admins` is False, skip the admin-group branch (admin group still satisfies the user-group gate: treat membership as "user").
- wherever the resolved role becomes `admin` via group claim, write the audit row before returning:

```python
from app.services.audit import audit
if role == "admin":
    await audit(session, "user.role_change", user_id=user.id, resource=user.id,
                detail={"via": "idp_group", "provider": provider_name, "new_role": "admin"})
```

(For the not-promoted case when flag is off but the group matched, log `admin_claim_pending` the same way with `detail={"via": "idp_group", "pending": True}`.)

`routers/oauth.py:73-75` — pass `provider.auto_promote_admins`.

`schemas.py` — mirror `allow_signup` in the three provider schemas:
- line ~136 (`ProviderCreate`): `auto_promote_admins: bool = True`
- line ~152 (`ProviderUpdate`): `auto_promote_admins: bool | None = None`
- line ~168 (`ProviderOut`): `auto_promote_admins: bool`

`routers/oauth_admin.py` — mirror `allow_signup` at lines 36-37 (out mapping: `auto_promote_admins=bool(p.auto_promote_admins)`) and 74-75 (create mapping); the update path uses `model_dump(exclude_unset=True)` or explicit sets — follow whatever `allow_signup` does there. Add `await audit_request(...)` calls `provider.create|update|delete` in the three admin mutations with `detail={"name": p.name}`.

- [ ] **Step 4: Run** — federation + oauth_admin tests + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(sso): auto_promote_admins toggle, audit IdP role elevation"`

---

### Task 8: Subdomain validation

**Files:**
- Modify: `backend/app/schemas.py:47-52` (InstanceCreate)
- Test: `backend/tests/test_subdomain_validation.py` (create)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_subdomain_validation.py
import pytest
from pydantic import ValidationError

from app.schemas import InstanceCreate


def _make(sub):
    return InstanceCreate(template_id="t", name="n", subdomain=sub)


@pytest.mark.parametrize("good", ["abc", "a", "my-desktop-2", "x" * 63])
def test_valid_subdomains(good):
    assert _make(good).subdomain == good


@pytest.mark.parametrize("bad", [
    "", "-abc", "abc-", "ab_c", "AB", "a.b", "a/b", "a`b", "a b",
    "x" * 64, "$(rm -rf)", "api", "traefik", "www",
])
def test_invalid_subdomains_rejected(bad):
    with pytest.raises(ValidationError):
        _make(bad)
```

- [ ] **Step 2: Run, verify fails** (uppercase/reserved currently accepted).

- [ ] **Step 3: Implement** — in `schemas.py`:

```python
import re
from pydantic import BaseModel, field_validator

SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_SUBDOMAINS = {"api", "traefik", "www", "admin", "auth", "portal"}


class InstanceCreate(BaseModel):
    template_id: str
    name: str
    subdomain: str
    env_overrides: dict[str, str] = {}
    session_config: dict[str, Any] | None = None

    @field_validator("subdomain")
    @classmethod
    def _valid_subdomain(cls, v: str) -> str:
        if not SUBDOMAIN_RE.match(v):
            raise ValueError(
                "subdomain must be 1-63 chars: lowercase letters, digits, "
                "hyphens (no leading/trailing hyphen)"
            )
        if v in RESERVED_SUBDOMAINS:
            raise ValueError(f"'{v}' is a reserved name")
        return v
```

The subdomain feeds container names (`selkies-{subdomain}`), Traefik middleware keys, and path prefixes in `route_writer.py` — this validator closes the injection path at the only write site (`InstanceUpdate` has no subdomain field; recreate reuses the stored value).

- [ ] **Step 4: Run** — new tests + `tests/test_instances*.py` (fixtures may use invalid subdomains — fix fixtures, not the validator) → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(security): validate instance subdomains, reserve system names"`

---

### Task 9: Shared-template admin gate + PATCH allowlists

**Files:**
- Modify: `backend/app/routers/templates.py:67-103`, `backend/app/routers/instances.py` (update endpoint, ~line 630)
- Test: `backend/tests/test_templates_authz.py` (create)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_templates_authz.py
# Use the existing non-admin client fixture + a seeded shared template (owner_id=None).

def test_non_admin_cannot_update_shared_template(user_client, shared_template):
    r = user_client.put(f"/api/templates/{shared_template.id}", json={"display_name": "x"})
    assert r.status_code == 403


def test_non_admin_cannot_delete_shared_template(user_client, shared_template):
    r = user_client.delete(f"/api/templates/{shared_template.id}")
    assert r.status_code == 403


def test_admin_can_update_shared_template(admin_client, shared_template):
    r = admin_client.put(f"/api/templates/{shared_template.id}", json={"display_name": "x"})
    assert r.status_code == 200
```

- [ ] **Step 2: Run, verify fails** (`require_owner_or_admin(None, user)` — check `app/security/deps.py`; if owner_id None currently passes for everyone, tests fail as expected).

- [ ] **Step 3: Implement** — in both `update_template` and `delete_template`:

```python
    if template.owner_id is None:
        if user.role != "admin":
            raise HTTPException(403, "Shared templates can only be modified by admins")
    else:
        require_owner_or_admin(template.owner_id, user)
```

Mass-assignment allowlist — `update_template` field loop becomes:

```python
    ALLOWED = {"display_name", "image", "icon", "description", "env_vars",
               "gpu_enabled", "gpu_count", "memory_limit", "cpu_limit", "shm_size",
               "dind", "volumes", "internal_port", "internal_protocol",
               "category", "tags", "session_config",
               "cap_add", "security_opt", "tls_skip_verify"}
    for field, value in body.model_dump(exclude_unset=True).items():
        if field in ALLOWED:
            setattr(template, field, value)
```

(`cap_add`/`security_opt`/`tls_skip_verify` land in Task 11; harmless to allowlist now.) Same pattern in `instances.py` update endpoint: allowlist `{"name", "env_overrides", "session_config"}`.

- [ ] **Step 4: Run** — full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(authz): admin-only shared templates, explicit PATCH field allowlists"`

---

### Task 10: Instance quota + per-user create rate limit

**Files:**
- Modify: `backend/app/config.py` (add settings), `backend/app/routers/instances.py:204-235`
- Test: `backend/tests/test_instance_quota.py` (create)

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_instance_quota.py
# user_client fixture = authenticated non-admin; template fixture exists.

def _payload(template, i):
    return {"template_id": template.id, "name": f"n{i}", "subdomain": f"quota-test-{i}"}


def test_user_quota_enforced(user_client, template, monkeypatch):
    from app.config import Settings
    monkeypatch.setattr("app.routers.instances._settings.MAX_INSTANCES_PER_USER", 2)
    assert user_client.post("/api/instances", json=_payload(template, 1)).status_code == 201
    assert user_client.post("/api/instances", json=_payload(template, 2)).status_code == 201
    r = user_client.post("/api/instances", json=_payload(template, 3))
    assert r.status_code == 429


def test_admin_exempt_from_quota(admin_client, template, monkeypatch):
    monkeypatch.setattr("app.routers.instances._settings.MAX_INSTANCES_PER_USER", 1)
    assert admin_client.post("/api/instances", json=_payload(template, 4)).status_code == 201
    assert admin_client.post("/api/instances", json=_payload(template, 5)).status_code == 201
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement.**

`config.py` — add:

```python
    MAX_INSTANCES_PER_USER: int = 3      # 0 = unlimited; admins exempt
    RATE_LIMIT_INSTANCE_CREATE: str = "10/3600"  # per user
```

`routers/instances.py` — module level:

```python
from app.config import Settings
from app.middleware.rate_limit import SlidingWindow

_settings = Settings()
_limit, _window = _settings.RATE_LIMIT_INSTANCE_CREATE.split("/")
_create_limiter = SlidingWindow(int(_limit), int(_window))
```

In `create_instance`, after the template lookup:

```python
    if user.role != "admin":
        if not _create_limiter.allow(user.id):
            raise HTTPException(429, "Too many instances created recently — try again later")
        quota = _settings.MAX_INSTANCES_PER_USER
        if quota > 0:
            owned = (await session.exec(
                select(Instance).where(Instance.owner_id == user.id)
            )).all()
            if len(owned) >= quota:
                raise HTTPException(
                    429, f"Instance limit reached ({quota}). Delete an instance first."
                )
```

Audit create + delete (in `create_instance` after commit, and in the delete endpoint):

```python
    await audit(session, "instance.create", user_id=user.id, resource=instance.id,
                detail={"template": template.name, "subdomain": instance.subdomain})
    await session.commit()
```

- [ ] **Step 4: Run** — new tests + instances suite → PASS. (Note `_settings` may already exist in instances.py under a different name — reuse, don't duplicate.)
- [ ] **Step 5: Commit** — `git commit -am "feat(security): per-user instance quota and creation rate limit"`

---

### Task 11: Container hardening defaults + template overrides

**Files:**
- Modify: `backend/app/services/docker_manager.py:39-101`, `backend/app/models.py` (ServiceTemplate), `backend/app/schemas.py` (TemplateCreate/Update), `backend/app/routers/instances.py` (launch call sites ~lines 60-80, 130-160), `backend/app/routers/templates.py` (DinD limit check)
- Test: `backend/tests/test_docker_manager.py` (extend — exists, mocks `docker.DockerClient.from_env`)

- [ ] **Step 1: Failing tests** (append; mirror existing mock pattern in the file):

```python
def test_default_container_is_confined(mock_docker):
    mgr = DockerManager()
    mgr.create_container(name="n", image="img", labels={}, environment={},
                         volumes={}, port=3001)
    kwargs = mock_docker.containers.create.call_args.kwargs
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["cap_drop"] == ["ALL"]
    assert kwargs["privileged"] is False
    assert "sysctls" not in kwargs or kwargs["sysctls"] == {}


def test_template_cap_add_and_security_opt_passthrough(mock_docker):
    mgr = DockerManager()
    mgr.create_container(name="n", image="img", labels={}, environment={},
                         volumes={}, port=3001,
                         cap_add=["SYS_NICE"], security_opt=["seccomp=unconfined"])
    kwargs = mock_docker.containers.create.call_args.kwargs
    assert kwargs["cap_add"] == ["SYS_NICE"]
    assert "seccomp=unconfined" in kwargs["security_opt"]
    assert "no-new-privileges:true" in kwargs["security_opt"]


def test_dind_requires_memory_limit(mock_docker):
    mgr = DockerManager()
    with pytest.raises(ValueError, match="resource limits"):
        mgr.create_container(name="n", image="img", labels={}, environment={},
                             volumes={}, port=3001, dind=True, memory_limit=None)


def test_dind_still_privileged_with_limits(mock_docker):
    mgr = DockerManager()
    mgr.create_container(name="n", image="img", labels={}, environment={},
                         volumes={}, port=3001, dind=True, memory_limit="4g",
                         cpu_limit="2")
    kwargs = mock_docker.containers.create.call_args.kwargs
    assert kwargs["privileged"] is True
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement.**

`models.py` ServiceTemplate — add after `dind`:

```python
    cap_add: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    security_opt: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    tls_skip_verify: bool = False
```

`schemas.py` — add the same three to `TemplateCreate` (defaults `[]`, `[]`, `False`) and `TemplateUpdate` (all `| None = None`).

`routers/templates.py` — in `create_template` and `update_template`, gate the new knobs like DinD:

```python
    if (body.cap_add or body.security_opt) and user.role != "admin":
        raise HTTPException(403, "cap_add/security_opt overrides require admin")
```

`docker_manager.py` `create_container` — new signature params `cap_add: list[str] | None = None, security_opt: list[str] | None = None`, and replace the kwargs block:

```python
        if dind:
            privileged = True
            environment = {**environment, "START_DOCKER": "true"}
            if not memory_limit or not cpu_limit:
                raise ValueError(
                    "DinD templates require explicit resource limits (memory + cpu)"
                )

        sec_opts = ["no-new-privileges:true"] + list(security_opt or [])
        kwargs: dict = {
            "name": name,
            "image": image,
            "labels": labels,
            "environment": {"PIXELFLUX_WAYLAND": "true", **environment},
            "volumes": volumes,
            "detach": True,
            "network": self._network_name,
            "privileged": privileged,
        }
        if privileged:
            # privileged implies all caps; cap flags are ignored/invalid
            kwargs["security_opt"] = list(security_opt or [])
        else:
            kwargs["security_opt"] = sec_opts
            kwargs["cap_drop"] = ["ALL"]
            kwargs["cap_add"] = list(cap_add or [])
```

Drop the unconditional `sysctls net.ipv4.ip_unprivileged_port_start=0` — Selkies listens on 3001 (>1024). If a seed template truly needs a low port, expose a `sysctls`-free workaround via `cap_add: ["NET_BIND_SERVICE"]` on that template.

`routers/instances.py` — both launch call sites (`_launch_instance_background` and recreate, ~lines 60-80 and 130-160) pass the new fields:

```python
        cap_add=template.cap_add,
        security_opt=template.security_opt,
```

If `cpu_limit` exists on templates but was never passed to Docker, wire it now: `if cpu_limit: kwargs["nano_cpus"] = int(float(cpu_limit) * 1e9)`.

**Seed templates** (`templates/*.json`): leave `cap_add: []` initially. The desktop images may fail to boot fully confined — that's expected to be resolved empirically in the smoke test (Task 20): boot each seed template, add the minimal caps to its JSON, re-test. Document final cap set in the template file.

- [ ] **Step 4: Run** — docker manager + instances suites + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): confined containers by default, admin-gated cap overrides, DinD limits mandatory"`

---

### Task 12: Per-user Docker networks

**Files:**
- Modify: `backend/app/services/docker_manager.py`, `backend/app/routers/instances.py` (launch + delete), `docker-compose.yml` (traefik `container_name`)
- Test: `backend/tests/test_docker_manager.py` (extend)

- [ ] **Step 1: Failing tests**

```python
def test_ensure_user_network_creates_and_attaches_traefik(mock_docker):
    import docker.errors
    mock_docker.networks.get.side_effect = docker.errors.NotFound("x")
    mgr = DockerManager()
    name = mgr.ensure_user_network("user-1234567890ab-extra")
    assert name == "styx-u-user-1234567"
    mock_docker.networks.create.assert_called_once_with(name, driver="bridge")
    created = mock_docker.networks.create.return_value
    created.connect.assert_called_once_with("styx-traefik")


def test_ensure_user_network_idempotent(mock_docker):
    mgr = DockerManager()
    mgr.ensure_user_network("u1")  # networks.get succeeds → no create
    mock_docker.networks.create.assert_not_called()


def test_create_container_uses_network_override(mock_docker):
    mgr = DockerManager()
    mgr.create_container(name="n", image="img", labels={}, environment={},
                         volumes={}, port=3001, network="styx-u-abc")
    assert mock_docker.containers.create.call_args.kwargs["network"] == "styx-u-abc"
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement.**

`docker_manager.py`:

```python
TRAEFIK_CONTAINER = "styx-traefik"


class DockerManager:
    ...
    def ensure_user_network(self, user_id: str) -> str:
        """Per-user bridge network; traefik is attached so it can route to
        instance containers. Backend itself never joins user networks."""
        name = f"styx-u-{user_id[:12]}"
        try:
            self._client.networks.get(name)
            return name
        except docker.errors.NotFound:
            pass
        net = self._client.networks.create(name, driver="bridge")
        try:
            net.connect(TRAEFIK_CONTAINER)
        except docker.errors.APIError:
            pass  # already connected or traefik not named — routing falls back
        return name

    def remove_user_network(self, user_id: str) -> None:
        name = f"styx-u-{user_id[:12]}"
        try:
            net = self._client.networks.get(name)
            try:
                net.disconnect(TRAEFIK_CONTAINER)
            except docker.errors.APIError:
                pass
            net.remove()
        except docker.errors.NotFound:
            pass
        except docker.errors.APIError:
            pass  # still has containers — leave it
```

`create_container` gains `network: str | None = None`; kwargs uses `"network": network or self._network_name`.

`routers/instances.py` — in `_launch_instance_background` and the recreate path, before `create_container`:

```python
        net = None
        if instance.owner_id:
            net = await asyncio.to_thread(docker.ensure_user_network, instance.owner_id)
```

pass `network=net` to `create_container`. In the delete endpoint, after container removal, best-effort cleanup when the user has no other instances:

```python
    if instance.owner_id:
        remaining = (await session.exec(select(Instance).where(
            Instance.owner_id == instance.owner_id, Instance.id != instance.id))).all()
        if not remaining:
            await asyncio.to_thread(docker.remove_user_network, instance.owner_id)
```

`docker-compose.yml` traefik service — pin the name so the backend can attach it:

```yaml
  traefik:
    image: traefik:v3.4
    container_name: styx-traefik
```

- [ ] **Step 4: Run** — full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): per-user docker networks kill cross-user lateral movement"`

---

### Task 13: Per-template `tls_skip_verify` in route writer

**Files:**
- Modify: `backend/app/services/route_writer.py`
- Test: `backend/tests/test_route_writer.py` (extend — exists)

- [ ] **Step 1: Failing tests**

```python
def test_insecure_transport_only_when_template_opts_in():
    cfg = build_routes_config(
        [{"id": "i1", "subdomain": "a", "port": 3001, "protocol": "https",
          "tls_skip_verify": True},
         {"id": "i2", "subdomain": "b", "port": 8443, "protocol": "https",
          "tls_skip_verify": False}],
        "example.com")
    assert cfg["http"]["services"]["i1"]["loadBalancer"]["serversTransport"] == "selkies-transport"
    assert "serversTransport" not in cfg["http"]["services"]["i2"]["loadBalancer"]


def test_no_transport_block_when_no_instance_opts_in():
    cfg = build_routes_config(
        [{"id": "i2", "subdomain": "b", "port": 8443, "protocol": "https",
          "tls_skip_verify": False}],
        "example.com")
    assert "serversTransports" not in cfg["http"]
```

- [ ] **Step 2: Run, verify fails.**

- [ ] **Step 3: Implement** — in `build_routes_config`, replace the `if protocol == "https":` block:

```python
        if protocol == "https" and inst.get("tls_skip_verify"):
            svc_config["serversTransport"] = "selkies-transport"
            has_https = True
```

In `refresh_routes_from_db`, include the template flag:

```python
            "tls_skip_verify": bool(tmpl.tls_skip_verify) if tmpl else False,
```

**Seed templates:** Selkies images serve self-signed HTTPS internally — set `"tls_skip_verify": true` in each seed template JSON that has `"internal_protocol": "https"` (`templates/*.json`), otherwise existing deployments break on upgrade.

- [ ] **Step 4: Run** — route writer + full suite → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(security): scope insecureSkipVerify to templates that opt in"`

---

### Task 14: Conditional CORS dev origin + SQLite perms

**Files:**
- Modify: `backend/app/main.py:225-231`, `backend/app/database.py` (`init_db`)
- Test: inline assertions via existing app tests (CORS config is wiring; cover with one test)

- [ ] **Step 1: Implement CORS** (`main.py`):

```python
_cors_origins = [f"https://{_settings.DOMAIN}"]
if not _settings.COOKIE_SECURE:
    _cors_origins.append("http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
```

- [ ] **Step 2: Implement SQLite perms** (`database.py` end of `init_db`):

```python
import os
import stat
from pathlib import Path

async def init_db():
    async with engine.begin() as conn:
        await _run_migrations(conn)
        await conn.run_sync(SQLModel.metadata.create_all)
    _restrict_db_perms()
    async with async_session() as session:
        await seed_templates(session, settings.TEMPLATES_DIR)


def _restrict_db_perms():
    url = settings.DATABASE_URL
    if "sqlite" not in url:
        return
    path = Path(url.split("///")[-1])
    if path.exists():
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)  # 0600
```

- [ ] **Step 3: Test**

```python
# append to backend/tests/test_database_migrations.py
def test_restrict_db_perms_noop_for_memory(monkeypatch):
    from app import database
    monkeypatch.setattr(database.settings, "DATABASE_URL", "sqlite+aiosqlite://")
    database._restrict_db_perms()  # must not raise
```

- [ ] **Step 4: Run full suite + ruff** → PASS.
- [ ] **Step 5: Commit** — `git commit -am "fix(security): dev CORS origin only without COOKIE_SECURE, chmod 0600 sqlite"`

---

### Task 15: Backend Dockerfile non-root

**Files:**
- Modify: `backend/Dockerfile`, `docker-compose.yml` (backend service `group_add`)

- [ ] **Step 1: Implement**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .
RUN playwright install --with-deps chromium

# non-root runtime user; video/render groups for /dev/dri access
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app

COPY --chown=appuser:appuser app/ app/

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`docker-compose.yml` backend service — add:

```yaml
    group_add:
      - video
      - render
```

Caveat: playwright installs chromium for root during build; verify screenshots still work as appuser — `playwright install` may need to run as appuser instead (move the `RUN playwright install --with-deps chromium` after `USER appuser` if the smoke test shows browser-launch failures; `--with-deps` needs root, so split: `RUN playwright install-deps chromium` as root, then `USER appuser`, then `RUN playwright install chromium`).

- [ ] **Step 2: Verify build** — `docker build -t styx-backend-test ./backend` → succeeds.
- [ ] **Step 3: Commit** — `git commit -am "feat(security): run backend as non-root user"`

---

### Task 16: nginx security headers

**Files:**
- Modify: `frontend/nginx.conf`

- [ ] **Step 1: Implement** — add inside the `server` block, above the location blocks:

```nginx
    # Security headers (mirror backend SecurityHeadersMiddleware; HSTS is set
    # at the edge — Cloudflare or Traefik direct-mode middleware — not here,
    # so plain-HTTP LAN access in tunnel mode isn't bricked).
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
```

Compare with `backend/app/middleware/security_headers.py` CSP first — the values must match (frontend serves the SPA shell; backend covers `/api`). If the backend CSP differs (e.g. allows `data:` fonts), copy the backend's exact policy string.

Note: nginx `add_header` in a `location` block suppresses server-level headers — the `/assets/` and `/index.html` locations use `add_header Cache-Control ...`, so repeat the security headers in those two location blocks (nginx inheritance rule).

- [ ] **Step 2: Verify** — `docker build -t styx-frontend-test ./frontend && docker run --rm styx-frontend-test nginx -t` → "syntax is ok".
- [ ] **Step 3: Commit** — `git commit -am "feat(security): security headers on frontend nginx"`

---

### Task 17: docker-socket-proxy + healthchecks + compose hardening

**Files:**
- Modify: `docker-compose.yml`, `backend/app/services/docker_manager.py:36` (client from env URL), `backend/app/config.py` (DOCKER_SOCKET already exists)

- [ ] **Step 1: DockerManager honors DOCKER_SOCKET.** Current code uses `docker.DockerClient.from_env()` which reads `DOCKER_HOST` env. Change to explicit settings-driven URL:

```python
from app.config import Settings

class DockerManager:
    def __init__(self, network_name: str = "styx-portal", base_url: str | None = None):
        url = base_url or Settings().DOCKER_SOCKET
        self._client = docker.DockerClient(base_url=url)
        self._network_name = network_name
```

Test (extend `test_docker_manager.py`, patching `docker.DockerClient` instead of `from_env` — update existing mocks accordingly):

```python
def test_manager_uses_configured_socket(monkeypatch):
    captured = {}
    class FakeClient:
        def __init__(self, base_url=None):
            captured["url"] = base_url
    monkeypatch.setattr("docker.DockerClient", FakeClient)
    DockerManager(base_url="tcp://docker-proxy:2375")
    assert captured["url"] == "tcp://docker-proxy:2375"
```

- [ ] **Step 2: Compose changes** — full new `docker-compose.yml`:

```yaml
networks:
  styx-portal:
    name: styx-portal
    driver: bridge
  styx-docker:
    name: styx-docker
    internal: true

volumes:
  db-data:
  screenshots:
  traefik-dynamic:
  letsencrypt:

services:
  docker-proxy:
    image: lscr.io/linuxserver/socket-proxy:latest
    restart: unless-stopped
    read_only: true
    tmpfs:
      - /run
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    environment:
      - CONTAINERS=1
      - IMAGES=1
      - NETWORKS=1
      - VOLUMES=1
      - POST=1
      - INFO=1
      - EVENTS=1
      - PING=1
      - EXEC=0
      - BUILD=0
      - COMMIT=0
      - SWARM=0
      - SYSTEM=0
    networks:
      - styx-docker
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:2375/_ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  traefik:
    profiles: ["tunnel"]
    image: traefik:v3.4
    container_name: styx-traefik
    restart: unless-stopped
    # tunnel mode (default): no host ports — cloudflared is the only ingress
    volumes:
      - ./traefik/traefik.yml:/etc/traefik/traefik.yml:ro
      - traefik-dynamic:/etc/traefik/dynamic:ro
    networks:
      - styx-portal
    healthcheck:
      test: ["CMD", "traefik", "healthcheck", "--ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  traefik-direct:
    profiles: ["direct"]
    image: traefik:v3.4
    container_name: styx-traefik
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    environment:
      - LE_EMAIL=${LE_EMAIL:-}
      - CF_DNS_API_TOKEN=${CF_DNS_API_TOKEN:-}   # cloudflare example; see .env.example
    volumes:
      - ./traefik/traefik-direct.yml:/etc/traefik/traefik.yml:ro
      - traefik-dynamic:/etc/traefik/dynamic:ro
      - letsencrypt:/letsencrypt
    networks:
      - styx-portal
    healthcheck:
      test: ["CMD", "traefik", "healthcheck", "--ping"]
      interval: 30s
      timeout: 5s
      retries: 3

  cloudflared:
    profiles: ["tunnel"]
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel run
    depends_on:
      - traefik
      - frontend
    environment:
      - TUNNEL_TOKEN=${CF_TUNNEL_TOKEN}
    networks:
      - styx-portal

  backend:
    build: ./backend
    restart: unless-stopped
    depends_on:
      docker-proxy:
        condition: service_healthy
    environment:
      - DOMAIN=${DOMAIN}
      - DATABASE_URL=sqlite+aiosqlite:///./data/styx-portal.db
      - DOCKER_SOCKET=tcp://docker-proxy:2375
      - DOCKER_NETWORK=styx-portal
      - TEMPLATES_DIR=/app/templates
      - JWT_SECRET=${JWT_SECRET:-}
      - COOKIE_SECURE=${COOKIE_SECURE:-true}
    volumes:
      - db-data:/app/data
      - screenshots:/app/data/screenshots
      - traefik-dynamic:/app/traefik-dynamic
      - ./templates:/app/templates:ro
    group_add:
      - video
      - render
    devices:
      - /dev/dri:/dev/dri
    networks:
      - styx-portal
      - styx-docker
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 15s

  frontend:
    build: ./frontend
    restart: unless-stopped
    depends_on:
      - backend
    networks:
      - styx-portal
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:3000/"]
      interval: 30s
      timeout: 5s
      retries: 3
```

Notes:
- **Docker socket mount is gone from backend.** Only docker-proxy sees it, read-only, on an `internal: true` network.
- `traefik` (profile `tunnel`) and `traefik-direct` (profile `direct`) share `container_name: styx-traefik`, so exactly one ingress runs per mode and the backend's network-attach target name is stable. Plain `docker compose up` starts no ingress — `.env` sets `COMPOSE_PROFILES=tunnel` (default in `.env.example`) so it works out of the box; `COMPOSE_PROFILES=direct` switches modes. `cloudflared` also carries profile `tunnel` and its `depends_on: traefik` stays valid within the profile.
- `AUTHENTIK_MIDDLEWARE` env removed from backend (config default suffices; legacy).
- Traefik `healthcheck --ping` requires `ping: {}` in static config — added in Task 18.
- Instance containers created by the backend get `network=styx-u-*` (Task 12), which the proxy permits via `NETWORKS=1`/`POST=1`.

- [ ] **Step 3: Verify** — `docker compose config -q` (validates both profiles: `COMPOSE_PROFILES=tunnel docker compose config -q` and `COMPOSE_PROFILES=direct docker compose config -q`).
- [ ] **Step 4: Run backend suite** (DockerManager constructor change) → PASS.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): docker-socket-proxy, healthchecks, deploy profiles"`

---

### Task 18: Traefik static configs (tunnel + direct), dashboard off

**Files:**
- Modify: `traefik/traefik.yml`
- Create: `traefik/traefik-direct.yml`
- Modify: `backend/app/services/route_writer.py` (dashboard router removal + entryPoint names)

- [ ] **Step 1: tunnel config** — `traefik/traefik.yml`:

```yaml
api:
  dashboard: false
  insecure: false

ping: {}

entryPoints:
  web:
    address: ":80"

providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true
```

- [ ] **Step 2: direct config** — `traefik/traefik-direct.yml`:

```yaml
api:
  dashboard: false
  insecure: false

ping: {}

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
  websecure:
    address: ":443"
    http:
      tls:
        certResolver: letsencrypt
        domains:
          - main: "${DOMAIN}"
            sans:
              - "*.${DOMAIN}"

certificatesResolvers:
  letsencrypt:
    acme:
      email: "${LE_EMAIL}"
      storage: /letsencrypt/acme.json
      dnsChallenge:
        provider: cloudflare   # see .env.example for other providers
        resolvers:
          - "1.1.1.1:53"

providers:
  file:
    directory: /etc/traefik/dynamic
    watch: true
```

Caveat: Traefik static YAML does **not** interpolate `${DOMAIN}` from container env. Two options — pick (a): (a) move entrypoint TLS domains out of static config and set the cert domains on the routers via the dynamic file (route_writer adds `tls: {certResolver: letsencrypt, domains: [...]}` per router when `DEPLOY_MODE=direct`), or (b) generate traefik-direct.yml from a template at startup. Option (a) keeps one static file; implement in Step 3.

- [ ] **Step 3: route_writer changes:**

```python
# config.py: add
    DEPLOY_MODE: str = "tunnel"   # tunnel | direct
```

In `build_routes_config`, accept `deploy_mode: str = "tunnel"` param (threaded from `_settings.DEPLOY_MODE` in `write_routes`):
- Remove the `dashboard` router block entirely (lines 43-47).
- When `deploy_mode == "direct"`, every router gets:

```python
            "entryPoints": ["websecure"],
            "tls": {
                "certResolver": "letsencrypt",
                "domains": [{"main": domain, "sans": [f"*.{domain}"]}],
            },
```

  (tunnel mode keeps `["web"]`, no tls block). Implement as a small helper applied to each router dict:

```python
def _router_transport(deploy_mode: str, domain: str) -> dict:
    if deploy_mode == "direct":
        return {
            "entryPoints": ["websecure"],
            "tls": {"certResolver": "letsencrypt",
                    "domains": [{"main": domain, "sans": [f"*.{domain}"]}]},
        }
    return {"entryPoints": ["web"]}
```

  and `router.update(_router_transport(deploy_mode, domain))` for frontend/api/instances_fallback/instance routers.

Tests (extend `test_route_writer.py`):

```python
def test_direct_mode_routes_use_websecure_tls():
    cfg = build_routes_config([], "example.com", deploy_mode="direct")
    fr = cfg["http"]["routers"]["frontend"]
    assert fr["entryPoints"] == ["websecure"]
    assert fr["tls"]["certResolver"] == "letsencrypt"


def test_tunnel_mode_routes_use_web_and_no_dashboard():
    cfg = build_routes_config([], "example.com")
    assert "dashboard" not in cfg["http"]["routers"]
    assert cfg["http"]["routers"]["frontend"]["entryPoints"] == ["web"]
```

Then simplify `traefik-direct.yml`: drop the `domains:` block under the websecure entrypoint (routers carry it), keeping the redirect + resolver:

```yaml
  websecure:
    address: ":443"
```

- [ ] **Step 4: Run** — route writer tests + full suite → PASS. `docker compose config -q` still clean.
- [ ] **Step 5: Commit** — `git commit -am "feat(security): direct TLS deploy mode, dashboard off by default"`

---

### Task 19: .env.example + README deployment notes

**Files:**
- Modify: `.env.example`, `README.md` (deployment section)

- [ ] **Step 1: .env.example** — replace secret/deploy sections:

```bash
# ── Deployment ────────────────────────────────────────────────
# Your portal domain (instances live under /i/<name> on this host)
DOMAIN=portal.example.com

# Ingress: "tunnel" (Cloudflare Tunnel, default) or "direct" (host ports 80/443
# with automatic Let's Encrypt wildcard TLS)
COMPOSE_PROFILES=tunnel
DEPLOY_MODE=tunnel

# tunnel mode only:
CF_TUNNEL_TOKEN=

# direct mode only — Let's Encrypt via DNS-01 (wildcard certs):
#LE_EMAIL=you@example.com
#CF_DNS_API_TOKEN=          # Cloudflare DNS API token (other providers: see Traefik docs)

# ── Secrets ───────────────────────────────────────────────────
# Leave JWT_SECRET empty: one is generated on first start and saved to the
# data volume (back it up!). To set your own: openssl rand -base64 48
JWT_SECRET=

# ── Cookies ───────────────────────────────────────────────────
# true (default) requires HTTPS end-to-end. Only set false for plain-HTTP
# local development.
COOKIE_SECURE=true
```

- [ ] **Step 2: README** — add a "Deployment modes" subsection documenting: tunnel vs direct, the `COMPOSE_PROFILES` + `DEPLOY_MODE` pair, auto-generated secret + backup note, DinD risk warning, quota env (`MAX_INSTANCES_PER_USER`). Keep it short — the full guide is Phase 3.

- [ ] **Step 3: Commit** — `git commit -am "docs: secure-by-default env + deployment modes"`

---

### Task 20: Smoke test + seed-template cap tuning

No code — verification checklist run on the dev host (requires Docker). Record results in the PR description.

- [ ] `cp .env.example .env`, set `DOMAIN` + `CF_TUNNEL_TOKEN` (or `COMPOSE_PROFILES=direct` + LE vars), leave `JWT_SECRET` empty → `docker compose up -d --build`
- [ ] Backend logs show generated-secret warning once; `docker compose ps` → all services healthy
- [ ] Setup wizard → create admin → login OK (CSRF + refresh work: stay logged in >15 min)
- [ ] Launch each seed template as a non-admin user:
  - desktop boots and is usable → record; if it fails, check `docker logs` for cap/privilege errors, add the minimal `cap_add` to that template JSON, `recreate`, repeat. Commit final cap sets: `git commit -am "feat(security): minimal capability sets for seed templates"`
- [ ] Verify isolation: two users, one instance each → `docker exec` into user A's container, `ping`/`curl` user B's container name → must fail (different networks)
- [ ] Verify socket proxy: `docker exec` into backend → `curl http://docker-proxy:2375/containers/json` works, `curl -X POST http://docker-proxy:2375/exec/...` → 403
- [ ] Quota: create instances past `MAX_INSTANCES_PER_USER` → 429 with friendly message
- [ ] Reuse detection: copy refresh cookie, refresh once, replay old cookie → 401 and all sessions for that family dead; `/api/audit` shows `auth.refresh_reuse`
- [ ] `GET /api/audit` as admin returns events; as user → 403
- [ ] Full suite + lint green: `cd backend && .venv/bin/python -m pytest && .venv/bin/python -m ruff check app/ tests/`

---

## Spec coverage map

| Spec section | Tasks |
|---|---|
| §1 secrets | 1, 19 |
| §2 TLS/deploy mode + dashboard + skip-verify | 13, 17, 18, 19 |
| §3 socket proxy | 17 |
| §4 isolation (caps, networks, DinD, quotas) | 11, 12, 10, 20 |
| §5 auth fixes (CSRF, reuse, linking, subdomain, shared templates, promotion, audit) | 3, 4, 5, 6, 7, 8, 9 |
| §6 hygiene (non-root, sqlite, healthchecks, nginx, CORS, migrations) | 2, 14, 15, 16, 17 |
