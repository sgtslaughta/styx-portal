# Service Proxy Core (SP1) — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend for proxying arbitrary internal HTTP services through the single Styx hostname with group ACL, two mount modes, three auth modes, local docker discovery and health polling.

**Architecture:** New `proxied_services`, `groups`, `user_groups`, `service_presets` tables. A new `service_routes` module adds Traefik routers/middlewares into the dict `route_writer.build_routes_config` already builds. A new `services` router owns CRUD, the Traefik forwardAuth `auth-check`, cookie-root `enter`, and `/_styx/exit`. Health runs as one more `main.py` loop.

**Tech Stack:** FastAPI, SQLModel (aiosqlite), Traefik v3 file provider, httpx, pytest (asyncio auto mode), ruff.

**Spec:** `docs/superpowers/specs/2026-10-12-service-proxy-core-design.md` (sections §3–§8, §10, §11). Frontend + docs are in `2026-10-12-service-proxy-core-frontend.md`.

## Global Constraints

- One hostname only: every router rule starts with `Host(`{domain}`)`. No subdomains anywhere.
- No `host` mount mode. Mount modes: `path`, `cookie-root`. Auth modes: `sso`, `sso-with-bypass`, `app-native`.
- Reserved slugs (reject with 400): `api i w assets login setup connecting change-password accept-invite _styx if application outpost.goauthentik.io static media flows ws - .well-known source`.
- Every service router carries `ip-ban-gate`, `styx-ratelimit`, `styx-strip-identity`.
- `auth-check` is called only by Traefik on the docker network; it is never routed publicly (the `/api/services/{slug}/auth-check` path is only reachable through the `api` router which the frontend uses; that is acceptable because it is read-only and returns 200/302/403/404 with no secrets).
- Admin-only CRUD; every mutation calls `audit_request` with action `<entity>.<verb>`.
- Files stay under 500 lines: new code goes in new modules, not appended to `route_writer.py` / `instances.py`.
- Ruff line length 100, Python 3.12. Commits: Conventional Commits, end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Run tests with `cd backend && .venv/bin/python -m pytest -q`; lint with `.venv/bin/python -m ruff check app tests`.

## Review Focus

1. Slug `API` or `Api` (case) must be rejected like `api`: the regex is lowercase-only, so uppercase fails the pattern. Test in Task 1.
2. Bypass rule with `path_prefix: "/"` and no header exposes the whole service unauthenticated. Allowed (admin choice) but the UI warns; backend test in Task 5 pins that it is accepted and that `auth_mode != sso-with-bypass` with non-empty `bypass_rules` is rejected.
3. `upstream_url` with a non-http(s) scheme (`file://`, `unix://`) must be rejected. Test in Task 1.
4. Forwarded URI with query string (`/sonarr/api?x=1`) must still match bypass prefix `/sonarr/api`. Test in Task 4.
5. Disabling a service must remove its routers on the next write and make `auth-check` return 404. Tests in Task 3 and Task 4.

---

### Task 1: Models and schemas

**Files:**
- Modify: `backend/app/models.py` (append after `WorkstationAccess`)
- Modify: `backend/app/schemas.py` (append)
- Test: `backend/tests/test_service_schemas.py`

**Interfaces:**
- Produces models `Group`, `UserGroup`, `ServicePreset`, `ProxiedService`; schemas `BypassRule`, `ProxiedServiceCreate`, `ProxiedServiceUpdate`, `ProxiedServiceOut`, `GroupCreate`, `GroupOut`, `UserGroupsUpdate`, `DiscoveredContainer`, `ServicePresetOut`; constants `SERVICE_SLUG_RE`, `RESERVED_SERVICE_SLUGS`; helper `upstream_base(svc) -> str`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_service_schemas.py
import pytest
from pydantic import ValidationError
from app.schemas import ProxiedServiceCreate


def _base(**kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://192.168.1.10:8989", "mount_mode": "path", "auth_mode": "sso"}
    d.update(kw)
    return d


def test_valid_url_service():
    s = ProxiedServiceCreate(**_base())
    assert s.slug == "sonarr"


@pytest.mark.parametrize("slug", ["api", "Api", "API", "_styx", "if", "outpost.goauthentik.io",
                                  ".well-known", "-", "w", "i", "has space", ""])
def test_reserved_or_invalid_slug_rejected(slug):
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(slug=slug))


@pytest.mark.parametrize("url", ["file:///etc/passwd", "unix:///var/run/docker.sock", "192.168.1.1:80"])
def test_bad_upstream_scheme_rejected(url):
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(upstream_url=url))


def test_docker_local_requires_container_and_port():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(kind="docker-local", upstream_url=None))
    s = ProxiedServiceCreate(**_base(kind="docker-local", upstream_url=None,
                                     container="sonarr", container_port=8989))
    assert s.container_port == 8989


def test_bypass_rules_only_with_bypass_mode():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(auth_mode="sso",
                                     bypass_rules=[{"path_prefix": "/sonarr/api"}]))
    s = ProxiedServiceCreate(**_base(auth_mode="sso-with-bypass",
                                     bypass_rules=[{"path_prefix": "/", "required_header": None}]))
    assert s.bypass_rules[0].path_prefix == "/"


def test_bypass_prefix_must_start_with_slash():
    with pytest.raises(ValidationError):
        ProxiedServiceCreate(**_base(auth_mode="sso-with-bypass",
                                     bypass_rules=[{"path_prefix": "api"}]))
```

- [ ] **Step 2: Run, expect ImportError**

Run: `cd backend && .venv/bin/python -m pytest tests/test_service_schemas.py -q`
Expected: FAIL `ImportError: cannot import name 'ProxiedServiceCreate'`

- [ ] **Step 3: Add models**

Append to `backend/app/models.py`:

```python
class Group(SQLModel, table=True):
    __tablename__ = "groups"
    id: str = Field(default_factory=_uuid, primary_key=True)
    name: str = Field(unique=True, index=True)
    description: str | None = None
    created_at: datetime = Field(default_factory=_now)


class UserGroup(SQLModel, table=True):
    __tablename__ = "user_groups"
    user_id: str = Field(foreign_key="users.id", primary_key=True)
    group_id: str = Field(foreign_key="groups.id", primary_key=True)


class ServicePreset(SQLModel, table=True):
    """Routing preset seeded from templates/services/*.json (insert-only)."""
    __tablename__ = "service_presets"
    id: str = Field(primary_key=True)          # e.g. "sonarr"
    name: str
    icon: str | None = None
    default_port: int | None = None
    mount_mode: str = "path"
    auth_mode: str = "sso"
    bypass_rules: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    health_path: str | None = None
    verify_tls: bool = True
    base_url_hint: str | None = None
    warnings: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class ProxiedService(SQLModel, table=True):
    __tablename__ = "proxied_services"
    id: str = Field(default_factory=_uuid, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str
    icon: str | None = None
    kind: str = "url"                          # url | docker-local
    upstream_url: str | None = None            # url kind
    container: str | None = None               # docker-local kind
    container_port: int | None = None
    # Set when connecting the container to the styx network failed and we
    # fell back to host.docker.internal (see routers/services.py).
    upstream_fallback: str | None = None
    mount_mode: str = "path"                   # path | cookie-root
    auth_mode: str = "sso"                     # sso | sso-with-bypass | app-native
    bypass_rules: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    allowed_groups: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    verify_tls: bool = True
    health_path: str | None = None
    health_status: str = "unknown"             # healthy | unhealthy | unknown
    health_checked_at: datetime | None = None
    preset_id: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


def upstream_base(svc: "ProxiedService") -> str:
    """Base URL Traefik and the health loop use to reach the service."""
    if svc.kind == "docker-local":
        return svc.upstream_fallback or f"http://{svc.container}:{svc.container_port}"
    return (svc.upstream_url or "").rstrip("/")
```

- [ ] **Step 4: Add schemas**

Append to `backend/app/schemas.py`:

```python
SERVICE_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_SERVICE_SLUGS = {
    "api", "i", "w", "assets", "login", "setup", "connecting", "change-password",
    "accept-invite", "_styx",
    # Authentik (SP2) prefixes, reserved now so no slug migration later
    "if", "application", "outpost.goauthentik.io", "static", "media", "flows", "ws",
    "-", ".well-known", "source",
}
MOUNT_MODES = {"path", "cookie-root"}
AUTH_MODES = {"sso", "sso-with-bypass", "app-native"}
SERVICE_KINDS = {"url", "docker-local"}


class BypassRule(BaseModel):
    path_prefix: str = Field(min_length=1, max_length=255)
    required_header: str | None = Field(default=None, max_length=64)

    @field_validator("path_prefix")
    @classmethod
    def _starts_with_slash(cls, v):
        if not v.startswith("/"):
            raise ValueError("path_prefix must start with /")
        return v


class _ServiceFields(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    icon: str | None = Field(default=None, max_length=255)
    kind: str = "url"
    upstream_url: str | None = None
    container: str | None = Field(default=None, max_length=255)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    mount_mode: str = "path"
    auth_mode: str = "sso"
    bypass_rules: list[BypassRule] = []
    allowed_groups: list[str] = []
    verify_tls: bool = True
    health_path: str | None = Field(default=None, max_length=255)
    preset_id: str | None = None
    enabled: bool = True

    @field_validator("kind")
    @classmethod
    def _kind(cls, v):
        if v not in SERVICE_KINDS:
            raise ValueError("kind must be url or docker-local")
        return v

    @field_validator("mount_mode")
    @classmethod
    def _mount(cls, v):
        if v not in MOUNT_MODES:
            raise ValueError("mount_mode must be path or cookie-root")
        return v

    @field_validator("auth_mode")
    @classmethod
    def _auth(cls, v):
        if v not in AUTH_MODES:
            raise ValueError("auth_mode must be sso, sso-with-bypass or app-native")
        return v

    @field_validator("upstream_url")
    @classmethod
    def _url(cls, v):
        if v is None:
            return v
        if not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("upstream_url must start with http:// or https://")
        return v.rstrip("/")

    @field_validator("health_path")
    @classmethod
    def _health(cls, v):
        if v is not None and not v.startswith("/"):
            raise ValueError("health_path must start with /")
        return v

    def _cross_check(self):
        if self.kind == "url" and not self.upstream_url:
            raise ValueError("upstream_url required for kind=url")
        if self.kind == "docker-local" and not (self.container and self.container_port):
            raise ValueError("container and container_port required for kind=docker-local")
        if self.bypass_rules and self.auth_mode != "sso-with-bypass":
            raise ValueError("bypass_rules only allowed with auth_mode=sso-with-bypass")
        return self


class ProxiedServiceCreate(_ServiceFields):
    slug: str

    @field_validator("slug")
    @classmethod
    def _slug(cls, v):
        if not SERVICE_SLUG_RE.match(v) or v in RESERVED_SERVICE_SLUGS:
            raise ValueError("slug is invalid or reserved")
        return v

    @model_validator(mode="after")
    def _after(self):
        return self._cross_check()


class ProxiedServiceUpdate(_ServiceFields):
    @model_validator(mode="after")
    def _after(self):
        return self._cross_check()


class ProxiedServiceOut(BaseModel):
    id: str
    slug: str
    name: str
    icon: str | None
    kind: str
    upstream_url: str | None
    container: str | None
    container_port: int | None
    upstream_fallback: str | None
    mount_mode: str
    auth_mode: str
    bypass_rules: list[dict]
    allowed_groups: list[str]
    verify_tls: bool
    health_path: str | None
    health_status: str
    health_checked_at: str | None
    preset_id: str | None
    enabled: bool
    created_at: str
    updated_at: str


class ServicePresetOut(BaseModel):
    id: str
    name: str
    icon: str | None
    default_port: int | None
    mount_mode: str
    auth_mode: str
    bypass_rules: list[dict]
    health_path: str | None
    verify_tls: bool
    base_url_hint: str | None
    warnings: list[str]


class DiscoveredContainer(BaseModel):
    name: str
    image: str
    ports: list[int]
    networks: list[str]
    suggested_preset: str | None = None


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)


class GroupOut(BaseModel):
    id: str
    name: str
    description: str | None
    member_count: int = 0


class UserGroupsUpdate(BaseModel):
    group_ids: list[str]
```

Add `model_validator` to the pydantic import line at the top of `schemas.py`:
`from pydantic import BaseModel, Field, field_validator, model_validator`.

- [ ] **Step 5: Run tests, expect PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/test_service_schemas.py -q`
Expected: all PASS. Then `.venv/bin/python -m ruff check app tests`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/tests/test_service_schemas.py
git commit -m "feat(services): proxied service, group and preset models + schemas"
```

---

### Task 2: Groups CRUD and user membership

**Files:**
- Create: `backend/app/routers/groups.py`
- Modify: `backend/app/main.py` (router registration)
- Test: `backend/tests/test_groups_api.py`

**Interfaces:**
- Produces: `GET/POST /api/groups`, `DELETE /api/groups/{id}`, `GET/PUT /api/users/{user_id}/groups`; helper `async def user_group_names(session, user_id) -> list[str]` (used by Task 4).

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_groups_api.py
import pytest
from sqlmodel import select
from app.models import User


@pytest.mark.asyncio
async def test_group_crud_and_membership(admin_client, session):
    r = await admin_client.post("/api/groups", json={"name": "media", "description": "Jellyfin"})
    assert r.status_code == 201, r.text
    gid = r.json()["id"]
    r = await admin_client.post("/api/groups", json={"name": "media"})
    assert r.status_code == 409
    r = await admin_client.get("/api/groups")
    assert [g["name"] for g in r.json()] == ["media"]

    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    r = await admin_client.put(f"/api/users/{admin.id}/groups", json={"group_ids": [gid]})
    assert r.status_code == 200
    r = await admin_client.get(f"/api/users/{admin.id}/groups")
    assert r.json() == [gid]
    r = await admin_client.get("/api/groups")
    assert r.json()[0]["member_count"] == 1

    r = await admin_client.delete(f"/api/groups/{gid}")
    assert r.status_code == 204
    r = await admin_client.get(f"/api/users/{admin.id}/groups")
    assert r.json() == []


@pytest.mark.asyncio
async def test_groups_admin_only(member_client):
    r = await member_client.get("/api/groups")
    assert r.status_code == 403
```

- [ ] **Step 2: Run, expect 404s**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py -q`
Expected: FAIL (404 Not Found on `/api/groups`).

- [ ] **Step 3: Implement router**

```python
# backend/app/routers/groups.py
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlmodel import delete, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import Group, User, UserGroup
from app.schemas import GroupCreate, GroupOut, UserGroupsUpdate
from app.security.deps import require_admin
from app.services.audit import audit_request

router = APIRouter()
users_router = APIRouter()


async def user_group_names(session: AsyncSession, user_id: str) -> list[str]:
    result = await session.exec(
        select(Group.name).join(UserGroup, UserGroup.group_id == Group.id)
        .where(UserGroup.user_id == user_id))
    return sorted(result.all())


@router.get("", response_model=list[GroupOut])
async def list_groups(admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session)):
    counts = dict((await session.exec(
        select(UserGroup.group_id, func.count()).group_by(UserGroup.group_id))).all())
    groups = (await session.exec(select(Group).order_by(Group.name))).all()
    return [GroupOut(id=g.id, name=g.name, description=g.description,
                     member_count=counts.get(g.id, 0)) for g in groups]


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(body: GroupCreate, request: Request,
                       admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    if (await session.exec(select(Group).where(Group.name == body.name))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Group exists")
    g = Group(name=body.name, description=body.description)
    session.add(g)
    await audit_request(session, request, "group.create", user_id=admin.id,
                        resource=g.id, detail={"name": g.name})
    await session.commit()
    return GroupOut(id=g.id, name=g.name, description=g.description)


@router.delete("/{group_id}", status_code=204)
async def delete_group(group_id: str, request: Request,
                       admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    g = await session.get(Group, group_id)
    if g is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Group not found")
    await session.exec(delete(UserGroup).where(UserGroup.group_id == group_id))
    await session.delete(g)
    await audit_request(session, request, "group.delete", user_id=admin.id,
                        resource=group_id, detail={"name": g.name})
    await session.commit()
    return Response(status_code=204)


@users_router.get("/{user_id}/groups", response_model=list[str])
async def get_user_groups(user_id: str, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    result = await session.exec(select(UserGroup.group_id).where(UserGroup.user_id == user_id))
    return sorted(result.all())


@users_router.put("/{user_id}/groups", response_model=list[str])
async def set_user_groups(user_id: str, body: UserGroupsUpdate, request: Request,
                          admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    if await session.get(User, user_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    existing = set((await session.exec(select(Group.id).where(Group.id.in_(body.group_ids)))).all())
    if existing != set(body.group_ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown group id")
    await session.exec(delete(UserGroup).where(UserGroup.user_id == user_id))
    for gid in existing:
        session.add(UserGroup(user_id=user_id, group_id=gid))
    await audit_request(session, request, "user.groups_set", user_id=admin.id,
                        resource=user_id, detail={"group_ids": sorted(existing)})
    await session.commit()
    return sorted(existing)
```

In `backend/app/main.py`, next to the other router imports add
`from app.routers import groups as groups_router`, and after the
`system_settings_router` registration line add:

```python
app.include_router(groups_router.router, prefix="/api/groups", tags=["groups"])
app.include_router(groups_router.users_router, prefix="/api/users", tags=["groups"])
```

- [ ] **Step 4: Run tests + ruff, expect PASS**

Run: `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py -q && .venv/bin/python -m ruff check app tests`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/groups.py backend/app/main.py backend/tests/test_groups_api.py
git commit -m "feat(groups): groups CRUD and per-user membership"
```

---

### Task 3: Service presets seeding

**Files:**
- Create: `templates/services/sonarr.json`, `radarr.json`, `prowlarr.json`, `lidarr.json`, `jellyfin.json`, `nextcloud.json`, `gitlab.json`, `audiobookshelf.json`, `unraid.json`, `generic-url.json`
- Modify: `backend/app/database.py` (`seed_service_presets`, called from `init_db`)
- Modify: `backend/app/config.py` (`SERVICE_PRESETS_DIR`)
- Test: `backend/tests/test_seed_service_presets.py`

**Interfaces:**
- Produces: `async def seed_service_presets(session, presets_dir: str)`; `Settings.SERVICE_PRESETS_DIR = "/app/templates/services"`.

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_seed_service_presets.py
import json
import pytest
from sqlmodel import select
from app.database import seed_service_presets
from app.models import ServicePreset


@pytest.mark.asyncio
async def test_seed_inserts_once(session, tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({
        "id": "x", "name": "X", "default_port": 80, "mount_mode": "path", "auth_mode": "sso"}))
    await seed_service_presets(session, str(tmp_path))
    await seed_service_presets(session, str(tmp_path))
    rows = (await session.exec(select(ServicePreset))).all()
    assert len(rows) == 1 and rows[0].name == "X"


@pytest.mark.asyncio
async def test_repo_presets_load(session):
    import os
    here = os.path.join(os.path.dirname(__file__), "..", "..", "templates", "services")
    await seed_service_presets(session, here)
    ids = {p.id for p in (await session.exec(select(ServicePreset))).all()}
    assert {"sonarr", "jellyfin", "audiobookshelf", "unraid", "generic-url"} <= ids
    ab = await session.get(ServicePreset, "audiobookshelf")
    assert ab.mount_mode == "cookie-root"
```

- [ ] **Step 2: Run, expect ImportError**

Run: `cd backend && .venv/bin/python -m pytest tests/test_seed_service_presets.py -q`

- [ ] **Step 3: Add preset files**

`templates/services/sonarr.json` (radarr/prowlarr/lidarr identical except `id`, `name`, `default_port` 7878 / 9696 / 8686 and the `/<slug>/api` prefix):

```json
{
  "id": "sonarr",
  "name": "Sonarr",
  "icon": "📺",
  "default_port": 8989,
  "mount_mode": "path",
  "auth_mode": "sso-with-bypass",
  "bypass_rules": [{"path_prefix": "/sonarr/api", "required_header": "X-Api-Key"}],
  "health_path": "/sonarr/ping",
  "verify_tls": true,
  "base_url_hint": "Settings → General → URL Base = /sonarr, then restart Sonarr.",
  "warnings": ["/sonarr/api is reachable without Styx login so mobile apps can use the API key."]
}
```

`templates/services/jellyfin.json`:

```json
{
  "id": "jellyfin",
  "name": "Jellyfin",
  "icon": "🎬",
  "default_port": 8096,
  "mount_mode": "path",
  "auth_mode": "sso-with-bypass",
  "bypass_rules": [{"path_prefix": "/jellyfin/", "required_header": "Authorization"}],
  "health_path": "/jellyfin/health",
  "verify_tls": true,
  "base_url_hint": "Dashboard → Networking → Base URL = /jellyfin, then restart Jellyfin.",
  "warnings": ["Requests carrying an Authorization header bypass Styx login so Jellyfin apps work. Jellyfin validates the token itself."]
}
```

`templates/services/nextcloud.json`:

```json
{
  "id": "nextcloud", "name": "Nextcloud", "icon": "☁️", "default_port": 80,
  "mount_mode": "path", "auth_mode": "sso", "bypass_rules": [],
  "health_path": "/nextcloud/status.php", "verify_tls": true,
  "base_url_hint": "config.php: 'overwritewebroot' => '/nextcloud', 'overwrite.cli.url' => 'https://<host>/nextcloud'.",
  "warnings": []
}
```

`templates/services/gitlab.json`:

```json
{
  "id": "gitlab", "name": "GitLab", "icon": "🦊", "default_port": 80,
  "mount_mode": "path", "auth_mode": "sso", "bypass_rules": [],
  "health_path": "/gitlab/-/readiness", "verify_tls": true,
  "base_url_hint": "gitlab.rb: external_url 'https://<host>/gitlab' then gitlab-ctl reconfigure.",
  "warnings": ["Git over HTTPS from the CLI will not pass Styx SSO; use SSH remotes or app-native mode."]
}
```

`templates/services/audiobookshelf.json`:

```json
{
  "id": "audiobookshelf", "name": "Audiobookshelf", "icon": "🎧", "default_port": 13378,
  "mount_mode": "cookie-root", "auth_mode": "sso-with-bypass",
  "bypass_rules": [{"path_prefix": "/api/", "required_header": "Authorization"}],
  "health_path": "/healthcheck", "verify_tls": true,
  "base_url_hint": null,
  "warnings": ["Audiobookshelf has no base-URL support: it takes over the root of the hostname for this browser (one service at a time). Mobile apps cannot use this mode."]
}
```

`templates/services/unraid.json`:

```json
{
  "id": "unraid", "name": "Unraid", "icon": "🟠", "default_port": 443,
  "mount_mode": "cookie-root", "auth_mode": "sso", "bypass_rules": [],
  "health_path": "/login", "verify_tls": false,
  "base_url_hint": null,
  "warnings": ["Unraid uses a self-signed certificate: TLS verification is disabled for this upstream.",
               "Takes over the root of the hostname for this browser (one service at a time)."]
}
```

`templates/services/generic-url.json`:

```json
{
  "id": "generic-url", "name": "Generic HTTP service", "icon": "🔗", "default_port": null,
  "mount_mode": "path", "auth_mode": "sso", "bypass_rules": [],
  "health_path": null, "verify_tls": true,
  "base_url_hint": "Configure the app's base URL / URL base to /<slug> if it supports one; otherwise use cookie-root mode.",
  "warnings": []
}
```

- [ ] **Step 4: Loader + config**

In `backend/app/config.py` add `SERVICE_PRESETS_DIR: str = "/app/templates/services"` after `TEMPLATES_DIR`.

In `backend/app/database.py`, import `ServicePreset` from `app.models`, add after `seed_templates`:

```python
async def seed_service_presets(session: AsyncSession, presets_dir: str):
    """Insert-only seed of templates/services/*.json into service_presets."""
    if not os.path.isdir(presets_dir):
        return
    for filename in sorted(os.listdir(presets_dir)):
        if not filename.endswith(".json"):
            continue
        with open(os.path.join(presets_dir, filename)) as f:
            data = json.load(f)
        if await session.get(ServicePreset, data["id"]):
            continue
        session.add(ServicePreset(**data))
    await session.commit()
```

and in `init_db` after `await seed_templates(session, settings.TEMPLATES_DIR)` add
`await seed_service_presets(session, settings.SERVICE_PRESETS_DIR)`.

Check the backend Dockerfile / compose copies `templates/` into `/app/templates` (it does for instance templates; the `services/` subdirectory rides along). If the Dockerfile uses an explicit `COPY templates/*.json`, change it to `COPY templates/ /app/templates/`.

- [ ] **Step 5: Run tests + ruff, expect PASS, commit**

```bash
git add templates/services backend/app/database.py backend/app/config.py backend/tests/test_seed_service_presets.py
git commit -m "feat(services): seed service routing presets"
```

---

### Task 4: Traefik routes for services

**Files:**
- Create: `backend/app/services/service_routes.py`
- Modify: `backend/app/services/route_writer.py` (signature of `build_routes_config`, `write_routes`, `refresh_routes_from_db`, serversTransports merge)
- Test: `backend/tests/test_route_writer_services.py`

**Interfaces:**
- Consumes: `upstream_base` (Task 1).
- Produces: `add_service_routes(config: dict, middlewares: dict, services: list[dict], domain: str, transport: dict) -> None`; `COOKIE_NAME = "styx_svc"`; `build_routes_config(..., services: list[dict] | None = None)`; `write_routes(..., services=None)`. Service dict shape: `{"slug", "upstream", "mount_mode", "auth_mode", "verify_tls", "enabled"}`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_route_writer_services.py
from app.services.route_writer import build_routes_config


def _svc(**kw):
    d = {"slug": "sonarr", "upstream": "http://192.168.1.10:8989", "mount_mode": "path",
         "auth_mode": "sso", "verify_tls": True, "enabled": True}
    d.update(kw)
    return d


def test_path_mode_router():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    r = cfg["http"]["routers"]["svc-sonarr"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/sonarr`)"
    assert r["priority"] == 60
    for mw in ("ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "svc-auth-sonarr"):
        assert mw in r["middlewares"]
    fa = cfg["http"]["middlewares"]["svc-auth-sonarr"]["forwardAuth"]
    assert fa["address"] == "http://backend:8000/api/services/sonarr/auth-check"
    assert fa["authResponseHeaders"] == ["X-Styx-User", "X-Styx-Groups"]
    assert cfg["http"]["services"]["svc-sonarr"]["loadBalancer"]["servers"] == [
        {"url": "http://192.168.1.10:8989"}]
    # no cookie-root service: /api router untouched
    assert cfg["http"]["routers"]["api"]["rule"] == "Host(`example.com`) && PathPrefix(`/api`)"
    assert "api-client" not in cfg["http"]["routers"]


def test_cookie_root_router_and_api_gating():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(slug="unraid", mount_mode="cookie-root")])
    r = cfg["http"]["routers"]["svc-unraid"]
    assert r["rule"] == "Host(`example.com`) && HeaderRegexp(`Cookie`, `(^|; )styx_svc=unraid(;|$)`)"
    assert r["priority"] == 40
    api = cfg["http"]["routers"]["api"]
    assert api["rule"] == ("Host(`example.com`) && PathPrefix(`/api`) && "
                           "!HeaderRegexp(`Cookie`, `(^|; )styx_svc=`)")
    client = cfg["http"]["routers"]["api-client"]
    assert client["rule"] == "Host(`example.com`) && PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)"
    assert client["priority"] == 100 and client["service"] == "api"


def test_exit_router_always_present_when_services():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    r = cfg["http"]["routers"]["styx-exit"]
    assert r["rule"] == "Host(`example.com`) && PathPrefix(`/_styx`)"
    assert r["priority"] == 90 and r["service"] == "api"


def test_app_native_has_no_forward_auth():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(auth_mode="app-native")])
    assert "svc-auth-sonarr" not in cfg["http"]["routers"]["svc-sonarr"]["middlewares"]
    assert "svc-auth-sonarr" not in cfg["http"]["middlewares"]


def test_insecure_upstream_transport():
    cfg = build_routes_config([], "example.com", "tunnel",
                              services=[_svc(upstream="https://10.0.0.5", verify_tls=False)])
    lb = cfg["http"]["services"]["svc-sonarr"]["loadBalancer"]
    assert lb["serversTransport"] == "styx-insecure-upstream"
    assert cfg["http"]["serversTransports"]["styx-insecure-upstream"] == {"insecureSkipVerify": True}


def test_insecure_transport_coexists_with_selkies_transport():
    inst = {"id": "i1", "subdomain": "d1", "port": 3001, "protocol": "https",
            "tls_skip_verify": True, "extra_ports": []}
    cfg = build_routes_config([inst], "example.com", "tunnel",
                              services=[_svc(upstream="https://10.0.0.5", verify_tls=False)])
    assert set(cfg["http"]["serversTransports"]) == {"selkies-transport", "styx-insecure-upstream"}


def test_disabled_service_emits_nothing():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc(enabled=False)])
    assert "svc-sonarr" not in cfg["http"]["routers"]
    assert "svc-sonarr" not in cfg["http"]["services"]


def test_identity_headers_stripped():
    cfg = build_routes_config([], "example.com", "tunnel", services=[_svc()])
    hdrs = cfg["http"]["middlewares"]["styx-strip-identity"]["headers"]["customRequestHeaders"]
    assert hdrs["X-Styx-User"] == "" and hdrs["X-authentik-groups"] == ""


def test_no_services_no_service_middlewares():
    cfg = build_routes_config([], "example.com", "tunnel")
    assert "styx-strip-identity" not in cfg["http"]["middlewares"]
    assert "styx-exit" not in cfg["http"]["routers"]
```

- [ ] **Step 2: Run, expect TypeError on `services=`**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer_services.py -q`

- [ ] **Step 3: Implement `service_routes.py`**

```python
# backend/app/services/service_routes.py
"""Traefik routers/middlewares for proxied services (spec §4).

Mounted on the single Styx hostname. `path` services get PathPrefix(/slug);
`cookie-root` services take over `/` for browsers carrying the styx_svc cookie.
"""

COOKIE_NAME = "styx_svc"
AUTH_CHECK = "http://backend:8000/api/services/{slug}/auth-check"
IDENTITY_HEADERS = ["X-Styx-User", "X-Styx-Groups", "X-authentik-username",
                    "X-authentik-groups", "X-authentik-email", "X-authentik-uid"]
BASE_MW = ["ip-ban-gate", "styx-ratelimit", "styx-strip-identity", "service-unavailable-errors"]


def add_service_routes(config: dict, middlewares: dict, services: list[dict],
                       domain: str, transport: dict) -> None:
    routers = config["http"]["routers"]
    lbs = config["http"]["services"]
    has_cookie_root = False
    has_insecure = False
    emitted = 0
    for s in services:
        if not s.get("enabled", True):
            continue
        emitted += 1
        slug = s["slug"]
        rid = f"svc-{slug}"
        mws = list(BASE_MW)
        if s["auth_mode"] != "app-native":
            middlewares[f"svc-auth-{slug}"] = {"forwardAuth": {
                "address": AUTH_CHECK.format(slug=slug),
                "authResponseHeaders": ["X-Styx-User", "X-Styx-Groups"]}}
            mws.append(f"svc-auth-{slug}")
        if s["mount_mode"] == "cookie-root":
            has_cookie_root = True
            rule = (f"Host(`{domain}`) && HeaderRegexp(`Cookie`, "
                    f"`(^|; ){COOKIE_NAME}={slug}(;|$)`)")
            priority = 40
        else:
            rule = f"Host(`{domain}`) && PathPrefix(`/{slug}`)"
            priority = 60
        routers[rid] = {"rule": rule, "service": rid, "priority": priority,
                        "middlewares": mws, **transport}
        lb: dict = {"servers": [{"url": s["upstream"]}]}
        if not s.get("verify_tls", True):
            lb["serversTransport"] = "styx-insecure-upstream"
            has_insecure = True
        lbs[rid] = {"loadBalancer": lb}

    if not emitted:
        return
    middlewares["styx-strip-identity"] = {"headers": {
        "customRequestHeaders": {h: "" for h in IDENTITY_HEADERS}}}
    middlewares["service-unavailable-errors"] = {"errors": {
        "status": ["502-504"], "service": "api", "query": "/api/service-unavailable"}}
    routers["styx-exit"] = {"rule": f"Host(`{domain}`) && PathPrefix(`/_styx`)",
                            "service": "api", "priority": 90,
                            "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    if has_cookie_root:
        # While a takeover cookie is set, /api belongs to the app unless the
        # request is from the Styx frontend (X-Styx-Client header).
        routers["api"]["rule"] = (f"Host(`{domain}`) && PathPrefix(`/api`) && "
                                  f"!HeaderRegexp(`Cookie`, `(^|; ){COOKIE_NAME}=`)")
        routers["api-client"] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/api`) && Header(`X-Styx-Client`, `1`)",
            "service": "api", "priority": 100,
            "middlewares": ["ip-ban-gate", "styx-ratelimit"], **transport}
    if has_insecure:
        config["http"].setdefault("serversTransports", {})["styx-insecure-upstream"] = {
            "insecureSkipVerify": True}
```

- [ ] **Step 4: Wire into `route_writer.py`**

Edit `build_routes_config` signature:

```python
def build_routes_config(instances: list[dict], domain: str,
                        deploy_mode: str = "tunnel",
                        workstations: list[dict] | None = None,
                        services: list[dict] | None = None) -> dict:
```

Replace the block

```python
    config["http"]["middlewares"] = middlewares
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }
```

with

```python
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }
    if services:
        from app.services.service_routes import add_service_routes
        add_service_routes(config, middlewares, services, domain,
                           _router_transport(deploy_mode, domain))
    config["http"]["middlewares"] = middlewares
```

Edit `write_routes`:

```python
def write_routes(instances: list[dict], domain: str | None = None,
                 workstations: list[dict] | None = None,
                 services: list[dict] | None = None):
    ...
        config = build_routes_config(instances, domain, _settings.DEPLOY_MODE,
                                     workstations, services)
```

In `refresh_routes_from_db`, import `ProxiedService, upstream_base` from `app.models`, and before `write_routes(...)` add:

```python
    svc_result = await session.exec(
        select(ProxiedService).where(ProxiedService.enabled == True))  # noqa: E712
    svc_data = [{
        "slug": s.slug, "upstream": upstream_base(s), "mount_mode": s.mount_mode,
        "auth_mode": s.auth_mode, "verify_tls": s.verify_tls, "enabled": s.enabled,
    } for s in svc_result.all()]
    write_routes(data, workstations=ws_data, services=svc_data)
```

- [ ] **Step 5: Run full suite + ruff, expect PASS**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app tests`
Existing route_writer tests must stay green (no services → no change).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/service_routes.py backend/app/services/route_writer.py backend/tests/test_route_writer_services.py
git commit -m "feat(services): emit Traefik routes for proxied services"
```

---

### Task 5: Services router — auth-check, enter, exit, unavailable page

**Files:**
- Modify: `backend/app/security/deps.py` (add `session_user_or_none`)
- Create: `backend/app/routers/services_auth.py`
- Modify: `backend/app/main.py` (register `services_auth.router` at `/api/services`, `services_auth.exit_router` at `/_styx`)
- Test: `backend/tests/test_services_auth_check.py`

**Interfaces:**
- Consumes: `user_group_names` (Task 2), `COOKIE_NAME` (Task 4).
- Produces: `GET /api/services/{slug}/auth-check`, `POST /api/services/{slug}/enter`, `GET /_styx/exit`, `GET /api/service-unavailable` (routers `router`, `exit_router`, `pages_router`); `async def session_user_or_none(request, session) -> User | None`; `async def user_may_open(session, user, svc) -> bool`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_services_auth_check.py
import pytest
from httpx import ASGITransport, AsyncClient
from sqlmodel import select
from app.main import app
from app.models import Group, ProxiedService, User, UserGroup


async def _svc(session, **kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "auth_mode": "sso-with-bypass",
         "bypass_rules": [{"path_prefix": "/sonarr/api", "required_header": "X-Api-Key"}]}
    d.update(kw)
    s = ProxiedService(**d)
    session.add(s)
    await session.commit()
    return s


def _fwd(uri, **h):
    return {"x-forwarded-uri": uri, "x-forwarded-proto": "https",
            "x-forwarded-host": "localhost", "sec-fetch-mode": "navigate", **h}


@pytest.mark.asyncio
async def test_anonymous_navigation_redirects_to_login(session):
    await _svc(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 302
    assert r.headers["location"] == "https://localhost/login?next=/sonarr/"


@pytest.mark.asyncio
async def test_anonymous_xhr_401(session):
    await _svc(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/services/sonarr/auth-check",
                        headers={"x-forwarded-uri": "/sonarr/x", "accept": "application/json"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_bypass_with_header_allows_anonymous(session):
    await _svc(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.get("/api/services/sonarr/auth-check",
                        headers=_fwd("/sonarr/api/v3/series?x=1", **{"X-Api-Key": "k"}))
        assert r.status_code == 200
        r = await c.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/api/v3/series"))
        assert r.status_code == 302


@pytest.mark.asyncio
async def test_member_allowed_when_no_groups_required(member_client, session):
    await _svc(session)
    r = await member_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-user"] == "member"


@pytest.mark.asyncio
async def test_member_denied_then_allowed_by_group(member_client, session):
    await _svc(session, allowed_groups=["media"])
    r = await member_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 403
    g = Group(name="media")
    session.add(g)
    await session.commit()
    user = (await session.exec(select(User).where(User.username == "member"))).first()
    session.add(UserGroup(user_id=user.id, group_id=g.id))
    await session.commit()
    r = await member_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200
    assert r.headers["x-styx-groups"] == "media"


@pytest.mark.asyncio
async def test_admin_always_allowed(admin_client, session):
    await _svc(session, allowed_groups=["nobody"])
    r = await admin_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_disabled_or_unknown_404(admin_client, session):
    await _svc(session, enabled=False)
    r = await admin_client.get("/api/services/sonarr/auth-check", headers=_fwd("/sonarr/"))
    assert r.status_code == 404
    r = await admin_client.get("/api/services/nope/auth-check", headers=_fwd("/nope/"))
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_enter_sets_cookie_and_exit_clears(member_client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso", bypass_rules=[])
    r = await member_client.post("/api/services/unraid/enter")
    assert r.status_code == 200
    assert "styx_svc=unraid" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"]
    r = await member_client.get("/_styx/exit", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/"
    assert "styx_svc=;" in r.headers["set-cookie"] or 'styx_svc=""' in r.headers["set-cookie"]


@pytest.mark.asyncio
async def test_enter_denied_without_group(member_client, session):
    await _svc(session, slug="unraid", mount_mode="cookie-root", auth_mode="sso",
               bypass_rules=[], allowed_groups=["ops"])
    r = await member_client.post("/api/services/unraid/enter")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_enter_rejects_path_mode(member_client, session):
    await _svc(session)
    r = await member_client.post("/api/services/sonarr/enter")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_unavailable_page(client):
    r = await client.get("/api/service-unavailable")
    assert r.status_code == 503 and "text/html" in r.headers["content-type"]
```

- [ ] **Step 2: Run, expect 404s**

- [ ] **Step 3: Add `session_user_or_none` to `deps.py`**

Append to `backend/app/security/deps.py`:

```python
async def session_user_or_none(request: Request, session: AsyncSession) -> User | None:
    """Same checks as get_current_user, but None instead of 401 (forwardAuth use)."""
    try:
        return await get_current_user(request, session)
    except HTTPException:
        return None
```

- [ ] **Step 4: Implement `services_auth.py`**

```python
# backend/app/routers/services_auth.py
"""Traefik forwardAuth target, cookie-root enter/exit, unavailable page (spec §4.2, §5)."""
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import get_session
from app.models import ProxiedService, User
from app.routers.groups import user_group_names
from app.routers.workstations import _redirect_host
from app.security.deps import get_current_user, session_user_or_none
from app.services.service_routes import COOKIE_NAME

router = APIRouter()
exit_router = APIRouter()


async def get_service_by_slug(session: AsyncSession, slug: str) -> ProxiedService | None:
    return (await session.exec(select(ProxiedService).where(ProxiedService.slug == slug))).first()


def bypass_matches(rules: list[dict], uri: str, headers) -> bool:
    path = uri.split("?", 1)[0]
    for rule in rules:
        if not path.startswith(rule.get("path_prefix", "/")):
            continue
        hdr = rule.get("required_header")
        if not hdr or hdr.lower() in headers:
            return True
    return False


async def user_may_open(session: AsyncSession, user: User, svc: ProxiedService) -> bool:
    if user.role == "admin" or not svc.allowed_groups:
        return True
    names = await user_group_names(session, user.id)
    return bool(set(names) & set(svc.allowed_groups))


def _login_redirect(request: Request, uri: str):
    is_nav = (request.headers.get("sec-fetch-mode") == "navigate"
              or "text/html" in request.headers.get("accept", ""))
    if not is_nav:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    proto = request.headers.get("x-forwarded-proto", "https")
    if proto not in ("http", "https"):
        proto = "https"
    target = f"{proto}://{_redirect_host(request)}/login"
    # relative, same-host paths only (no open redirect)
    if re.match(r"^/[a-z0-9._-]*(/|$)", uri):
        target += f"?next={quote(uri, safe='/?=&')}"
    return RedirectResponse(target, status_code=302)


@router.get("/{slug}/auth-check")
async def auth_check(slug: str, request: Request,
                     session: AsyncSession = Depends(get_session)):
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    uri = request.headers.get("x-forwarded-uri", "/")
    if svc.auth_mode == "sso-with-bypass" and bypass_matches(svc.bypass_rules, uri, request.headers):
        return Response(status_code=200)
    user = await session_user_or_none(request, session)
    if user is None:
        return _login_redirect(request, uri)
    if not await user_may_open(session, user, svc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this service")
    groups = await user_group_names(session, user.id)
    return Response(status_code=200,
                    headers={"X-Styx-User": user.username, "X-Styx-Groups": ",".join(groups)})


@router.post("/{slug}/enter")
async def enter_service(slug: str, request: Request, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown service")
    if svc.mount_mode != "cookie-root":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Service is not cookie-root mounted")
    if not await user_may_open(session, user, svc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No access to this service")
    resp = Response(status_code=200)
    resp.set_cookie(COOKIE_NAME, slug, path="/", httponly=True, secure=True, samesite="lax")
    return resp


@exit_router.get("/exit")
async def exit_service():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(COOKIE_NAME, path="/")
    return resp


_UNAVAILABLE_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Service unavailable</title>
<style>body{font-family:system-ui;background:#0b0f14;color:#e6edf3;display:grid;
place-items:center;height:100vh;margin:0}main{text-align:center}a{color:#7aa2f7}</style>
</head><body><main><h1>Service unavailable</h1>
<p>Styx could not reach this service. It may be stopped or still starting.</p>
<p><a href="/_styx/exit">Back to Styx</a></p></main></body></html>"""


@pages_router.get("/service-unavailable", include_in_schema=False)
async def service_unavailable():
    return HTMLResponse(_UNAVAILABLE_HTML, status_code=503)
```

Add `pages_router = APIRouter()` next to `exit_router = APIRouter()`. Its full path becomes `/api/service-unavailable`, which is what the Traefik errors middleware in Task 4 queries.

Register in `backend/app/main.py`:

```python
from app.routers import services_auth as services_auth_router
...
app.include_router(services_auth_router.router, prefix="/api/services", tags=["services"])
app.include_router(services_auth_router.exit_router, prefix="/_styx", tags=["services"])
app.include_router(services_auth_router.pages_router, prefix="/api", tags=["services"])
```

Add `"/_styx/exit"` nothing to CSRF: it is a GET. `POST /api/services/{slug}/enter` goes through CSRF like every other POST (the frontend wrapper sends the header).

- [ ] **Step 5: Run tests + ruff, expect PASS. Commit**

```bash
git add backend/app/security/deps.py backend/app/routers/services_auth.py backend/app/main.py backend/tests/test_services_auth_check.py
git commit -m "feat(services): forwardAuth auth-check, cookie-root enter/exit"
```

---

### Task 6: Services CRUD router with docker network attach

**Files:**
- Modify: `backend/app/services/docker_manager.py` (add `connect_to_network`, `list_containers`)
- Create: `backend/app/routers/services.py`
- Modify: `backend/app/main.py` (register at `/api/services`, before `services_auth` so `/presets` and `/discover` are not swallowed by `/{slug}/...` — FastAPI matches in registration order)
- Test: `backend/tests/test_services_api.py`

**Interfaces:**
- Consumes: Task 1 schemas, `refresh_routes_from_db` (Task 4), `user_may_open` (Task 5).
- Produces: `GET /api/services` (any user, filtered), `POST`, `PUT /{id}`, `DELETE /{id}`, `POST /{id}/enable`, `POST /{id}/disable`, `GET /api/services/presets`, `GET /api/services/discover`; `def get_docker_manager()` in `routers/services.py` (override in tests); `DockerManager.connect_to_network(container: str, network: str | None = None) -> bool`; `DockerManager.list_containers() -> list[dict]`.

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_services_api.py
from unittest.mock import MagicMock
import pytest
from app.main import app
from app.routers import services as services_router


@pytest.fixture
def docker_mock():
    m = MagicMock()
    m.connect_to_network.return_value = True
    m.list_containers.return_value = [
        {"name": "sonarr", "image": "lscr.io/linuxserver/sonarr:latest", "ports": [8989],
         "networks": ["bridge"]},
        {"name": "random", "image": "nginx:1.27", "ports": [80], "networks": ["bridge"]},
    ]
    app.dependency_overrides[services_router.get_docker_manager] = lambda: m
    yield m
    app.dependency_overrides.pop(services_router.get_docker_manager, None)


@pytest.fixture(autouse=True)
def no_route_write(monkeypatch):
    calls = []
    async def fake(session):
        calls.append(1)
    monkeypatch.setattr("app.services.route_writer.refresh_routes_from_db", fake)
    return calls


def _body(**kw):
    d = {"slug": "sonarr", "name": "Sonarr", "kind": "url",
         "upstream_url": "http://10.0.0.2:8989", "mount_mode": "path", "auth_mode": "sso"}
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_crud_and_routes_refresh(admin_client, docker_mock, no_route_write):
    r = await admin_client.post("/api/services", json=_body())
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    assert len(no_route_write) == 1
    r = await admin_client.post("/api/services", json=_body())
    assert r.status_code == 409
    r = await admin_client.put(f"/api/services/{sid}", json=_body(name="Sonarr TV"))
    assert r.status_code == 200 and r.json()["name"] == "Sonarr TV"
    r = await admin_client.post(f"/api/services/{sid}/disable")
    assert r.status_code == 200 and r.json()["enabled"] is False
    r = await admin_client.delete(f"/api/services/{sid}")
    assert r.status_code == 204
    assert len(no_route_write) == 4


@pytest.mark.asyncio
async def test_reserved_slug_400(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_body(slug="api"))
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_docker_local_connects_network(admin_client, docker_mock):
    r = await admin_client.post("/api/services", json=_body(
        kind="docker-local", upstream_url=None, container="sonarr", container_port=8989))
    assert r.status_code == 201, r.text
    docker_mock.connect_to_network.assert_called_once_with("sonarr")
    assert r.json()["upstream_fallback"] is None


@pytest.mark.asyncio
async def test_docker_local_fallback_when_connect_fails(admin_client, docker_mock):
    docker_mock.connect_to_network.return_value = False
    r = await admin_client.post("/api/services", json=_body(
        kind="docker-local", upstream_url=None, container="sonarr", container_port=8989))
    assert r.status_code == 201
    assert r.json()["upstream_fallback"] == "http://host.docker.internal:8989"


@pytest.mark.asyncio
async def test_member_list_filtered_by_group(admin_client, member_client, docker_mock):
    await admin_client.post("/api/services", json=_body())
    await admin_client.post("/api/services", json=_body(slug="radarr", name="Radarr",
                                                         allowed_groups=["ops"]))
    r = await member_client.get("/api/services")
    assert [s["slug"] for s in r.json()] == ["sonarr"]
    r = await admin_client.get("/api/services")
    assert len(r.json()) == 2
    r = await member_client.post("/api/services", json=_body(slug="x"))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_presets_and_discover(admin_client, docker_mock, session):
    from app.database import seed_service_presets
    import os
    await seed_service_presets(session, os.path.join(
        os.path.dirname(__file__), "..", "..", "templates", "services"))
    r = await admin_client.get("/api/services/presets")
    assert any(p["id"] == "sonarr" for p in r.json())
    r = await admin_client.get("/api/services/discover")
    assert r.status_code == 200
    by_name = {c["name"]: c for c in r.json()}
    assert by_name["sonarr"]["suggested_preset"] == "sonarr"
    assert by_name["random"]["suggested_preset"] is None
```

- [ ] **Step 2: Run, expect failures**

- [ ] **Step 3: DockerManager methods**

Append to `class DockerManager` in `backend/app/services/docker_manager.py`:

```python
    def connect_to_network(self, container: str, network: str | None = None) -> bool:
        """Attach a container to the styx network so Traefik can reach it. False on failure."""
        try:
            net = self._client.networks.get(network or self._network_name)
            net.connect(container)
            return True
        except docker.errors.APIError as e:
            if "already exists" in str(e).lower():
                return True
            logger.warning("network connect failed for %s: %s", container, e)
            return False
        except docker.errors.NotFound:
            return False

    def disconnect_from_network(self, container: str, network: str | None = None) -> None:
        try:
            self._client.networks.get(network or self._network_name).disconnect(container)
        except docker.errors.DockerException:
            pass

    def list_containers(self) -> list[dict]:
        """Running containers not managed by Styx and not part of the Styx compose stack."""
        own_project = None
        try:
            own_project = self._client.containers.get(TRAEFIK_CONTAINER).labels.get(
                "com.docker.compose.project")
        except docker.errors.DockerException:
            pass
        out = []
        for c in self._client.containers.list():
            labels = c.labels or {}
            if labels.get("styx-portal.managed") == "true":
                continue
            if own_project and labels.get("com.docker.compose.project") == own_project:
                continue
            ports = sorted({int(p.split("/")[0]) for p in
                            (c.attrs.get("Config", {}).get("ExposedPorts") or {})})
            nets = list((c.attrs.get("NetworkSettings", {}).get("Networks") or {}).keys())
            image = c.image.tags[0] if c.image.tags else str(c.image.id)
            out.append({"name": c.name, "image": image, "ports": ports, "networks": nets})
        return out
```

(`logger` and `docker` are already imported in that module; if `logger` is not, add `logger = logging.getLogger("styx-portal")`.)

- [ ] **Step 4: Implement router**

```python
# backend/app/routers/services.py
"""Admin CRUD for proxied services (spec §6, §8)."""
import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Settings
from app.database import get_session
from app.models import ProxiedService, ServicePreset, User
from app.routers.services_auth import user_may_open
from app.schemas import (DiscoveredContainer, ProxiedServiceCreate, ProxiedServiceOut,
                         ProxiedServiceUpdate, ServicePresetOut)
from app.security.deps import get_current_user, require_admin
from app.services.audit import audit_request
from app.services.docker_manager import DockerManager

router = APIRouter()
_settings = Settings()


def get_docker_manager() -> DockerManager:
    return DockerManager(network_name=_settings.DOCKER_NETWORK)


def _iso(d: datetime | None) -> str | None:
    return d.isoformat() if d else None


def _out(s: ProxiedService) -> ProxiedServiceOut:
    return ProxiedServiceOut(
        id=s.id, slug=s.slug, name=s.name, icon=s.icon, kind=s.kind,
        upstream_url=s.upstream_url, container=s.container, container_port=s.container_port,
        upstream_fallback=s.upstream_fallback, mount_mode=s.mount_mode, auth_mode=s.auth_mode,
        bypass_rules=s.bypass_rules, allowed_groups=s.allowed_groups, verify_tls=s.verify_tls,
        health_path=s.health_path, health_status=s.health_status,
        health_checked_at=_iso(s.health_checked_at), preset_id=s.preset_id, enabled=s.enabled,
        created_at=_iso(s.created_at) or "", updated_at=_iso(s.updated_at) or "")


async def _refresh(session: AsyncSession) -> None:
    from app.services import route_writer
    await route_writer.refresh_routes_from_db(session)


async def _get_or_404(session: AsyncSession, sid: str) -> ProxiedService:
    s = await session.get(ProxiedService, sid)
    if s is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Service not found")
    return s


async def _attach_docker(s: ProxiedService, docker: DockerManager) -> None:
    """docker-local: join the styx network; fall back to host.docker.internal."""
    if s.kind != "docker-local":
        s.upstream_fallback = None
        return
    ok = await asyncio.to_thread(docker.connect_to_network, s.container)
    # ponytail: fallback assumes the host published the same port number;
    # SP4 (deploy-from-template) owns ports and removes the guess.
    s.upstream_fallback = None if ok else f"http://host.docker.internal:{s.container_port}"


@router.get("/presets", response_model=list[ServicePresetOut])
async def list_presets(user: User = Depends(get_current_user),
                       session: AsyncSession = Depends(get_session)):
    return (await session.exec(select(ServicePreset).order_by(ServicePreset.name))).all()


@router.get("/discover", response_model=list[DiscoveredContainer])
async def discover(admin: User = Depends(require_admin),
                   session: AsyncSession = Depends(get_session),
                   docker: DockerManager = Depends(get_docker_manager)):
    preset_ids = [p.id for p in (await session.exec(select(ServicePreset))).all()]
    out = []
    for c in await asyncio.to_thread(docker.list_containers):
        hay = f"{c['name']} {c['image']}".lower()
        match = next((p for p in preset_ids if p in hay), None)
        out.append(DiscoveredContainer(**c, suggested_preset=match))
    return out


@router.get("", response_model=list[ProxiedServiceOut])
async def list_services(user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(ProxiedService).order_by(ProxiedService.name))).all()
    out = []
    for s in rows:
        if user.role == "admin" or (s.enabled and await user_may_open(session, user, s)):
            out.append(_out(s))
    return out


@router.post("", response_model=ProxiedServiceOut, status_code=201)
async def create_service(body: ProxiedServiceCreate, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager)):
    if (await session.exec(select(ProxiedService).where(ProxiedService.slug == body.slug))).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Slug already in use")
    s = ProxiedService(**body.model_dump(exclude={"bypass_rules"}),
                       bypass_rules=[r.model_dump() for r in body.bypass_rules])
    await _attach_docker(s, docker)
    session.add(s)
    await audit_request(session, request, "service.create", user_id=admin.id,
                        resource=s.id, detail={"slug": s.slug, "auth_mode": s.auth_mode,
                                               "mount_mode": s.mount_mode})
    await session.commit()
    await session.refresh(s)
    await _refresh(session)
    return _out(s)


@router.put("/{sid}", response_model=ProxiedServiceOut)
async def update_service(sid: str, body: ProxiedServiceUpdate, request: Request,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager)):
    s = await _get_or_404(session, sid)
    for k, v in body.model_dump(exclude={"bypass_rules"}).items():
        setattr(s, k, v)
    s.bypass_rules = [r.model_dump() for r in body.bypass_rules]
    s.updated_at = datetime.now(timezone.utc)
    await _attach_docker(s, docker)
    session.add(s)
    await audit_request(session, request, "service.update", user_id=admin.id,
                        resource=s.id, detail={"slug": s.slug, "auth_mode": s.auth_mode,
                                               "mount_mode": s.mount_mode})
    await session.commit()
    await session.refresh(s)
    await _refresh(session)
    return _out(s)


async def _set_enabled(sid, enabled, request, admin, session):
    s = await _get_or_404(session, sid)
    s.enabled = enabled
    s.updated_at = datetime.now(timezone.utc)
    session.add(s)
    await audit_request(session, request, "service.enable" if enabled else "service.disable",
                        user_id=admin.id, resource=s.id, detail={"slug": s.slug})
    await session.commit()
    await session.refresh(s)
    await _refresh(session)
    return _out(s)


@router.post("/{sid}/enable", response_model=ProxiedServiceOut)
async def enable_service(sid: str, request: Request, admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    return await _set_enabled(sid, True, request, admin, session)


@router.post("/{sid}/disable", response_model=ProxiedServiceOut)
async def disable_service(sid: str, request: Request, admin: User = Depends(require_admin),
                          session: AsyncSession = Depends(get_session)):
    return await _set_enabled(sid, False, request, admin, session)


@router.delete("/{sid}", status_code=204)
async def delete_service(sid: str, request: Request, admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session),
                         docker: DockerManager = Depends(get_docker_manager)):
    s = await _get_or_404(session, sid)
    if s.kind == "docker-local" and not s.upstream_fallback:
        await asyncio.to_thread(docker.disconnect_from_network, s.container)
    await session.delete(s)
    await audit_request(session, request, "service.delete", user_id=admin.id,
                        resource=sid, detail={"slug": s.slug})
    await session.commit()
    await _refresh(session)
    return Response(status_code=204)
```

Register in `main.py` **before** the `services_auth` line (static paths `/presets`, `/discover` must be matched before `/{slug}/auth-check`):

```python
from app.routers import services as services_router
...
app.include_router(services_router.router, prefix="/api/services", tags=["services"])
app.include_router(services_auth_router.router, prefix="/api/services", tags=["services"])
```

- [ ] **Step 5: Run full suite + ruff, expect PASS. Commit**

```bash
git add backend/app/services/docker_manager.py backend/app/routers/services.py backend/app/main.py backend/tests/test_services_api.py
git commit -m "feat(services): admin CRUD, discovery, docker network attach"
```

---

### Task 7: Health loop

**Files:**
- Create: `backend/app/services/service_health.py`
- Modify: `backend/app/main.py` (`_service_health_loop`, task start/cancel in lifespan)
- Test: `backend/tests/test_service_health.py`

**Interfaces:**
- Consumes: `upstream_base` (Task 1).
- Produces: `async def check_url(url: str, verify: bool) -> str`; `async def run_health_pass(session, checker=check_url) -> int` (number of services checked).

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_service_health.py
import pytest
from app.models import ProxiedService
from app.services.service_health import run_health_pass


@pytest.mark.asyncio
async def test_health_pass_updates_status(session):
    a = ProxiedService(slug="a", name="A", upstream_url="http://10.0.0.1", health_path="/ping")
    b = ProxiedService(slug="b", name="B", upstream_url="https://10.0.0.2", health_path="/x",
                       verify_tls=False)
    c = ProxiedService(slug="c", name="C", upstream_url="http://10.0.0.3")   # no health_path
    d = ProxiedService(slug="d", name="D", upstream_url="http://10.0.0.4", health_path="/",
                       enabled=False)
    for s in (a, b, c, d):
        session.add(s)
    await session.commit()
    seen = []

    async def fake(url, verify):
        seen.append((url, verify))
        return "healthy" if url.startswith("http://10.0.0.1") else "unhealthy"

    n = await run_health_pass(session, checker=fake)
    assert n == 2
    assert seen == [("http://10.0.0.1/ping", True), ("https://10.0.0.2/x", False)]
    await session.refresh(a); await session.refresh(b); await session.refresh(c)
    assert (a.health_status, b.health_status, c.health_status) == ("healthy", "unhealthy", "unknown")
    assert a.health_checked_at is not None


@pytest.mark.asyncio
async def test_check_url_connection_error_is_unhealthy():
    from app.services.service_health import check_url
    assert await check_url("http://127.0.0.1:9", True) == "unhealthy"
```

- [ ] **Step 2: Run, expect ImportError**

- [ ] **Step 3: Implement**

```python
# backend/app/services/service_health.py
"""Polls proxied services' health_path (spec §7)."""
from datetime import datetime, timezone

import httpx
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import ProxiedService, upstream_base


async def check_url(url: str, verify: bool) -> str:
    try:
        async with httpx.AsyncClient(verify=verify, timeout=5.0, follow_redirects=False) as c:
            r = await c.get(url)
        return "healthy" if r.status_code < 400 else "unhealthy"
    except httpx.HTTPError:
        return "unhealthy"


async def run_health_pass(session: AsyncSession, checker=check_url) -> int:
    rows = (await session.exec(select(ProxiedService).where(
        ProxiedService.enabled == True))).all()  # noqa: E712
    checked = 0
    for s in rows:
        if not s.health_path:
            continue
        s.health_status = await checker(upstream_base(s) + s.health_path, s.verify_tls)
        s.health_checked_at = datetime.now(timezone.utc)
        session.add(s)
        checked += 1
    await session.commit()
    return checked
```

In `backend/app/main.py` add next to the other loops:

```python
async def _service_health_loop():
    from app.services.service_health import run_health_pass
    while True:
        await asyncio.sleep(30)
        try:
            async with async_session() as session:
                await run_health_pass(session)
        except Exception:
            pass
```

In lifespan: `svc_health_task = asyncio.create_task(_service_health_loop())` after `health_task = ...`, and `svc_health_task.cancel()` after `yield` alongside the others.

- [ ] **Step 4: Run tests + ruff, expect PASS. Commit**

```bash
git add backend/app/services/service_health.py backend/app/main.py backend/tests/test_service_health.py
git commit -m "feat(services): health polling loop"
```

---

### Task 8: Backend gate

- [ ] **Step 1: Full suite, lint, bandit**

```bash
cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app tests && .venv/bin/python -m bandit -c pyproject.toml -r app -ll -ii
```
Expected: all pass. If bandit flags `insecureSkipVerify`/`verify=False` usage, it is the per-service opt-in; add `# nosec B501` only on the exact `httpx.AsyncClient(verify=verify...)` line with a comment pointing at the admin toggle.

- [ ] **Step 2: Line-count check**

`wc -l backend/app/routers/services.py backend/app/routers/services_auth.py backend/app/services/service_routes.py backend/app/services/route_writer.py` — each under 500.

- [ ] **Step 3: Commit any fixes**

```bash
git commit -am "chore(services): backend gate fixes"
```

Then continue with `docs/superpowers/plans/2026-10-12-service-proxy-core-frontend.md`.
