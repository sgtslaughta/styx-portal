# Workstation Streaming ("Styx Agent") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enroll physical Linux workstations into Styx Portal via a server-minted one-liner and stream their desktops (video + audio, GPU-encoded) to browsers through Traefik, alongside container instances.

**Architecture:** Backend gains three tables (`Workstation`, `WorkstationEnrollmentToken`, `WorkstationAccess`), public enroll/agent API routers (token-authenticated, CSRF-exempt), Traefik route generation pointing at workstation LAN IPs under `/w/{subdomain}`, and heartbeat-driven online/offline state. A new top-level `agent/` directory holds the bash enrollment script, a stdlib-only Python agent daemon (supervises Selkies, heartbeats), and an uninstall script — all served to workstations by the backend. Frontend gains an admin Workstations panel and user-facing workstation cards.

**Tech Stack:** FastAPI + SQLModel (existing patterns), Selkies portable tarball (cached/served by backend), systemd `--user` units, React/TS frontend.

**Spec:** `docs/superpowers/specs/2026-06-10-workstation-streaming-design.md`

**Spec deviations (intentional):**
1. Spec says routes use `Host(ws-{subdomain}.{domain})`. The codebase routes instances with `Host({domain}) && PathPrefix(/i/{sub})` (see `route_writer.py`). Workstations follow the existing pattern with `/w/{sub}` — no DNS changes, consistent middleware.
2. Tarball endpoint lives at `/api/enroll/artifacts/selkies.tar.gz` (spec said `/api/agent/...`) — it is needed before an agent token exists, so it belongs in the public enroll router.
3. Spec's "Health page gains a Workstations section" is covered by the Workstations admin panel itself (status badge, last seen, last error, 15 s auto-refresh); a duplicate Health section is deferred.
4. Agent endpoints use the existing default rate limit (120/60) rather than the stricter auth bucket — heartbeats are token-authenticated and arrive every 30 s per machine.

**Conventions used throughout:**
- All backend commands run from `backend/`: `.venv/bin/python -m pytest <file> -v`
- Datetime columns are naive-UTC in SQLite; compare with `tzinfo` guard (see Task 9).
- Commit after every task.

---

## File Map

| Path | Action | Purpose |
|---|---|---|
| `backend/app/models.py` | modify | 3 new tables |
| `backend/app/schemas.py` | modify | workstation request/response schemas |
| `backend/app/config.py` | modify | LAN URL, tarball URL, TTLs, agent dir |
| `backend/app/routers/workstations.py` | create | admin CRUD + mine + connect |
| `backend/app/routers/enroll.py` | create | public: script/agent/artifact serving + register |
| `backend/app/routers/agent.py` | create | heartbeat + deregister (agent-token auth) |
| `backend/app/services/workstations.py` | create | subdomain slug, command builder, stale-offline |
| `backend/app/services/artifacts.py` | create | Selkies tarball cache |
| `backend/app/services/route_writer.py` | modify | workstation routes |
| `backend/app/main.py` | modify | routers, CSRF exemptions, monitor loop |
| `agent/styx_agent.py` | create | daemon: run/status/doctor/uninstall |
| `agent/enroll.sh` | create | preflight + install + register |
| `agent/uninstall.sh` | create | removal |
| `agent/tests/test_styx_agent.py` | create | daemon unit tests |
| `docker-compose.yml` | modify | mount `./agent` into backend |
| `frontend/src/api/client.ts` | modify | API methods |
| `frontend/src/components/system/workstations-panel.tsx` | create | admin panel |
| `frontend/src/components/settings/nav-config.tsx` | modify | register panel |
| `frontend/src/components/instances/workstation-grid.tsx` | create | user cards |
| `frontend/src/components/instances/instance-workspace.tsx` | modify | mount grid |
| `docs/WORKSTATIONS.md` | create | admin + troubleshooting guide |

---

### Task 1: Models

**Files:**
- Modify: `backend/app/models.py` (append at end)
- Test: `backend/tests/test_workstation_models.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_workstation_models.py
import pytest
from datetime import datetime, timedelta, timezone

from app.models import User, Workstation, WorkstationEnrollmentToken, WorkstationAccess
from app.security.passwords import hash_password


@pytest.mark.asyncio
async def test_workstation_defaults(session):
    admin = User(username="a", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    ws = Workstation(name="desk", subdomain="desk", created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    assert ws.status == "pending"
    assert ws.display_server == "x11"
    assert ws.protocol == "http"
    assert ws.stream_settings["framerate"] == 60
    assert ws.all_users is False


@pytest.mark.asyncio
async def test_enrollment_token_and_access(session):
    admin = User(username="a", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    tok = WorkstationEnrollmentToken(
        token_hash="h" * 64, created_by=admin.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    ws = Workstation(name="desk", subdomain="desk", created_by=admin.id)
    session.add(tok)
    session.add(ws)
    await session.commit()
    session.add(WorkstationAccess(workstation_id=ws.id, user_id=admin.id))
    await session.commit()
    assert tok.used_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workstation_models.py -v`
Expected: FAIL — `ImportError: cannot import name 'Workstation'`

- [ ] **Step 3: Append models to `backend/app/models.py`**

```python
class Workstation(SQLModel, table=True):
    __tablename__ = "workstations"

    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str
    subdomain: str = Field(unique=True, index=True)
    hostname: str = ""
    lan_ip: str = ""
    port: int = 8443
    protocol: str = "http"               # selkies on the workstation; http for v1
    status: str = "pending"              # pending | online | offline | revoked
    display_server: str = "x11"          # x11 | wayland
    gpu_info: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    os_info: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    agent_version: str = ""
    agent_token_hash: str = Field(default="", index=True)
    selkies_password_enc: str = ""
    stream_settings: dict[str, Any] = Field(
        default_factory=lambda: {"encoder": "auto", "framerate": 60, "bitrate_kbps": 16000},
        sa_column=Column(JSON),
    )
    all_users: bool = False
    last_heartbeat: datetime | None = None
    last_error: str | None = None
    created_by: str = Field(foreign_key="users.id")
    created_at: datetime = Field(default_factory=_now)


class WorkstationEnrollmentToken(SQLModel, table=True):
    __tablename__ = "workstation_enrollment_tokens"

    id: str = Field(default_factory=_uuid, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    created_by: str = Field(foreign_key="users.id")
    expires_at: datetime
    used_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)


class WorkstationAccess(SQLModel, table=True):
    __tablename__ = "workstation_access"
    __table_args__ = (UniqueConstraint("workstation_id", "user_id", name="uq_workstation_user"),)

    id: int | None = Field(default=None, primary_key=True)
    workstation_id: str = Field(foreign_key="workstations.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    created_at: datetime = Field(default_factory=_now)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workstation_models.py -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_workstation_models.py
git commit -m "feat(workstations): Workstation, enrollment-token, access models"
```

---

### Task 2: Settings

**Files:**
- Modify: `backend/app/config.py`
- Test: `backend/tests/test_config.py` (append)

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_config.py`)

```python
def test_server_lan_url_falls_back_to_domain():
    from app.config import Settings
    s = Settings(DOMAIN="example.com", SERVER_LAN_URL="")
    assert s.server_lan_url() == "https://example.com"
    s2 = Settings(SERVER_LAN_URL="https://192.168.1.10/")
    assert s2.server_lan_url() == "https://192.168.1.10"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'server_lan_url'`

- [ ] **Step 3: Add settings.** In `backend/app/config.py`, inside `class Settings`, after `SECRETS_FILE` line add:

```python
    # --- Workstation streaming (physical machines) ---
    SERVER_LAN_URL: str = ""        # e.g. https://192.168.1.10 — used in enrollment one-liner
    SERVER_CA_PIN: str = ""         # optional sha256:<hex fp> for self-signed LAN TLS
    SELKIES_TARBALL_URL: str = (
        "https://github.com/selkies-project/selkies-gstreamer/releases/download/"
        "v1.6.2/selkies-gstreamer-portable-v1.6.2_amd64.tar.gz"
    )
    ARTIFACT_CACHE_DIR: str = "/app/data/artifacts"
    AGENT_DIR: str = "/app/agent"   # mounted from repo ./agent; dev fallback in enroll router
    ENROLL_TOKEN_TTL_HOURS: int = 24
    WORKSTATION_OFFLINE_AFTER_S: int = 90
    WORKSTATION_DEFAULT_PORT: int = 8443
    WORKSTATION_HEARTBEAT_S: int = 30
```

And after `oauth_redirect_base()` method add:

```python
    def server_lan_url(self) -> str:
        return (self.SERVER_LAN_URL or f"https://{self.DOMAIN}").rstrip("/")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (all, including pre-existing)

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(workstations): settings for LAN URL, artifacts, enrollment TTLs"
```

---

### Task 3: Schemas

**Files:**
- Modify: `backend/app/schemas.py` (append at end)

- [ ] **Step 1: Append schemas** (pure Pydantic, no test file needed — exercised by router tests in Tasks 4–7):

```python
class WorkstationOut(BaseModel):
    id: str
    name: str
    subdomain: str
    hostname: str
    lan_ip: str
    port: int
    status: str
    display_server: str
    gpu_info: dict[str, Any]
    os_info: dict[str, Any]
    agent_version: str
    stream_settings: dict[str, Any]
    all_users: bool
    last_heartbeat: str | None
    last_error: str | None
    created_at: str
    allowed_user_ids: list[str] = []


class EnrollTokenOut(BaseModel):
    token: str
    expires_at: str
    command: str


class WorkstationRegisterRequest(BaseModel):
    token: str
    hostname: str = Field(min_length=1, max_length=255)
    lan_ip: str = Field(min_length=1, max_length=64)
    display_server: str = "x11"           # x11 | wayland
    gpu_info: dict[str, Any] = {}
    os_info: dict[str, Any] = {}
    agent_version: str = ""
    port: int | None = None

    @field_validator("display_server")
    @classmethod
    def _valid_display(cls, v: str) -> str:
        if v not in ("x11", "wayland"):
            raise ValueError("display_server must be 'x11' or 'wayland'")
        return v


class WorkstationRegisterResponse(BaseModel):
    workstation_id: str
    agent_token: str
    subdomain: str
    selkies_user: str
    selkies_password: str
    port: int
    stream_settings: dict[str, Any]
    heartbeat_interval_s: int


class WorkstationHeartbeatRequest(BaseModel):
    status: str = "online"                # online | error
    lan_ip: str | None = None
    last_error: str | None = None
    health: dict[str, Any] = {}


class WorkstationHeartbeatResponse(BaseModel):
    state: str                            # ok | revoked
    stream_settings: dict[str, Any]
    heartbeat_interval_s: int


class WorkstationUpdate(BaseModel):
    name: str | None = None
    all_users: bool | None = None
    stream_settings: dict[str, Any] | None = None


class WorkstationAccessUpdate(BaseModel):
    user_ids: list[str]


class WorkstationConnectOut(BaseModel):
    url: str
```

- [ ] **Step 2: Verify import works**

Run: `.venv/bin/python -c "from app.schemas import WorkstationOut, EnrollTokenOut; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat(workstations): API schemas"
```

---

### Task 4: Workstations service helpers + admin token mint

**Files:**
- Create: `backend/app/services/workstations.py`
- Create: `backend/app/routers/workstations.py`
- Modify: `backend/app/main.py` (router registration + CSRF exemptions)
- Test: `backend/tests/test_workstation_enroll.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_workstation_enroll.py
import pytest
from sqlmodel import select

from app.models import WorkstationEnrollmentToken


@pytest.mark.asyncio
async def test_mint_enroll_token_admin_only(client):
    r = await client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_mint_enroll_token(admin_client, session):
    r = await admin_client.post("/api/workstations/enroll-tokens")
    assert r.status_code == 201
    body = r.json()
    assert len(body["token"]) > 30
    assert "curl -fsSL" in body["command"]
    assert "--token " + body["token"] in body["command"]
    assert "/api/enroll/script" in body["command"]
    rows = (await session.exec(select(WorkstationEnrollmentToken))).all()
    assert len(rows) == 1
    assert rows[0].token_hash != body["token"]  # stored hashed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_workstation_enroll.py -v`
Expected: FAIL — 404 (route not registered)

- [ ] **Step 3: Create `backend/app/services/workstations.py`**

```python
"""Helpers for physical-workstation enrollment and lifecycle."""
import hashlib
import re
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.config import Settings
from app.models import Workstation

_settings = Settings()

ENROLL_SCRIPT_PATH = "/api/enroll/script"
SELKIES_USER = "styx"


def sha256_hex(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def build_enroll_command(raw_token: str) -> str:
    base = _settings.server_lan_url()
    cmd = (f"curl -fsSL {base}{ENROLL_SCRIPT_PATH} | bash -s -- "
           f"--token {raw_token} --server {base}")
    if _settings.SERVER_CA_PIN:
        cmd += f" --ca-pin {_settings.SERVER_CA_PIN}"
    return cmd


def slugify_hostname(hostname: str) -> str:
    s = re.sub(r"[^a-z0-9-]+", "-", hostname.lower()).strip("-")[:40]
    return s or "workstation"


async def unique_subdomain(session, hostname: str) -> str:
    base = slugify_hostname(hostname)
    candidate, n = base, 2
    while True:
        existing = await session.exec(
            select(Workstation).where(Workstation.subdomain == candidate))
        if existing.first() is None:
            return candidate
        candidate = f"{base}-{n}"
        n += 1


async def mark_stale_offline(session) -> bool:
    """Flip online workstations with stale heartbeats to offline.
    Returns True if anything changed (caller refreshes routes)."""
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=_settings.WORKSTATION_OFFLINE_AFTER_S)
    result = await session.exec(
        select(Workstation).where(Workstation.status == "online"))
    changed = False
    for ws in result.all():
        hb = ws.last_heartbeat
        if hb is not None and hb.tzinfo is None:
            hb = hb.replace(tzinfo=timezone.utc)
        if hb is None or hb < cutoff:
            ws.status = "offline"
            session.add(ws)
            changed = True
    return changed
```

- [ ] **Step 4: Create `backend/app/routers/workstations.py`** (mint endpoint only; Task 7 extends this file)

```python
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import User, WorkstationEnrollmentToken
from app.schemas import EnrollTokenOut
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.workstations import build_enroll_command, sha256_hex

router = APIRouter()
_settings = Settings()


@router.post("/enroll-tokens", response_model=EnrollTokenOut, status_code=201)
async def mint_enroll_token(request: Request,
                            admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    raw = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(
        hours=_settings.ENROLL_TOKEN_TTL_HOURS)
    session.add(WorkstationEnrollmentToken(
        token_hash=sha256_hex(raw), created_by=admin.id, expires_at=expires))
    await audit_request(session, request, "workstation.enroll_token_create",
                        user_id=admin.id)
    await session.commit()
    return EnrollTokenOut(token=raw, expires_at=expires.isoformat(),
                          command=build_enroll_command(raw))
```

- [ ] **Step 5: Register router + CSRF exemptions in `backend/app/main.py`**

Change the import block (line ~18) to add:

```python
from app.routers import workstations as workstations_router
```

Replace the `_CSRF_EXEMPT` line and middleware check:

```python
_CSRF_EXEMPT = {"/api/auth/login", "/api/auth/setup"}
_CSRF_EXEMPT_PREFIXES = ("/api/enroll/", "/api/agent/")


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if (request.method in UNSAFE_METHODS
                and request.url.path not in _CSRF_EXEMPT
                and not request.url.path.startswith(_CSRF_EXEMPT_PREFIXES)):
            if not csrf_valid(request.cookies.get(CSRF_COOKIE),
                              request.headers.get(CSRF_HEADER)):
                return JSONResponse({"detail": "CSRF check failed"}, status_code=403)
        return await call_next(request)
```

After the existing `include_router` lines add:

```python
app.include_router(workstations_router.router, prefix="/api/workstations", tags=["workstations"])
```

- [ ] **Step 6: Run tests**

Run: `.venv/bin/python -m pytest tests/test_workstation_enroll.py tests/test_csrf.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/workstations.py backend/app/routers/workstations.py backend/app/main.py backend/tests/test_workstation_enroll.py
git commit -m "feat(workstations): enrollment token minting + one-liner command"
```

---

### Task 5: Public enroll router — register + script/agent file serving

**Files:**
- Create: `backend/app/routers/enroll.py`
- Modify: `backend/app/main.py` (register router)
- Modify: `docker-compose.yml` (mount agent dir)
- Test: `backend/tests/test_workstation_enroll.py` (append)

- [ ] **Step 1: Append failing tests to `backend/tests/test_workstation_enroll.py`**

```python
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from app.models import Workstation, User


async def _mint(session, admin_id: str, *, expired=False, used=False) -> str:
    raw = secrets.token_urlsafe(32)
    delta = timedelta(hours=-1) if expired else timedelta(hours=24)
    session.add(WorkstationEnrollmentToken(
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        created_by=admin_id,
        expires_at=datetime.now(timezone.utc) + delta,
        used_at=datetime.now(timezone.utc) if used else None))
    await session.commit()
    return raw


async def _admin_id(session) -> str:
    from sqlmodel import select as _select
    return (await session.exec(_select(User).where(User.role == "admin"))).first().id


@pytest.mark.asyncio
async def test_register_happy_path(admin_client, client, session):
    raw = await _mint(session, await _admin_id(session))
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "My-Desk.local", "lan_ip": "192.168.1.50",
        "display_server": "wayland", "gpu_info": {"vendor": "nvidia"},
        "os_info": {"distro": "ubuntu"}, "agent_version": "0.1.0"})
    assert r.status_code == 201
    body = r.json()
    assert body["subdomain"] == "my-desk-local"
    assert body["selkies_user"] == "styx"
    assert len(body["agent_token"]) > 30
    assert body["heartbeat_interval_s"] == 30
    ws = (await session.exec(select(Workstation))).first()
    assert ws.status == "pending"
    assert ws.agent_token_hash == hashlib.sha256(body["agent_token"].encode()).hexdigest()
    # token single-use
    r2 = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_register_rejects_expired_and_bogus(client, admin_client, session):
    raw = await _mint(session, await _admin_id(session), expired=True)
    r = await client.post("/api/enroll/register", json={
        "token": raw, "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r.status_code == 401
    r = await client.post("/api/enroll/register", json={
        "token": "bogus", "hostname": "x", "lan_ip": "1.2.3.4"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_register_subdomain_collision_appends_suffix(client, admin_client, session):
    aid = await _admin_id(session)
    for expected in ("desk", "desk-2"):
        raw = await _mint(session, aid)
        r = await client.post("/api/enroll/register", json={
            "token": raw, "hostname": "desk", "lan_ip": "192.168.1.50"})
        assert r.json()["subdomain"] == expected


@pytest.mark.asyncio
async def test_enroll_script_served(client):
    r = await client.get("/api/enroll/script")
    assert r.status_code == 200
    assert "--token" in r.text  # bash script content


@pytest.mark.asyncio
async def test_agent_py_served(client):
    r = await client.get("/api/enroll/agent.py")
    assert r.status_code == 200
    assert "def main" in r.text
```

Note: `admin_client` fixture in test args forces admin creation before `client` calls (FK for `created_by`).

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_workstation_enroll.py -v`
Expected: new tests FAIL (404)

- [ ] **Step 3: Create placeholder agent files** (real content in Tasks 11–13; serving must work now)

```bash
mkdir -p agent/tests
cat > agent/enroll.sh <<'EOF'
#!/usr/bin/env bash
# Styx workstation enrollment script — full implementation in Task 12.
# Args: --token <t> --server <url> [--ca-pin sha256:<fp>]
set -euo pipefail
echo "placeholder"
EOF
cat > agent/styx_agent.py <<'EOF'
"""Styx workstation agent — full implementation in Task 11."""
def main() -> int:
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
EOF
cat > agent/uninstall.sh <<'EOF'
#!/usr/bin/env bash
# Styx agent uninstall — full implementation in Task 13.
set -euo pipefail
echo "placeholder"
EOF
chmod +x agent/enroll.sh agent/uninstall.sh
```

- [ ] **Step 4: Create `backend/app/routers/enroll.py`**

```python
"""Public enrollment endpoints — token-gated or static; no cookie auth.

CSRF-exempt by path prefix (see main.py): agents have no cookies.
"""
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, PlainTextResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Workstation, WorkstationEnrollmentToken
from app.schemas import WorkstationRegisterRequest, WorkstationRegisterResponse
from app.security.crypto import encrypt_secret
from app.services.audit import audit_request
from app.services.workstations import (
    SELKIES_USER, sha256_hex, unique_subdomain,
)

router = APIRouter()
_settings = Settings()


def _agent_dir() -> Path:
    p = Path(_settings.AGENT_DIR)
    if p.is_dir():
        return p
    # Dev fallback: repo layout backend/app/routers/ -> repo root /agent
    return Path(__file__).resolve().parents[3] / "agent"


def _serve(filename: str) -> PlainTextResponse:
    path = _agent_dir() / filename
    if not path.is_file():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            f"Agent file {filename} missing on server — "
                            f"check the ./agent mount (AGENT_DIR).")
    return PlainTextResponse(path.read_text())


@router.get("/script")
async def enroll_script():
    return _serve("enroll.sh")


@router.get("/agent.py")
async def agent_py():
    return _serve("styx_agent.py")


@router.get("/uninstall")
async def uninstall_script():
    return _serve("uninstall.sh")


@router.get("/artifacts/selkies.tar.gz")
async def selkies_tarball():
    from app.services.artifacts import ensure_selkies_tarball
    try:
        path = await ensure_selkies_tarball()
    except Exception as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Selkies tarball unavailable: could not download from "
            f"{_settings.SELKIES_TARBALL_URL} ({e.__class__.__name__}). "
            "Fix the URL (SELKIES_TARBALL_URL) or pre-place the file at "
            f"{_settings.ARTIFACT_CACHE_DIR}/selkies.tar.gz")
    return FileResponse(path, media_type="application/gzip",
                        filename="selkies.tar.gz")


@router.post("/register", response_model=WorkstationRegisterResponse,
             status_code=201)
async def register(body: WorkstationRegisterRequest, request: Request,
                   session: AsyncSession = Depends(get_session)):
    now = datetime.now(timezone.utc)
    result = await session.exec(select(WorkstationEnrollmentToken).where(
        WorkstationEnrollmentToken.token_hash == sha256_hex(body.token)))
    tok = result.first()
    expires = tok.expires_at if tok else None
    if expires is not None and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if tok is None or tok.used_at is not None or (expires and expires < now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Invalid, expired, or already-used enrollment token")
    tok.used_at = now
    session.add(tok)

    agent_token = secrets.token_urlsafe(32)
    selkies_password = secrets.token_urlsafe(16)
    subdomain = await unique_subdomain(session, body.hostname)
    ws = Workstation(
        name=body.hostname, subdomain=subdomain, hostname=body.hostname,
        lan_ip=body.lan_ip, port=body.port or _settings.WORKSTATION_DEFAULT_PORT,
        display_server=body.display_server, gpu_info=body.gpu_info,
        os_info=body.os_info, agent_version=body.agent_version,
        agent_token_hash=sha256_hex(agent_token),
        selkies_password_enc=encrypt_secret(selkies_password),
        created_by=tok.created_by,
    )
    session.add(ws)
    await audit_request(session, request, "workstation.register",
                        resource=ws.id,
                        detail={"hostname": body.hostname, "lan_ip": body.lan_ip,
                                "display_server": body.display_server})
    await session.commit()
    return WorkstationRegisterResponse(
        workstation_id=ws.id, agent_token=agent_token, subdomain=subdomain,
        selkies_user=SELKIES_USER, selkies_password=selkies_password,
        port=ws.port, stream_settings=ws.stream_settings,
        heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)
```

- [ ] **Step 5: Register router in `backend/app/main.py`**

Add import:

```python
from app.routers import enroll as enroll_router
```

Add with the other `include_router` calls:

```python
app.include_router(enroll_router.router, prefix="/api/enroll", tags=["enroll"])
```

- [ ] **Step 6: Create stub `backend/app/services/artifacts.py`** (full version Task 10; import must resolve)

```python
"""Selkies tarball download cache. Full implementation in Task 10."""
from pathlib import Path

from app.config import Settings

_settings = Settings()


async def ensure_selkies_tarball() -> Path:
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / "selkies.tar.gz"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    raise FileNotFoundError(dest)
```

- [ ] **Step 7: Mount agent dir in `docker-compose.yml`.** In the `backend` service `volumes:` list add:

```yaml
      - ./agent:/app/agent:ro
```

- [ ] **Step 8: Run tests**

Run: `.venv/bin/python -m pytest tests/test_workstation_enroll.py -v`
Expected: all PASS

- [ ] **Step 9: Commit**

```bash
git add backend/app/routers/enroll.py backend/app/services/artifacts.py backend/app/main.py backend/tests/test_workstation_enroll.py agent/ docker-compose.yml
git commit -m "feat(workstations): public register endpoint + agent file serving"
```

---

### Task 6: Agent API — heartbeat + deregister

**Files:**
- Create: `backend/app/routers/agent.py`
- Modify: `backend/app/main.py` (register router)
- Test: `backend/tests/test_workstation_agent_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_workstation_agent_api.py
import hashlib
import pytest
from sqlmodel import select

from app.models import User, Workstation


async def _make_ws(session, *, status="pending", token="agent-tok-1") -> Workstation:
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    if admin is None:
        from app.security.passwords import hash_password
        admin = User(username="adm-x", password_hash=hash_password("x"), role="admin")
        session.add(admin)
        await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status=status,
                     agent_token_hash=hashlib.sha256(token.encode()).hexdigest(),
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws


def _auth(token="agent-tok-1"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_heartbeat_requires_token(client, session):
    await _make_ws(session)
    assert (await client.post("/api/agent/heartbeat", json={})).status_code == 401
    assert (await client.post("/api/agent/heartbeat", json={},
                              headers=_auth("wrong"))).status_code == 401


@pytest.mark.asyncio
async def test_heartbeat_marks_online_and_returns_settings(client, session):
    ws = await _make_ws(session)
    r = await client.post("/api/agent/heartbeat",
                          json={"status": "online", "lan_ip": "192.168.1.99"},
                          headers=_auth())
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "ok"
    assert body["stream_settings"]["framerate"] == 60
    await session.refresh(ws)
    assert ws.status == "online"
    assert ws.lan_ip == "192.168.1.99"
    assert ws.last_heartbeat is not None


@pytest.mark.asyncio
async def test_heartbeat_revoked_workstation(client, session):
    await _make_ws(session, status="revoked")
    r = await client.post("/api/agent/heartbeat", json={}, headers=_auth())
    assert r.status_code == 200
    assert r.json()["state"] == "revoked"


@pytest.mark.asyncio
async def test_deregister_deletes_row(client, session):
    ws = await _make_ws(session)
    r = await client.post("/api/agent/deregister", json={}, headers=_auth())
    assert r.status_code == 200
    assert (await session.get(Workstation, ws.id)) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_workstation_agent_api.py -v`
Expected: FAIL (404)

- [ ] **Step 3: Create `backend/app/routers/agent.py`**

```python
"""Agent-facing endpoints. Auth: per-workstation bearer token (hashed at rest).

CSRF-exempt by path prefix (see main.py) — agents are header-authenticated,
no cookies, so cross-site request forgery does not apply.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlmodel import select, delete
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import Workstation, WorkstationAccess
from app.schemas import WorkstationHeartbeatRequest, WorkstationHeartbeatResponse
from app.services.audit import audit_request
from app.services.workstations import sha256_hex

router = APIRouter()
_settings = Settings()


async def get_agent_workstation(
        request: Request,
        session: AsyncSession = Depends(get_session)) -> Workstation:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Agent token required")
    token_hash = sha256_hex(auth[7:].strip())
    result = await session.exec(select(Workstation).where(
        Workstation.agent_token_hash == token_hash))
    ws = result.first()
    if ws is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown agent token")
    return ws


@router.post("/heartbeat", response_model=WorkstationHeartbeatResponse)
async def heartbeat(body: WorkstationHeartbeatRequest,
                    ws: Workstation = Depends(get_agent_workstation),
                    session: AsyncSession = Depends(get_session)):
    if ws.status == "revoked":
        return WorkstationHeartbeatResponse(
            state="revoked", stream_settings={},
            heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)
    routes_dirty = ws.status != "online" or bool(body.lan_ip and body.lan_ip != ws.lan_ip)
    ws.status = "online"
    if body.lan_ip:
        ws.lan_ip = body.lan_ip
    ws.last_heartbeat = datetime.now(timezone.utc)
    ws.last_error = body.last_error
    session.add(ws)
    await session.commit()
    if routes_dirty:
        from app.services.route_writer import refresh_routes_from_db
        await refresh_routes_from_db(session)
    return WorkstationHeartbeatResponse(
        state="ok", stream_settings=ws.stream_settings,
        heartbeat_interval_s=_settings.WORKSTATION_HEARTBEAT_S)


@router.post("/deregister")
async def deregister(request: Request,
                     ws: Workstation = Depends(get_agent_workstation),
                     session: AsyncSession = Depends(get_session)):
    await session.exec(delete(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws.id))
    await audit_request(session, request, "workstation.deregister",
                        resource=ws.id, detail={"hostname": ws.hostname})
    await session.delete(ws)
    await session.commit()
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)
    return {"ok": True}
```

- [ ] **Step 4: Register in `backend/app/main.py`**

```python
from app.routers import agent as agent_router
```

```python
app.include_router(agent_router.router, prefix="/api/agent", tags=["agent"])
```

- [ ] **Step 5: Run tests**

Run: `.venv/bin/python -m pytest tests/test_workstation_agent_api.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/agent.py backend/app/main.py backend/tests/test_workstation_agent_api.py
git commit -m "feat(workstations): agent heartbeat + deregister endpoints"
```

---

### Task 7: Admin CRUD, user listing, connect URL

**Files:**
- Modify: `backend/app/routers/workstations.py`
- Test: `backend/tests/test_workstation_admin_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_workstation_admin_api.py
import pytest
from sqlmodel import select

from app.models import User, Workstation, WorkstationAccess
from app.security.crypto import encrypt_secret
from app.security.passwords import hash_password


async def _seed(session):
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    user = User(username="carol", password_hash=hash_password("x"), role="user")
    session.add(user)
    await session.commit()
    ws = Workstation(name="desk", subdomain="desk", hostname="desk",
                     lan_ip="192.168.1.50", status="online",
                     selkies_password_enc=encrypt_secret("pw123"),
                     created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)
    return ws, user


@pytest.mark.asyncio
async def test_list_admin_only(admin_client, client, session):
    await _seed(session)
    assert (await client.get("/api/workstations")).status_code == 401
    r = await admin_client.get("/api/workstations")
    assert r.status_code == 200
    assert r.json()[0]["subdomain"] == "desk"


@pytest.mark.asyncio
async def test_patch_settings_and_access(admin_client, session):
    ws, user = await _seed(session)
    r = await admin_client.patch(f"/api/workstations/{ws.id}", json={
        "name": "Gaming rig", "stream_settings": {"encoder": "nvh264enc",
                                                  "framerate": 120,
                                                  "bitrate_kbps": 40000}})
    assert r.status_code == 200
    assert r.json()["stream_settings"]["framerate"] == 120
    r = await admin_client.put(f"/api/workstations/{ws.id}/access",
                               json={"user_ids": [user.id]})
    assert r.status_code == 200
    assert r.json()["allowed_user_ids"] == [user.id]


@pytest.mark.asyncio
async def test_delete_revokes_then_purges(admin_client, session):
    ws, _ = await _seed(session)
    r = await admin_client.delete(f"/api/workstations/{ws.id}")
    assert r.status_code == 200
    await session.refresh(ws)
    assert ws.status == "revoked"
    r = await admin_client.delete(f"/api/workstations/{ws.id}?purge=true")
    assert r.status_code == 200
    assert (await session.get(Workstation, ws.id)) is None


@pytest.mark.asyncio
async def test_mine_and_connect_respect_access(admin_client, client, session):
    ws, user = await _seed(session)
    # login as carol
    await client.get("/api/auth/csrf")
    login = await client.post("/api/auth/login",
                              json={"username": "carol", "password": "x"})
    assert login.status_code == 200
    csrf = client.cookies.get("csrf_token")
    client.headers["X-CSRF-Token"] = csrf or ""

    r = await client.get("/api/workstations/mine")
    assert r.status_code == 200 and r.json() == []
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 403

    session.add(WorkstationAccess(workstation_id=ws.id, user_id=user.id))
    await session.commit()
    r = await client.get("/api/workstations/mine")
    assert [w["id"] for w in r.json()] == [ws.id]
    r = await client.get(f"/api/workstations/{ws.id}/connect")
    assert r.status_code == 200
    assert "/w/desk/" in r.json()["url"]
    assert "password=pw123" in r.json()["url"]
```

Note: carol's password is `"x"` hashed directly — login flow works because `hash_password`/`verify` pair is symmetric; check `tests/test_auth_router.py` for the established login-in-test pattern and copy it if it differs (CSRF bootstrap via `GET /api/auth/csrf` then header). Adjust the login block to match the existing pattern if needed — the assertions stay the same.

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -v`
Expected: FAIL (404 / 405)

- [ ] **Step 3: Extend `backend/app/routers/workstations.py`.** Add imports at top:

```python
from fastapi import HTTPException, status
from sqlmodel import select, delete

from app.models import Workstation, WorkstationAccess
from app.schemas import (
    WorkstationAccessUpdate, WorkstationConnectOut, WorkstationOut,
    WorkstationUpdate,
)
from app.security.crypto import decrypt_secret
from app.security.deps import get_current_user
from app.services.workstations import SELKIES_USER
```

Then append endpoints:

```python
def _out(ws: Workstation, allowed: list[str]) -> WorkstationOut:
    return WorkstationOut(
        id=ws.id, name=ws.name, subdomain=ws.subdomain, hostname=ws.hostname,
        lan_ip=ws.lan_ip, port=ws.port, status=ws.status,
        display_server=ws.display_server, gpu_info=ws.gpu_info,
        os_info=ws.os_info, agent_version=ws.agent_version,
        stream_settings=ws.stream_settings, all_users=ws.all_users,
        last_heartbeat=ws.last_heartbeat.isoformat() if ws.last_heartbeat else None,
        last_error=ws.last_error, created_at=ws.created_at.isoformat(),
        allowed_user_ids=allowed)


async def _allowed_ids(session, ws_id: str) -> list[str]:
    rows = await session.exec(select(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws_id))
    return [a.user_id for a in rows.all()]


async def _get_or_404(session, ws_id: str) -> Workstation:
    ws = await session.get(Workstation, ws_id)
    if ws is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Workstation not found")
    return ws


@router.get("", response_model=list[WorkstationOut])
async def list_workstations(admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation))).all()
    return [_out(ws, await _allowed_ids(session, ws.id)) for ws in rows]


@router.get("/mine", response_model=list[WorkstationOut])
async def my_workstations(user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation).where(
        Workstation.status != "revoked"))).all()
    out = []
    for ws in rows:
        allowed = await _allowed_ids(session, ws.id)
        if user.role == "admin" or ws.all_users or user.id in allowed:
            out.append(_out(ws, []))
    return out


@router.get("/{ws_id}/connect", response_model=WorkstationConnectOut)
async def connect_url(ws_id: str, user: User = Depends(get_current_user),
                      session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    allowed = await _allowed_ids(session, ws.id)
    if not (user.role == "admin" or ws.all_users or user.id in allowed):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this workstation")
    if ws.status != "online":
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"Workstation is {ws.status}, not online")
    password = decrypt_secret(ws.selkies_password_enc)
    url = (f"https://{_settings.DOMAIN}/w/{ws.subdomain}/"
           f"?username={SELKIES_USER}&password={password}")
    return WorkstationConnectOut(url=url)


@router.patch("/{ws_id}", response_model=WorkstationOut)
async def update_workstation(ws_id: str, body: WorkstationUpdate,
                             request: Request,
                             admin: User = Depends(require_admin),
                             session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    if body.name is not None:
        ws.name = body.name
    if body.all_users is not None:
        ws.all_users = body.all_users
    if body.stream_settings is not None:
        ws.stream_settings = body.stream_settings
    session.add(ws)
    await audit_request(session, request, "workstation.update",
                        user_id=admin.id, resource=ws.id)
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


@router.put("/{ws_id}/access", response_model=WorkstationOut)
async def set_access(ws_id: str, body: WorkstationAccessUpdate,
                     request: Request,
                     admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    await session.exec(delete(WorkstationAccess).where(
        WorkstationAccess.workstation_id == ws.id))
    for uid in set(body.user_ids):
        session.add(WorkstationAccess(workstation_id=ws.id, user_id=uid))
    await audit_request(session, request, "workstation.access_change",
                        user_id=admin.id, resource=ws.id,
                        detail={"user_ids": body.user_ids})
    await session.commit()
    return _out(ws, await _allowed_ids(session, ws.id))


@router.delete("/{ws_id}")
async def delete_workstation(ws_id: str, request: Request, purge: bool = False,
                             admin: User = Depends(require_admin),
                             session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    if purge:
        await session.exec(delete(WorkstationAccess).where(
            WorkstationAccess.workstation_id == ws.id))
        await audit_request(session, request, "workstation.purge",
                            user_id=admin.id, resource=ws.id)
        await session.delete(ws)
    else:
        ws.status = "revoked"
        session.add(ws)
        await audit_request(session, request, "workstation.revoke",
                            user_id=admin.id, resource=ws.id)
    await session.commit()
    from app.services.route_writer import refresh_routes_from_db
    await refresh_routes_from_db(session)
    return {"ok": True}
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -v`
Expected: all PASS

- [ ] **Step 5: Run full backend suite + lint**

Run: `.venv/bin/python -m pytest --tb=short && .venv/bin/python -m ruff check app/ tests/`
Expected: all PASS, no lint errors

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/workstations.py backend/tests/test_workstation_admin_api.py
git commit -m "feat(workstations): admin CRUD, per-user access, connect URL"
```

---

### Task 8: Traefik routes for workstations

**Files:**
- Modify: `backend/app/services/route_writer.py`
- Test: `backend/tests/test_route_writer_workstations.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_route_writer_workstations.py
from app.services.route_writer import build_routes_config


def _ws(**kw):
    base = {"id": "ws1", "subdomain": "desk", "lan_ip": "192.168.1.50",
            "port": 8443, "protocol": "http"}
    base.update(kw)
    return base


def test_workstation_route_emitted():
    cfg = build_routes_config([], "example.com", "tunnel", workstations=[_ws()])
    r = cfg["http"]["routers"]["ws-ws1"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/w/desk`)"
    assert "strip-w-desk" in r["middlewares"]
    assert cfg["http"]["middlewares"]["strip-w-desk"] == {
        "stripPrefix": {"prefixes": ["/w/desk"]}}
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["servers"] == [{"url": "http://192.168.1.50:8443"}]


def test_workstation_https_gets_skip_verify_transport():
    cfg = build_routes_config([], "example.com", "tunnel",
                              workstations=[_ws(protocol="https")])
    svc = cfg["http"]["services"]["ws-ws1"]["loadBalancer"]
    assert svc["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {
        "insecureSkipVerify": True}


def test_no_workstations_is_default():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert not any(k.startswith("ws-") for k in cfg["http"]["routers"])
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_route_writer_workstations.py -v`
Expected: FAIL — unexpected keyword `workstations`

- [ ] **Step 3: Modify `route_writer.py`.**

Change signature:

```python
def build_routes_config(instances: list[dict], domain: str,
                        deploy_mode: str = "tunnel",
                        workstations: list[dict] | None = None) -> dict:
```

After the instance loop (before `config["http"]["middlewares"] = middlewares`), add:

```python
    for ws in workstations or []:
        sub = ws["subdomain"]
        strip_mw = f"strip-w-{sub}"
        middlewares[strip_mw] = {"stripPrefix": {"prefixes": [f"/w/{sub}"]}}
        rid = f"ws-{ws['id']}"
        config["http"]["routers"][rid] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/w/{sub}`)",
            "middlewares": ["instance-unavailable-errors", strip_mw],
            "service": rid,
            "priority": 50,
            **_router_transport(deploy_mode, domain),
        }
        protocol = ws.get("protocol", "http")
        svc: dict = {"servers": [{"url": f"{protocol}://{ws['lan_ip']}:{ws['port']}"}]}
        if protocol == "https":
            svc["serversTransport"] = "selkies-transport"
            has_https = True
        config["http"]["services"][rid] = {"loadBalancer": svc}
```

Update `write_routes`:

```python
def write_routes(instances: list[dict], domain: str | None = None,
                 workstations: list[dict] | None = None):
```

and pass through: `config = build_routes_config(instances, domain, _settings.DEPLOY_MODE, workstations)`.

Update `refresh_routes_from_db` — after building `data`, add:

```python
    from app.models import Workstation
    ws_result = await session.exec(
        select(Workstation).where(Workstation.status == "online"))
    ws_data = [{
        "id": w.id, "subdomain": w.subdomain, "lan_ip": w.lan_ip,
        "port": w.port, "protocol": w.protocol,
    } for w in ws_result.all()]
    write_routes(data, workstations=ws_data)
```

(replacing the existing `write_routes(data)` call).

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_route_writer_workstations.py tests/test_route_writer.py -v`
Expected: all PASS (existing route-writer tests must not break)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/route_writer.py backend/tests/test_route_writer_workstations.py
git commit -m "feat(workstations): Traefik routes to workstation LAN IPs under /w/"
```

---

### Task 9: Offline detection in monitor loop

**Files:**
- Modify: `backend/app/main.py` (`_session_monitor_loop`)
- Test: `backend/tests/test_workstation_monitor.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_workstation_monitor.py
import pytest
from datetime import datetime, timedelta, timezone

from app.models import User, Workstation
from app.security.passwords import hash_password
from app.services.workstations import mark_stale_offline


async def _ws(session, *, hb_age_s: int | None, status="online"):
    admin = User(username=f"a{hb_age_s}", password_hash=hash_password("x"), role="admin")
    session.add(admin)
    await session.commit()
    hb = (datetime.now(timezone.utc) - timedelta(seconds=hb_age_s)
          if hb_age_s is not None else None)
    ws = Workstation(name="w", subdomain=f"w{hb_age_s}", status=status,
                     last_heartbeat=hb, created_by=admin.id)
    session.add(ws)
    await session.commit()
    return ws


@pytest.mark.asyncio
async def test_stale_heartbeat_goes_offline(session):
    ws = await _ws(session, hb_age_s=300)
    assert await mark_stale_offline(session) is True
    assert ws.status == "offline"


@pytest.mark.asyncio
async def test_fresh_heartbeat_stays_online(session):
    ws = await _ws(session, hb_age_s=10)
    assert await mark_stale_offline(session) is False
    assert ws.status == "online"


@pytest.mark.asyncio
async def test_missing_heartbeat_goes_offline(session):
    ws = await _ws(session, hb_age_s=None)
    assert await mark_stale_offline(session) is True
    assert ws.status == "offline"
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/python -m pytest tests/test_workstation_monitor.py -v`
Expected: PASS already (`mark_stale_offline` exists from Task 4). If any FAIL, fix `mark_stale_offline`.

- [ ] **Step 3: Wire into monitor loop.** In `backend/app/main.py`, `_session_monitor_loop`, change the loop body:

```python
        try:
            async with async_session() as session:
                changed = await _run_monitor_pass(session, monitor, docker)
                from app.services.workstations import mark_stale_offline
                ws_changed = await mark_stale_offline(session)
                await session.commit()
                if changed or ws_changed:
                    await refresh_routes_from_db(session)
        except Exception:
            pass
```

- [ ] **Step 4: Run full suite**

Run: `.venv/bin/python -m pytest --tb=short`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_workstation_monitor.py
git commit -m "feat(workstations): heartbeat staleness marks workstations offline"
```

---

### Task 10: Selkies tarball artifact cache

**Files:**
- Modify: `backend/app/services/artifacts.py` (replace stub)
- Test: `backend/tests/test_artifacts.py`

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_artifacts.py
import pytest

from app.services import artifacts


@pytest.mark.asyncio
async def test_cached_file_served_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))
    (tmp_path / "selkies.tar.gz").write_bytes(b"cached-bytes")
    path = await artifacts.ensure_selkies_tarball()
    assert path.read_bytes() == b"cached-bytes"


@pytest.mark.asyncio
async def test_downloads_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def fake_download(url, dest):
        dest.write_bytes(b"downloaded")
    monkeypatch.setattr(artifacts, "_download", fake_download)
    path = await artifacts.ensure_selkies_tarball()
    assert path.read_bytes() == b"downloaded"


@pytest.mark.asyncio
async def test_download_failure_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(artifacts._settings, "ARTIFACT_CACHE_DIR", str(tmp_path))

    async def boom(url, dest):
        raise ConnectionError("no route")
    monkeypatch.setattr(artifacts, "_download", boom)
    with pytest.raises(ConnectionError):
        await artifacts.ensure_selkies_tarball()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: `test_downloads_when_missing` FAILs (`_download` missing)

- [ ] **Step 3: Replace `backend/app/services/artifacts.py`**

```python
"""Selkies tarball download cache.

The enrollment script fetches the Selkies portable tarball from this server,
not from the internet — workstations only need LAN reachability. The file is
downloaded once from SELKIES_TARBALL_URL and cached. Pre-placing the file at
{ARTIFACT_CACHE_DIR}/selkies.tar.gz also works (air-gapped installs).
"""
import asyncio
from pathlib import Path

import httpx

from app.config import Settings

_settings = Settings()
_lock = asyncio.Lock()


async def _download(url: str, dest: Path) -> None:
    async with httpx.AsyncClient(timeout=600, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)


async def ensure_selkies_tarball() -> Path:
    dest = Path(_settings.ARTIFACT_CACHE_DIR) / "selkies.tar.gz"
    if dest.is_file() and dest.stat().st_size > 0:
        return dest
    async with _lock:
        if dest.is_file() and dest.stat().st_size > 0:  # re-check under lock
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        try:
            await _download(_settings.SELKIES_TARBALL_URL, tmp)
            tmp.rename(dest)
        finally:
            tmp.unlink(missing_ok=True)
    return dest
```

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_artifacts.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/artifacts.py backend/tests/test_artifacts.py
git commit -m "feat(workstations): cache + serve Selkies tarball for agents"
```

---

### Task 11: Agent daemon (`styx_agent.py`)

**Files:**
- Modify: `agent/styx_agent.py` (replace placeholder)
- Create: `agent/tests/__init__.py` (empty), `agent/tests/test_styx_agent.py`

Stdlib only — no pip installs on workstations. Subcommands: `run`, `status`, `doctor`, `uninstall`.

- [ ] **Step 1: Write the failing tests**

```python
# agent/tests/test_styx_agent.py
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import styx_agent  # noqa: E402


def _cfg(tmp_path, **kw):
    cfg = {
        "server": "https://192.168.1.10", "agent_token": "tok",
        "workstation_id": "ws1", "port": 8443,
        "selkies_user": "styx", "selkies_password": "pw",
        "display_server": "x11",
        "stream_settings": {"encoder": "x264enc", "framerate": 60,
                            "bitrate_kbps": 16000},
        "selkies_dir": str(tmp_path / "selkies"),
        "ca_pin": "",
        "server_cert": "",
    }
    cfg.update(kw)
    p = tmp_path / "config.json"
    p.write_text(json.dumps(cfg))
    return p, cfg


def test_load_config(tmp_path):
    p, cfg = _cfg(tmp_path)
    loaded = styx_agent.load_config(p)
    assert loaded["port"] == 8443


def test_build_selkies_cmd_x11(tmp_path):
    _, cfg = _cfg(tmp_path)
    cmd, env = styx_agent.build_selkies_cmd(cfg)
    assert cmd[0].endswith("selkies-gstreamer-run")
    assert env["SELKIES_PORT"] == "8443"
    assert env["SELKIES_ENCODER"] == "x264enc"
    assert env["SELKIES_FRAMERATE"] == "60"
    assert env["SELKIES_ENABLE_BASIC_AUTH"] == "true"
    assert env["SELKIES_BASIC_AUTH_PASSWORD"] == "pw"
    assert env["DISPLAY"]  # attaches to a display


def test_build_selkies_cmd_wayland_sets_pixelflux(tmp_path):
    _, cfg = _cfg(tmp_path, display_server="wayland")
    cmd, env = styx_agent.build_selkies_cmd(cfg)
    assert env["PIXELFLUX_WAYLAND"] == "true"


def test_encoder_auto_resolves(monkeypatch, tmp_path):
    _, cfg = _cfg(tmp_path)
    cfg["stream_settings"]["encoder"] = "auto"
    monkeypatch.setattr(styx_agent, "detect_encoder", lambda: "nvh264enc")
    _, env = styx_agent.build_selkies_cmd(cfg)
    assert env["SELKIES_ENCODER"] == "nvh264enc"
```

- [ ] **Step 2: Run to verify failure**

Run (from repo root): `backend/.venv/bin/python -m pytest agent/tests -v`
Expected: FAIL — missing functions

- [ ] **Step 3: Replace `agent/styx_agent.py`**

```python
#!/usr/bin/env python3
"""Styx workstation agent — supervises Selkies and heartbeats to the portal.

Stdlib only. Installed by enroll.sh to ~/.local/share/styx-agent/.
Subcommands: run | status | doctor | uninstall
"""
import json
import os
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path

AGENT_VERSION = "0.1.0"
HOME = Path.home()
INSTALL_DIR = HOME / ".local/share/styx-agent"
CONFIG_PATH = HOME / ".config/styx-agent/config.json"
LOG_DIR = INSTALL_DIR / "logs"
STATE_PATH = INSTALL_DIR / "state.json"   # last heartbeat result, for status/doctor


def load_config(path: Path = CONFIG_PATH) -> dict:
    return json.loads(Path(path).read_text())


# --- TLS pinning -----------------------------------------------------------
# Enrollment verified the server certificate's SHA256 fingerprint against the
# pin embedded in the minted command and saved the cert to server_cert (PEM).
# We use that cert as the ONLY trusted CA — full chain verification against
# the pinned cert, never an unverified connection. Hostname check is off
# because self-signed LAN certs rarely carry the LAN IP in their SAN; trust
# comes from the pin, not the name.
def _ssl_context(cfg: dict) -> ssl.SSLContext:
    cert_file = cfg.get("server_cert", "")
    if cert_file and Path(cert_file).is_file():
        ctx = ssl.create_default_context(cafile=cert_file)
        ctx.check_hostname = False
        return ctx
    return ssl.create_default_context()


def check_pin(cert_file: str, ca_pin: str) -> bool:
    """Doctor check: pinned cert file still matches the fingerprint."""
    if not ca_pin or not cert_file:
        return True
    expected = ca_pin.split(":", 1)[1].replace(":", "").lower()
    pem = Path(cert_file).read_text()
    der = ssl.PEM_cert_to_DER_cert(pem)
    return sha256(der).hexdigest() == expected


def api(cfg: dict, path: str, payload: dict | None = None) -> dict:
    url = cfg["server"].rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method="POST" if data is not None else "GET",
        headers={"Authorization": f"Bearer {cfg['agent_token']}",
                 "Content-Type": "application/json"})
    ctx = _ssl_context(cfg) if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
        return json.loads(resp.read().decode() or "{}")


# --- Selkies process -------------------------------------------------------
def detect_encoder() -> str:
    if shutil.which("nvidia-smi") and subprocess.run(
            ["nvidia-smi", "-L"], capture_output=True).returncode == 0:
        return "nvh264enc"
    if shutil.which("vainfo") and subprocess.run(
            ["vainfo"], capture_output=True).returncode == 0:
        return "vah264enc"
    return "x264enc"


def build_selkies_cmd(cfg: dict) -> tuple[list[str], dict]:
    s = cfg["stream_settings"]
    encoder = s.get("encoder", "auto")
    if encoder == "auto":
        encoder = detect_encoder()
    env = os.environ.copy()
    env.update({
        "SELKIES_ADDR": "0.0.0.0",
        "SELKIES_PORT": str(cfg["port"]),
        "SELKIES_ENCODER": encoder,
        "SELKIES_FRAMERATE": str(s.get("framerate", 60)),
        "SELKIES_VIDEO_BITRATE": str(s.get("bitrate_kbps", 16000)),
        "SELKIES_ENABLE_BASIC_AUTH": "true",
        "SELKIES_BASIC_AUTH_USER": cfg["selkies_user"],
        "SELKIES_BASIC_AUTH_PASSWORD": cfg["selkies_password"],
        "SELKIES_ENABLE_RESIZE": "false",
        "SELKIES_AUDIO_BITRATE": "128000",
    })
    if cfg["display_server"] == "wayland":
        # Own-compositor takeover: pixelflux starts a Smithay compositor.
        env["PIXELFLUX_WAYLAND"] = "true"
    else:
        env.setdefault("DISPLAY", ":0")
    launcher = Path(cfg["selkies_dir"]) / "selkies-gstreamer-run"
    return [str(launcher)], env


def _write_state(d: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(d))


def run(cfg: dict) -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    selkies_log = open(LOG_DIR / "selkies.log", "ab", buffering=0)
    cmd, env = build_selkies_cmd(cfg)
    proc: subprocess.Popen | None = None
    interval = 30
    backoff = 2
    stopping = False

    def _stop(*_):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not stopping:
        if proc is None or proc.poll() is not None:
            if proc is not None:
                print(f"selkies exited rc={proc.returncode}; restarting in {backoff}s",
                      flush=True)
                time.sleep(min(backoff, 60))
                backoff *= 2
            proc = subprocess.Popen(cmd, env=env, stdout=selkies_log,
                                    stderr=selkies_log)
        err = None
        try:
            hb = api(cfg, "/api/agent/heartbeat", {
                "status": "online",
                "last_error": None if proc.poll() is None
                              else f"selkies exited rc={proc.returncode}",
            })
            _write_state({"ts": time.time(), "ok": True, "state": hb["state"]})
            if hb["state"] == "revoked":
                print("Revoked by server. Stopping. To remove this agent run:\n"
                      f"  python3 {INSTALL_DIR / 'styx_agent.py'} uninstall",
                      flush=True)
                break
            if hb["stream_settings"] != cfg["stream_settings"]:
                cfg["stream_settings"] = hb["stream_settings"]
                CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
                cmd, env = build_selkies_cmd(cfg)
                proc.terminate()
                proc.wait(timeout=10)
                proc = None
                continue
            interval = hb.get("heartbeat_interval_s", 30)
            backoff = 2
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            err = str(e)
            _write_state({"ts": time.time(), "ok": False, "error": err})
            print(f"heartbeat failed: {err}", flush=True)
        time.sleep(interval)

    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


# --- Diagnostics -----------------------------------------------------------
def _check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'OK' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    return ok


def doctor(cfg: dict) -> int:
    print("styx-agent doctor:")
    ok = True
    ok &= _check("config readable", True, str(CONFIG_PATH))
    launcher = Path(cfg["selkies_dir"]) / "selkies-gstreamer-run"
    ok &= _check("selkies installed", launcher.exists(), str(launcher))
    svc = subprocess.run(["systemctl", "--user", "is-active", "styx-agent"],
                         capture_output=True, text=True)
    ok &= _check("service active", svc.stdout.strip() == "active",
                 svc.stdout.strip())
    port_busy = socket.socket().connect_ex(("127.0.0.1", cfg["port"])) == 0
    ok &= _check(f"selkies listening :{cfg['port']}", port_busy,
                 "" if port_busy else "nothing listening — see logs/selkies.log")
    if cfg.get("ca_pin"):
        ok &= _check("TLS pin matches",
                     check_pin(cfg.get("server_cert", ""), cfg["ca_pin"]))
    try:
        api(cfg, "/api/agent/heartbeat", {"status": "online"})
        ok &= _check("server reachable + token valid", True)
    except Exception as e:
        ok &= _check("server reachable + token valid", False, str(e))
    enc = cfg["stream_settings"].get("encoder", "auto")
    ok &= _check("encoder", True,
                 detect_encoder() if enc == "auto" else enc)
    print("All checks passed." if ok else
          f"Some checks failed. Logs: {LOG_DIR}")
    return 0 if ok else 1


def status(cfg: dict) -> int:
    try:
        st = json.loads(STATE_PATH.read_text())
        age = int(time.time() - st["ts"])
        print(f"last heartbeat {age}s ago — "
              f"{'ok' if st.get('ok') else 'FAILED: ' + st.get('error', '?')}")
        return 0 if st.get("ok") else 1
    except FileNotFoundError:
        print("no heartbeat recorded yet — is the service running? "
              "(systemctl --user status styx-agent)")
        return 1


def uninstall(cfg: dict | None) -> int:
    subprocess.run(["systemctl", "--user", "disable", "--now", "styx-agent"],
                   capture_output=True)
    if cfg:
        try:
            api(cfg, "/api/agent/deregister", {})
            print("Deregistered from server.")
        except Exception as e:
            print(f"Could not deregister (server unreachable?): {e} — "
                  "remove it from the admin Workstations panel.")
    unit = HOME / ".config/systemd/user/styx-agent.service"
    unit.unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    CONFIG_PATH.unlink(missing_ok=True)
    print("Styx agent removed.")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    try:
        cfg = load_config()
    except FileNotFoundError:
        cfg = None
    if cmd == "uninstall":
        return uninstall(cfg)
    if cfg is None:
        print(f"Config missing at {CONFIG_PATH} — re-run enrollment.")
        return 1
    if cmd == "run":
        return run(cfg)
    if cmd == "doctor":
        return doctor(cfg)
    if cmd == "status":
        return status(cfg)
    print(f"Unknown command: {cmd} (expected run|status|doctor|uninstall)")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `backend/.venv/bin/python -m pytest agent/tests -v` (repo root)
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add agent/styx_agent.py agent/tests/
git commit -m "feat(agent): stdlib daemon — selkies supervision, heartbeat, doctor, uninstall"
```

---

### Task 12: Enrollment script (`enroll.sh`)

**Files:**
- Modify: `agent/enroll.sh` (replace placeholder)

- [ ] **Step 1: Replace `agent/enroll.sh`**

```bash
#!/usr/bin/env bash
# Styx Portal workstation enrollment.
# Usage: curl -fsSL https://SERVER/api/enroll/script | bash -s -- \
#          --token <TOKEN> --server https://SERVER [--ca-pin sha256:<FP>]
set -euo pipefail

TOKEN="" SERVER="" CA_PIN=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token)  TOKEN="$2"; shift 2 ;;
    --server) SERVER="$2"; shift 2 ;;
    --ca-pin) CA_PIN="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$TOKEN" && -n "$SERVER" ]] || {
  echo "E00: --token and --server are required." >&2; exit 2; }
SERVER="${SERVER%/}"

INSTALL_DIR="$HOME/.local/share/styx-agent"
CONFIG_DIR="$HOME/.config/styx-agent"
UNIT_DIR="$HOME/.config/systemd/user"

fail() { local code="$1"; shift; echo ""; echo "✗ $code: $*" >&2; exit 1; }
note() { echo "  → $*"; }
step() { echo ""; echo "[$1] $2"; }

# curl wrapper: once the server cert is fingerprint-verified (step 5) it is
# saved and used as the pinned CA for every request — no insecure fetches.
PINNED_CERT=""
fetch() {
  if [[ -n "$PINNED_CERT" ]]; then curl -fsS --cacert "$PINNED_CERT" "$@"
  else curl -fsS "$@"; fi
}

step 1/8 "Checking distro and glibc (E01)"
command -v python3 >/dev/null 2>&1 || fail E01 "python3 not found. Install it (apt install python3 / dnf install python3)."
GLIBC=$(ldd --version 2>/dev/null | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo "0.0")
python3 - "$GLIBC" <<'PY' || fail E01 "glibc >= 2.17 required (found $GLIBC). Selkies portable build will not run."
import sys
maj, mino = (int(x) for x in sys.argv[1].split("."))
sys.exit(0 if (maj, mino) >= (2, 17) else 1)
PY
note "python3 + glibc $GLIBC OK"

step 2/8 "Detecting display server (E02)"
DISPLAY_SERVER="x11"
SESSION_TYPE="${XDG_SESSION_TYPE:-}"
if [[ -z "$SESSION_TYPE" ]] && command -v loginctl >/dev/null; then
  SESSION_TYPE=$(loginctl show-session "$(loginctl 2>/dev/null | awk -v u="$USER" '$3==u {print $1; exit}')" -p Type --value 2>/dev/null || true)
fi
if [[ "$SESSION_TYPE" == "wayland" ]]; then
  DISPLAY_SERVER="wayland"
  note "Wayland session detected. Selkies cannot mirror an existing Wayland desktop;"
  note "the agent will start its OWN desktop session on this machine instead."
elif [[ -S "/tmp/.X11-unix/X0" || -n "${DISPLAY:-}" ]]; then
  note "X11 detected — your existing desktop (:0) will be streamed."
else
  fail E02 "No display session found. Log into a graphical session first (or check loginctl show-session)."
fi

step 3/8 "Detecting GPU encoder (E03)"
GPU_VENDOR="none"
if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  GPU_VENDOR="nvidia"; note "NVIDIA GPU — NVENC hardware encoding"
elif command -v vainfo >/dev/null && vainfo >/dev/null 2>&1; then
  GPU_VENDOR="vaapi"; note "VAAPI GPU — hardware encoding"
else
  note "WARNING: no GPU encoder found — falling back to CPU x264 (higher latency)."
  note "For gaming performance install GPU drivers (nvidia-smi or vainfo must work)."
fi
if [[ "$DISPLAY_SERVER" == "wayland" ]]; then
  id -nG | grep -qw video  || note "WARNING (E03): user not in 'video' group — run: sudo usermod -aG video $USER && re-login"
  id -nG | grep -qw render || note "WARNING (E03): user not in 'render' group — run: sudo usermod -aG render $USER && re-login"
fi

step 4/8 "Checking audio stack (E04)"
if command -v pipewire >/dev/null || command -v pulseaudio >/dev/null || pactl info >/dev/null 2>&1; then
  note "audio OK"
else
  fail E04 "Neither PipeWire nor PulseAudio found. Install one (apt install pipewire) for audio streaming."
fi

step 5/8 "Checking server reachability (E05/E06)"
if [[ -n "$CA_PIN" ]]; then
  HOSTPORT="${SERVER#https://}"; HOSTPORT="${HOSTPORT%%/*}"
  HOST="${HOSTPORT%%:*}"; PORT="${HOSTPORT##*:}"; [[ "$PORT" == "$HOST" ]] && PORT=443
  mkdir -p "$CONFIG_DIR"
  PINNED_CERT="$CONFIG_DIR/server-cert.pem"
  echo | openssl s_client -connect "$HOST:$PORT" 2>/dev/null \
    | openssl x509 -outform PEM > "$PINNED_CERT" \
    || fail E06 "Could not read TLS certificate from $HOST:$PORT."
  ACTUAL=$(openssl x509 -in "$PINNED_CERT" -fingerprint -sha256 -noout \
    | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')
  EXPECTED=$(echo "${CA_PIN#sha256:}" | tr -d ':' | tr 'A-F' 'a-f')
  if [[ "$ACTUAL" != "$EXPECTED" ]]; then
    rm -f "$PINNED_CERT"
    fail E06 "TLS certificate fingerprint mismatch (expected $EXPECTED, got $ACTUAL). Wrong server or MITM."
  fi
  chmod 600 "$PINNED_CERT"
  note "certificate pin verified — pinned cert saved for all further requests"
fi
fetch "$SERVER/api/health" >/dev/null || fail E05 "Cannot reach $SERVER from this machine. Check LAN routing/firewall (this must be the portal's LOCAL address, not the public tunnel)."
note "server reachable"

step 6/8 "Checking port and systemd (E07/E08)"
SELKIES_PORT=8443
if command -v ss >/dev/null && ss -ltn "sport = :$SELKIES_PORT" 2>/dev/null | grep -q LISTEN; then
  fail E07 "Port $SELKIES_PORT already in use. Free it or change WORKSTATION_DEFAULT_PORT on the server."
fi
systemctl --user show-environment >/dev/null 2>&1 \
  || fail E08 "systemd --user session unavailable. Log in as this user via a normal session (not su/sudo)."

step 7/8 "Installing agent + Selkies"
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$UNIT_DIR" "$INSTALL_DIR/logs"
fetch "$SERVER/api/enroll/agent.py"  -o "$INSTALL_DIR/styx_agent.py"
fetch "$SERVER/api/enroll/uninstall" -o "$INSTALL_DIR/uninstall.sh"
chmod +x "$INSTALL_DIR/uninstall.sh"
note "downloading Selkies (cached on server — may take a minute)…"
fetch "$SERVER/api/enroll/artifacts/selkies.tar.gz" -o "$INSTALL_DIR/selkies.tar.gz" \
  || fail E05 "Selkies download failed. On the server, check SELKIES_TARBALL_URL or pre-place the tarball (see docs/WORKSTATIONS.md)."
mkdir -p "$INSTALL_DIR/selkies"
tar -xzf "$INSTALL_DIR/selkies.tar.gz" -C "$INSTALL_DIR/selkies" --strip-components=1
rm -f "$INSTALL_DIR/selkies.tar.gz"

step 8/8 "Registering with portal"
SERVER_HOST="${SERVER#http*://}"; SERVER_HOST="${SERVER_HOST%%/*}"; SERVER_HOST="${SERVER_HOST%%:*}"
LAN_IP=$(ip route get "$SERVER_HOST" 2>/dev/null | grep -oP 'src \K\S+' || hostname -I | awk '{print $1}')
REGISTER_RESPONSE=$(fetch -X POST "$SERVER/api/enroll/register" \
  -H "Content-Type: application/json" \
  -d "$(python3 - "$TOKEN" "$LAN_IP" "$DISPLAY_SERVER" "$GPU_VENDOR" <<'PY'
import json, platform, sys
print(json.dumps({
    "token": sys.argv[1], "hostname": platform.node() or "workstation",
    "lan_ip": sys.argv[2], "display_server": sys.argv[3],
    "gpu_info": {"vendor": sys.argv[4]},
    "os_info": {"distro": platform.freedesktop_os_release().get("ID", "unknown")
                if hasattr(platform, "freedesktop_os_release") else "unknown",
                "kernel": platform.release()},
    "agent_version": "0.1.0"}))
PY
)") || fail E05 "Registration rejected. The token may be expired or already used — mint a new one in the admin Workstations panel."

python3 - "$REGISTER_RESPONSE" "$SERVER" "$CA_PIN" "$DISPLAY_SERVER" "$INSTALL_DIR" "$CONFIG_DIR" <<'PY'
import json, sys
r = json.loads(sys.argv[1])
cfg = {"server": sys.argv[2], "agent_token": r["agent_token"],
       "workstation_id": r["workstation_id"], "port": r["port"],
       "selkies_user": r["selkies_user"], "selkies_password": r["selkies_password"],
       "display_server": sys.argv[4], "stream_settings": r["stream_settings"],
       "selkies_dir": sys.argv[5] + "/selkies", "ca_pin": sys.argv[3],
       "server_cert": (sys.argv[6] + "/server-cert.pem") if sys.argv[3] else ""}
with open(sys.argv[6] + "/config.json", "w") as f:
    json.dump(cfg, f, indent=2)
print("  → registered as: " + r["subdomain"])
PY
chmod 600 "$CONFIG_DIR/config.json"

cat > "$UNIT_DIR/styx-agent.service" <<EOF
[Unit]
Description=Styx Portal workstation agent (Selkies streaming)
After=network-online.target

[Service]
ExecStart=/usr/bin/env python3 $INSTALL_DIR/styx_agent.py run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now styx-agent.service

if command -v loginctl >/dev/null && [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
  echo ""
  echo "Enabling lingering so streaming survives logout (requires sudo, one time):"
  sudo loginctl enable-linger "$USER" \
    || note "WARNING: lingering not enabled — streaming stops when you log out. Run later: sudo loginctl enable-linger $USER"
fi

echo ""
echo "✓ Enrollment complete. This workstation should appear Online in the portal within 60s."
echo "  Troubleshoot:  python3 $INSTALL_DIR/styx_agent.py doctor"
echo "  Uninstall:     python3 $INSTALL_DIR/styx_agent.py uninstall"
```

- [ ] **Step 2: Lint**

Run: `shellcheck agent/enroll.sh`
Expected: no errors (warnings SC2086-class fixed inline; if shellcheck not installed: `sudo apt install shellcheck` or skip with note in commit)

- [ ] **Step 3: Verify served content test still passes**

Run (from `backend/`): `.venv/bin/python -m pytest tests/test_workstation_enroll.py -v`
Expected: PASS (script still contains `--token`)

- [ ] **Step 4: Commit**

```bash
git add agent/enroll.sh
git commit -m "feat(agent): enrollment script — preflight E01-E08, install, register"
```

---

### Task 13: Uninstall script

**Files:**
- Modify: `agent/uninstall.sh` (replace placeholder)

- [ ] **Step 1: Replace `agent/uninstall.sh`**

```bash
#!/usr/bin/env bash
# Styx agent removal. Safe to run repeatedly.
# Usage: bash uninstall.sh   (or: python3 ~/.local/share/styx-agent/styx_agent.py uninstall)
set -euo pipefail

INSTALL_DIR="$HOME/.local/share/styx-agent"

if [[ -f "$INSTALL_DIR/styx_agent.py" ]]; then
  python3 "$INSTALL_DIR/styx_agent.py" uninstall
else
  systemctl --user disable --now styx-agent.service 2>/dev/null || true
  rm -f "$HOME/.config/systemd/user/styx-agent.service"
  systemctl --user daemon-reload 2>/dev/null || true
  rm -rf "$INSTALL_DIR" "$HOME/.config/styx-agent"
  echo "Styx agent removed (agent script was missing; cleaned up files directly)."
fi
```

- [ ] **Step 2: Lint + commit**

Run: `shellcheck agent/uninstall.sh`
Expected: clean

```bash
git add agent/uninstall.sh
git commit -m "feat(agent): standalone uninstall script"
```

---

### Task 14: Frontend API client + types

**Files:**
- Modify: `frontend/src/api/client.ts`

- [ ] **Step 1: Add types near the other exported types (top of file)**

```typescript
export type Workstation = {
  id: string; name: string; subdomain: string; hostname: string;
  lan_ip: string; port: number; status: string; display_server: string;
  gpu_info: Record<string, unknown>; os_info: Record<string, unknown>;
  agent_version: string; stream_settings: { encoder: string; framerate: number; bitrate_kbps: number };
  all_users: boolean; last_heartbeat: string | null; last_error: string | null;
  created_at: string; allowed_user_ids: string[];
};
export type EnrollToken = { token: string; expires_at: string; command: string };
```

- [ ] **Step 2: Add methods inside the `api` object (after `changeRole`)**

```typescript
  // Workstations
  listWorkstations: () => request<Workstation[]>("/workstations"),
  myWorkstations: () => request<Workstation[]>("/workstations/mine"),
  mintEnrollToken: () =>
    request<EnrollToken>("/workstations/enroll-tokens", { method: "POST" }),
  updateWorkstation: (id: string, data: { name?: string; all_users?: boolean;
    stream_settings?: Record<string, unknown> }) =>
    request<Workstation>(`/workstations/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  setWorkstationAccess: (id: string, user_ids: string[]) =>
    request<Workstation>(`/workstations/${id}/access`, { method: "PUT", body: JSON.stringify({ user_ids }) }),
  revokeWorkstation: (id: string, purge = false) =>
    request<{ ok: boolean }>(`/workstations/${id}?purge=${purge}`, { method: "DELETE" }),
  workstationConnectUrl: (id: string) =>
    request<{ url: string }>(`/workstations/${id}/connect`),
```

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(workstations): frontend API client methods"
```

---

### Task 15: Admin Workstations panel

**Files:**
- Create: `frontend/src/components/system/workstations-panel.tsx`
- Modify: `frontend/src/components/settings/nav-config.tsx`

**Before coding:** open `frontend/src/components/system/users-panel.tsx` and reuse its layout primitives (section card, table classes, copy-button pattern for the invite link). The component below is complete logic; match its surrounding classNames to users-panel so styling is consistent.

- [ ] **Step 1: Create `workstations-panel.tsx`**

```tsx
import { useCallback, useEffect, useState } from "react";
import { Copy, Monitor, RefreshCw, Trash2 } from "lucide-react";
import { api, type EnrollToken, type Workstation } from "@/api/client";

const STATUS_STYLES: Record<string, string> = {
  online: "bg-emerald-500/15 text-emerald-400",
  offline: "bg-amber-500/15 text-amber-400",
  pending: "bg-sky-500/15 text-sky-400",
  revoked: "bg-rose-500/15 text-rose-400",
};

export function WorkstationsPanel() {
  const [rows, setRows] = useState<Workstation[]>([]);
  const [users, setUsers] = useState<{ id: string; username: string }[]>([]);
  const [enroll, setEnroll] = useState<EnrollToken | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(() => {
    api.listWorkstations().then(setRows).catch((e) => setError(String(e)));
    api.listUsers().then((u) => setUsers(u.map(({ id, username }) => ({ id, username }))))
      .catch(() => {});
  }, []);
  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, [refresh]);

  const mint = async () => {
    setError(null);
    try { setEnroll(await api.mintEnrollToken()); }
    catch (e) { setError(String(e)); }
  };
  const copy = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  const toggleAllUsers = (ws: Workstation) =>
    api.updateWorkstation(ws.id, { all_users: !ws.all_users }).then(refresh);
  const toggleUser = (ws: Workstation, uid: string) => {
    const next = ws.allowed_user_ids.includes(uid)
      ? ws.allowed_user_ids.filter((x) => x !== uid)
      : [...ws.allowed_user_ids, uid];
    api.setWorkstationAccess(ws.id, next).then(refresh);
  };
  const revoke = (ws: Workstation) => {
    if (!confirm(`Revoke "${ws.name}"? The agent will stop streaming and show uninstall instructions.`)) return;
    api.revokeWorkstation(ws.id).then(refresh);
  };
  const purge = (ws: Workstation) => {
    if (!confirm(`Permanently remove "${ws.name}" from the portal? Run the uninstall on the machine too.`)) return;
    api.revokeWorkstation(ws.id, true).then(refresh);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Monitor className="h-5 w-5" /> Workstations
        </h2>
        <div className="flex gap-2">
          <button onClick={refresh} className="btn-secondary" title="Refresh">
            <RefreshCw className="h-4 w-4" />
          </button>
          <button onClick={mint} className="btn-primary">Enroll workstation</button>
        </div>
      </div>
      {error && <p className="text-sm text-rose-400">{error}</p>}

      {enroll && (
        <div className="rounded-lg border border-border bg-surface p-4 space-y-2">
          <p className="text-sm">Run this on the workstation (token valid until{" "}
            {new Date(enroll.expires_at).toLocaleString()}, single use):</p>
          <div className="flex items-start gap-2">
            <code className="flex-1 break-all rounded bg-muted px-2 py-1 text-xs">
              {enroll.command}
            </code>
            <button onClick={() => copy(enroll.command)} className="btn-secondary">
              <Copy className="h-4 w-4" /> {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No workstations enrolled. Click “Enroll workstation” and run the command
          on a physical Linux machine on the same network.
        </p>
      ) : rows.map((ws) => (
        <div key={ws.id} className="rounded-lg border border-border bg-surface p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="font-medium">{ws.name}</span>
              <span className={`ml-2 rounded px-2 py-0.5 text-xs ${STATUS_STYLES[ws.status] ?? ""}`}>
                {ws.status}
              </span>
            </div>
            <div className="flex gap-2">
              <button onClick={() => revoke(ws)} className="btn-secondary"
                      disabled={ws.status === "revoked"}>Revoke</button>
              <button onClick={() => purge(ws)} className="btn-danger" title="Remove from portal">
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted-foreground sm:grid-cols-4">
            <div><dt className="inline">IP: </dt><dd className="inline">{ws.lan_ip}:{ws.port}</dd></div>
            <div><dt className="inline">Display: </dt><dd className="inline">{ws.display_server}</dd></div>
            <div><dt className="inline">GPU: </dt><dd className="inline">{String(ws.gpu_info?.vendor ?? "none")}</dd></div>
            <div><dt className="inline">Last seen: </dt>
              <dd className="inline">{ws.last_heartbeat ? new Date(ws.last_heartbeat).toLocaleTimeString() : "never"}</dd></div>
          </dl>
          {ws.last_error && <p className="text-xs text-rose-400">Agent error: {ws.last_error}</p>}
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <label className="flex items-center gap-1.5">
              <input type="checkbox" checked={ws.all_users}
                     onChange={() => toggleAllUsers(ws)} />
              All users
            </label>
            {!ws.all_users && users.map((u) => (
              <label key={u.id} className="flex items-center gap-1.5">
                <input type="checkbox"
                       checked={ws.allowed_user_ids.includes(u.id)}
                       onChange={() => toggleUser(ws, u.id)} />
                {u.username}
              </label>
            ))}
          </div>
          {ws.status === "revoked" && (
            <p className="text-xs text-muted-foreground">
              To finish removal on the machine:{" "}
              <code>python3 ~/.local/share/styx-agent/styx_agent.py uninstall</code>
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
```

(If `btn-primary` / `btn-secondary` / `btn-danger` classes don't exist, copy the exact button classNames used in `users-panel.tsx`.)

- [ ] **Step 2: Register in `nav-config.tsx`.** Add import:

```tsx
import { WorkstationsPanel } from "@/components/system/workstations-panel";
import { MonitorSmartphone } from "lucide-react";
```

In the `administration` category `sections` array, after the `users` entry add:

```tsx
      { id: "workstations", label: "Workstations", icon: MonitorSmartphone,
        description: "Enroll and manage physical Linux machines.",
        tooltip: "Stream physical workstations via the Styx agent", Component: WorkstationsPanel },
```

- [ ] **Step 3: Build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/system/workstations-panel.tsx frontend/src/components/settings/nav-config.tsx
git commit -m "feat(workstations): admin panel — enroll, access, revoke"
```

---

### Task 16: User-facing workstation cards

**Files:**
- Create: `frontend/src/components/instances/workstation-grid.tsx`
- Modify: `frontend/src/components/instances/instance-workspace.tsx`

- [ ] **Step 1: Create `workstation-grid.tsx`**

```tsx
import { useEffect, useState } from "react";
import { Monitor } from "lucide-react";
import { api, type Workstation } from "@/api/client";

export function WorkstationGrid() {
  const [rows, setRows] = useState<Workstation[]>([]);
  useEffect(() => {
    const load = () => api.myWorkstations().then(setRows).catch(() => {});
    load();
    const t = setInterval(load, 15000);
    return () => clearInterval(t);
  }, []);
  if (rows.length === 0) return null;

  const connect = async (ws: Workstation) => {
    const { url } = await api.workstationConnectUrl(ws.id);
    window.open(url, "_blank", "noopener");
  };

  return (
    <section className="space-y-2">
      <h3 className="text-sm font-medium text-muted-foreground">Workstations</h3>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {rows.map((ws) => (
          <div key={ws.id}
               className="rounded-lg border border-border bg-surface p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Monitor className="h-6 w-6 text-muted-foreground" />
              <div>
                <p className="font-medium">{ws.name}</p>
                <p className="text-xs text-muted-foreground">
                  {ws.status === "online" ? "Online" : `Offline (${ws.status})`}
                  {" · "}{ws.display_server}
                </p>
              </div>
            </div>
            <button className="btn-primary" disabled={ws.status !== "online"}
                    onClick={() => connect(ws)}>
              Connect
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Mount it.** Find the instance grid render:

Run: `grep -n "InstanceGrid" frontend/src/components/instances/instance-workspace.tsx`
Expected: an import line and one JSX usage.

In `instance-workspace.tsx`, import `WorkstationGrid` and render `<WorkstationGrid />` immediately ABOVE the `<InstanceGrid …/>` JSX usage (same parent container). The component renders nothing when the user has no workstations, so layout is unchanged for everyone else.

- [ ] **Step 3: Build + commit**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean

```bash
git add frontend/src/components/instances/workstation-grid.tsx frontend/src/components/instances/instance-workspace.tsx
git commit -m "feat(workstations): dashboard workstation cards with connect"
```

---

### Task 17: Docs

**Files:**
- Create: `docs/WORKSTATIONS.md`
- Modify: `docs/ADMIN.md` (link), `CLAUDE.md` (structure note)

- [ ] **Step 1: Write `docs/WORKSTATIONS.md`** covering exactly:
  - What it is (stream physical Linux machines via Selkies; X11 = mirrors real desktop, Wayland = separate own-compositor session — upstream limitation, link selkies issue #46).
  - Enroll: mint in Settings → Workstations, paste one-liner. Requirements list (LAN reachability to `SERVER_LAN_URL`, python3, glibc ≥ 2.17, graphical session, PipeWire/PulseAudio; GPU drivers for gaming performance).
  - Settings reference table: `SERVER_LAN_URL`, `SERVER_CA_PIN`, `SELKIES_TARBALL_URL`, `ARTIFACT_CACHE_DIR`, `ENROLL_TOKEN_TTL_HOURS`, `WORKSTATION_OFFLINE_AFTER_S`, `WORKSTATION_DEFAULT_PORT`, `WORKSTATION_HEARTBEAT_S` (copy defaults from `backend/app/config.py`).
  - Error code table E00–E08 with the exact remediation text from `agent/enroll.sh`.
  - Troubleshooting: `python3 ~/.local/share/styx-agent/styx_agent.py doctor` / `status`, log paths, "workstation shows offline" (heartbeat > 90 s → check service + LAN), "stream black/slow" (encoder fallback to x264 → install GPU drivers).
  - Removal: both directions (agent uninstall command; admin Revoke → agent self-stops; Purge for dead machines).
  - Air-gapped note: pre-place tarball at `ARTIFACT_CACHE_DIR/selkies.tar.gz`.

- [ ] **Step 2: Link from `docs/ADMIN.md`** — add a short "Physical workstations" section pointing to `docs/WORKSTATIONS.md`.

- [ ] **Step 3: Update `CLAUDE.md`** project structure block — add `agent/` line ("workstation enrollment script + agent daemon") and `routers/enroll.py`, `routers/agent.py`, `routers/workstations.py` entries.

- [ ] **Step 4: Commit**

```bash
git add docs/WORKSTATIONS.md docs/ADMIN.md CLAUDE.md
git commit -m "docs: workstation streaming guide + error codes"
```

---

### Task 18: Final verification

- [ ] **Step 1: Full backend suite + lint**

Run (from `backend/`): `.venv/bin/python -m pytest --tb=short && .venv/bin/python -m ruff check app/ tests/`
Expected: all PASS (≈ 288 pre-existing + ~25 new), no lint errors

- [ ] **Step 2: Agent tests + shellcheck**

Run (repo root): `backend/.venv/bin/python -m pytest agent/tests -v && shellcheck agent/enroll.sh agent/uninstall.sh`
Expected: PASS / clean

- [ ] **Step 3: Frontend**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: clean

- [ ] **Step 4: Manual smoke (requires a real Linux machine on the LAN)** — cannot be automated; checklist for the operator:
  1. Set `SERVER_LAN_URL` in `.env`, `docker compose up -d`.
  2. Settings → Workstations → Enroll → run one-liner on an X11 machine.
  3. Machine flips to Online within 60 s; Connect opens stream with video+audio.
  4. `styx_agent.py doctor` all green; Revoke → agent stops within 30 s.

**Known risk flagged for smoke testing:** the Selkies portable tarball launcher name (`selkies-gstreamer-run`) and env-var names (`SELKIES_PORT`, `SELKIES_ENCODER`, …) follow the selkies-gstreamer v1.6.x docs; verify against the actual tarball contents during the first smoke test and adjust `build_selkies_cmd` + `SELKIES_TARBALL_URL` in one place if upstream renamed anything. Same for `PIXELFLUX_WAYLAND` bare-metal behavior — if the Smithay compositor pieces are missing outside the LSIO container, fall back to documenting Wayland machines as "own X session via Xvfb" (set `DISPLAY` to a started Xvfb and drop the env var) — the agent change is confined to `build_selkies_cmd`.
```
