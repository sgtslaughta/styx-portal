# Managed Mounts (SP1.5) — Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Styx configures app base paths itself (backup → apply → restart → verify → rollback), adds focus-mode open/confirm, native-app/identity options, and routes the shell.

**Architecture:** Pure config editors (`mount_edit.py`) + Docker archive read/write (`DockerManager`) + an asyncio job runner persisted in `mount_jobs` (`mount_jobs.py`) behind three admin endpoints (`routers/service_mounts.py`). Routing changes stay in `service_routes.py`; auth changes in `services_auth.py`.

**Tech Stack:** FastAPI, SQLModel/SQLite, docker-py (via socket-proxy, `POST=1` allows PUT archive), httpx, stdlib `tarfile`/`xml.etree`/`configparser`.

**Spec:** `docs/superpowers/specs/2026-10-13-managed-mounts-design.md` (+ SP1 spec `2026-10-12-service-proxy-core-design.md`)

Worktree: `/home/user/code/remote-access-mounts` · branch `feat/managed-mounts`. Run everything from `backend/`:
- tests: `.venv/bin/python -m pytest -q` (create venv first if missing: `python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'`)
- lint: `.venv/bin/python -m ruff check app/ tests/` (ruff pinned 0.15.14)

## Global Constraints

- Files < 500 lines. Semantic commits, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never recreate an adopted container. Writes only to preset-declared paths via the archive API.
- Adopted container (label `styx.managed` != `"true"`) → apply needs `consent: true`, else 409; consent audited.
- Backups in `<MOUNT_BACKUP_DIR>/<service_id>/<utc-ts>/`, keep last 5.
- Verify budget 90 s, interval 2 s; restart timeout 30 s; log excerpt = last 20 lines.
- `/_styx/open` GET only for `Sec-Fetch-Site` in {`same-origin`, `none`}; otherwise confirm page + CSRF POST.
- `Clear-Site-Data: "cache"` (never `"storage"`).
- Shell router: `Host(domain) && PathPrefix(/_styx/app)` → `frontend`, priority 95.
- Service routers force `X-Frame-Options: SAMEORIGIN`.
- `env` subpath method is **not implemented** (no Styx-created service containers exist yet; spec §3.1 reserves it). Presets with only an env method stay manual.

## Review Focus

1. Config file missing at every declared path → plan reports "Styx can't find <app>'s settings file", apply refused (409), no backup dir created. (Task 4)
2. App already has the target base path → plan returns empty change list, apply finishes `done` without restart. (Task 4)
3. Backend restarts mid-job → job becomes `failed` "Interrupted — backup kept at …" on startup. (Task 5)
4. Two admins click Apply → second gets 409 "A change is already running". (Task 5)
5. Bypass header present but empty / wrong prefix (`Authorization: Bearer x` on Jellyfin) → normal Styx login, not bypass. (Task 6)

---

### Task 1: Model, schema and preset fields

**Files:**
- Modify: `app/models.py` (`ServicePreset`, `ProxiedService`, new `MountJob`)
- Modify: `app/database.py` (column migrations list; `seed_service_presets` → upsert)
- Modify: `app/schemas_services.py` (`BypassRule`, `_ServiceFields`, `ProxiedServiceOut`, `ServiceTileOut`, `ServicePresetOut`)
- Modify: `app/routers/services.py` (`_out`, `_tile`)
- Test: `tests/test_mount_models.py`

**Interfaces:**
- Produces: `ProxiedService.mount_managed: bool`, `.pass_identity: bool`, `.frame_ok: bool`; `ServicePreset.subpath: dict | None`; `BypassRule.header_prefix: str | None`, `BypassRule.required_query: str | None`; `MountJob` (fields below); tile gains `frame_ok`.

- [ ] **Step 1: Failing test** `tests/test_mount_models.py`

```python
import json
import pytest
from app.database import seed_service_presets
from app.models import MountJob, ProxiedService, ServicePreset
from app.schemas_services import BypassRule


def test_bypass_rule_accepts_prefix_and_query():
    r = BypassRule(path_prefix="/jellyfin/", required_header="Authorization",
                   header_prefix="MediaBrowser")
    assert r.header_prefix == "MediaBrowser"
    q = BypassRule(path_prefix="/jellyfin/", required_query="api_key")
    assert q.required_query == "api_key"


async def test_new_columns_default(session):
    s = ProxiedService(slug="x", name="X")
    session.add(s); await session.commit(); await session.refresh(s)
    assert (s.mount_managed, s.pass_identity, s.frame_ok) == (False, False, True)


async def test_mount_job_roundtrip(session):
    j = MountJob(service_id="s1", steps=[{"id": "plan", "label": "Plan", "state": "done"}])
    session.add(j); await session.commit(); await session.refresh(j)
    assert j.state == "pending" and j.steps[0]["id"] == "plan" and j.changes == []


async def test_seed_upserts_existing_preset(session, tmp_path):
    session.add(ServicePreset(id="sonarr", name="Old")); await session.commit()
    (tmp_path / "sonarr.json").write_text(json.dumps(
        {"id": "sonarr", "name": "Sonarr", "subpath": {"methods": []}}))
    await seed_service_presets(session, str(tmp_path))
    p = await session.get(ServicePreset, "sonarr")
    await session.refresh(p)
    assert p.name == "Sonarr" and p.subpath == {"methods": []}
```

- [ ] **Step 2:** `.venv/bin/python -m pytest tests/test_mount_models.py -q` → FAIL (ImportError MountJob).

- [ ] **Step 3: Implement**

`app/models.py` — add to `ServicePreset`:
```python
    subpath: dict | None = Field(default=None, sa_column=Column(JSON))
```
add to `ProxiedService` (after `enabled`):
```python
    mount_managed: bool = False   # Styx set the app's base path (spec §3)
    pass_identity: bool = False   # forward X-Styx-User/Email/Groups upstream
    frame_ok: bool = True         # False = "Open without overlay"
```
new model at end of file:
```python
class MountJob(SQLModel, table=True):
    """One base-path apply run (spec §3.2). steps: [{id,label,state,detail}]."""
    __tablename__ = "mount_jobs"
    id: str = Field(default_factory=_uuid, primary_key=True)
    service_id: str = Field(index=True)
    state: str = "pending"        # pending|running|done|rolled_back|failed
    steps: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    changes: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    backup_dir: str | None = None
    log_excerpt: str | None = None
    created_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
```

`app/database.py` — append to the `migrations` list:
```python
        ("service_presets", "subpath", "JSON"),
        ("proxied_services", "mount_managed", "BOOLEAN NOT NULL DEFAULT 0"),
        ("proxied_services", "pass_identity", "BOOLEAN NOT NULL DEFAULT 0"),
        ("proxied_services", "frame_ok", "BOOLEAN NOT NULL DEFAULT 1"),
```
and replace the body of `seed_service_presets`' loop (presets are not user-editable, so upsert is safe and lets preset fixes reach existing installs):
```python
        existing = await session.get(ServicePreset, data["id"])
        if existing is None:
            session.add(ServicePreset(**data))
            continue
        for k, v in data.items():
            setattr(existing, k, v)
        session.add(existing)
```
Update its docstring to "Upsert of templates/services/*.json into service_presets (built-in, read-only)."

`app/schemas_services.py`:
```python
class BypassRule(BaseModel):
    path_prefix: str = Field(min_length=1, max_length=255)
    required_header: str | None = Field(default=None, max_length=64)
    header_prefix: str | None = Field(default=None, max_length=64)   # header value must start with this
    required_query: str | None = Field(default=None, max_length=64)  # query param must be present & non-empty
```
`_ServiceFields`: add `mount_managed: bool = False`, `pass_identity: bool = False`, `frame_ok: bool = True`.
`ProxiedServiceOut`: add `mount_managed: bool`, `pass_identity: bool`, `frame_ok: bool`.
`ServiceTileOut`: add `frame_ok: bool = True`.
`ServicePresetOut`: add `subpath: dict | None = None`.
`app/routers/services.py` `_tile`: pass `frame_ok=s.frame_ok`. (`_out` uses model fields — add the three if it lists fields explicitly.)

- [ ] **Step 4:** run test file + full suite → PASS. `ruff check`.
- [ ] **Step 5: Commit** `feat(services): mount_managed/pass_identity/frame_ok fields, mount_jobs table, preset upsert`

---

### Task 2: Config editors

**Files:**
- Create: `app/services/mount_edit.py`
- Modify: `backend/pyproject.toml` (add `defusedxml`)
- Test: `tests/test_mount_edit.py`

**Interfaces:**
- Produces: `edit_config(text: str, fmt: str, key: str, value: str) -> tuple[str, str | None]` returns `(new_text, old_value)`; `read_config(text, fmt, key) -> str | None`. `fmt` ∈ `xml|json|ini`. `key`: xml = path like `/Config/UrlBase` (root tag must match, missing child created); json = dotted `a.b`; ini = `section.key`. Raises `ValueError` on unparsable text or root mismatch.

- [ ] **Step 1: Failing test**

```python
import json
import pytest
from app.services.mount_edit import edit_config, read_config

XML = "<?xml version='1.0' encoding='utf-8'?>\n<Config>\n  <Port>8989</Port>\n  <UrlBase></UrlBase>\n</Config>"


def test_xml_set_existing():
    new, old = edit_config(XML, "xml", "/Config/UrlBase", "/sonarr")
    assert old == "" and read_config(new, "xml", "/Config/UrlBase") == "/sonarr"
    assert "<Port>8989</Port>" in new


def test_xml_creates_missing_child():
    new, old = edit_config("<NetworkConfiguration/>", "xml", "/NetworkConfiguration/BaseUrl", "/jellyfin")
    assert old is None and read_config(new, "xml", "/NetworkConfiguration/BaseUrl") == "/jellyfin"


def test_xml_root_mismatch_raises():
    with pytest.raises(ValueError):
        edit_config("<Other/>", "xml", "/Config/UrlBase", "/x")


def test_xml_rejects_entities():   # no XXE / billion laughs
    with pytest.raises(ValueError):
        edit_config('<!DOCTYPE a [<!ENTITY e "x">]><Config>&e;</Config>', "xml", "/Config/UrlBase", "/x")


def test_json_dotted():
    new, old = edit_config(json.dumps({"server": {"base": "/"}}), "json", "server.base", "/abs")
    assert old == "/" and json.loads(new)["server"]["base"] == "/abs"


def test_ini_section_key():
    new, old = edit_config("[http]\nroot = /\n", "ini", "http.root", "/app")
    assert old == "/" and read_config(new, "ini", "http.root") == "/app"


def test_garbage_raises():
    with pytest.raises(ValueError):
        edit_config("{not json", "json", "a", "b")
```

- [ ] **Step 2:** run → FAIL (module missing).
- [ ] **Step 3: Implement.** Add `"defusedxml>=0.7.1"` to `dependencies` in `backend/pyproject.toml` and `.venv/bin/pip install -e '.[dev]'`. Then `app/services/mount_edit.py`:

```python
"""Edit one value in an app config file (spec §3.1). Pure functions, no I/O."""
import configparser
import io
import json
import xml.etree.ElementTree as ET   # building/serialising only

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException


def _xml_parts(key: str) -> list[str]:
    parts = [p for p in key.split("/") if p]
    if len(parts) < 2:
        raise ValueError(f"xml key needs /Root/Child: {key}")
    return parts


def _xml_root(text: str) -> ET.Element:
    try:
        return DET.fromstring(text, forbid_dtd=True)   # no XXE / entity expansion
    except (ET.ParseError, DefusedXmlException) as e:
        raise ValueError(f"bad xml: {e}") from e


def read_config(text: str, fmt: str, key: str) -> str | None:
    if fmt == "xml":
        parts = _xml_parts(key)
        root = _xml_root(text)
        if root.tag != parts[0]:
            raise ValueError(f"root is <{root.tag}>, expected <{parts[0]}>")
        node = root.find("/".join(parts[1:]))
        return None if node is None else (node.text or "")
    if fmt == "json":
        try:
            cur = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"bad json: {e}") from e
        for k in key.split("."):
            if not isinstance(cur, dict) or k not in cur:
                return None
            cur = cur[k]
        return None if cur is None else str(cur)
    if fmt == "ini":
        cp = _ini(text)
        sec, _, k = key.partition(".")
        return cp.get(sec, k, fallback=None)
    raise ValueError(f"unknown format {fmt}")


def _ini(text: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str  # keep key case
    try:
        cp.read_string(text)
    except configparser.Error as e:
        raise ValueError(f"bad ini: {e}") from e
    return cp


def edit_config(text: str, fmt: str, key: str, value: str) -> tuple[str, str | None]:
    old = read_config(text, fmt, key)
    if fmt == "xml":
        parts = _xml_parts(key)
        root = _xml_root(text)
        node = root
        for tag in parts[1:]:
            child = node.find(tag)
            node = child if child is not None else ET.SubElement(node, tag)
        node.text = value
        decl = "<?xml version='1.0' encoding='utf-8'?>\n" if text.lstrip().startswith("<?xml") else ""
        return decl + ET.tostring(root, encoding="unicode"), old
    if fmt == "json":
        data = json.loads(text)
        cur = data
        *path, last = key.split(".")
        for k in path:
            cur = cur.setdefault(k, {})
        cur[last] = value
        return json.dumps(data, indent=2) + "\n", old
    cp = _ini(text)
    sec, _, k = key.partition(".")
    if not cp.has_section(sec):
        cp.add_section(sec)
    cp.set(sec, k, value)
    buf = io.StringIO()
    cp.write(buf)
    return buf.getvalue(), old
```

- [ ] **Step 4:** tests PASS, ruff clean.
- [ ] **Step 5: Commit** `feat(services): config editors for xml/json/ini base-path keys`

---

### Task 3: Docker archive read/write

**Files:**
- Modify: `app/services/docker_manager.py` (add 3 methods after `restart_container`)
- Test: `tests/test_docker_archive.py`

**Interfaces:**
- Produces: `DockerManager.read_file(container: str, path: str) -> tuple[bytes, tarfile.TarInfo] | None` (None if missing); `DockerManager.write_file(container: str, path: str, data: bytes, like: tarfile.TarInfo) -> None` (keeps mode/uid/gid of `like`); `DockerManager.container_labels(container: str) -> dict`; `DockerManager.container_logs(container: str, tail: int = 20) -> str`.

- [ ] **Step 1: Failing test** (mocks docker-py container)

```python
import io
import tarfile
from unittest.mock import MagicMock
import docker.errors
from app.services.docker_manager import DockerManager


def _tar(name: str, data: bytes) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        ti = tarfile.TarInfo(name); ti.size = len(data); ti.mode = 0o640; ti.uid = 911; ti.gid = 911
        t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def _dm(container):
    dm = DockerManager.__new__(DockerManager)
    client = MagicMock(); client.containers.get.return_value = container
    dm._client = lambda: client
    return dm


def test_read_file_returns_bytes_and_info():
    c = MagicMock(); c.get_archive.return_value = (iter([_tar("config.xml", b"<Config/>")]), {})
    data, info = _dm(c).read_file("sonarr", "/config/config.xml")
    assert data == b"<Config/>" and info.uid == 911 and info.mode == 0o640


def test_read_missing_returns_none():
    c = MagicMock(); c.get_archive.side_effect = docker.errors.NotFound("x")
    assert _dm(c).read_file("sonarr", "/nope") is None


def test_write_file_preserves_owner():
    c = MagicMock(); like = tarfile.TarInfo("config.xml"); like.uid = 911; like.gid = 911; like.mode = 0o640
    _dm(c).write_file("sonarr", "/config/config.xml", b"<Config>x</Config>", like)
    dest, blob = c.put_archive.call_args.args
    assert dest == "/config"
    ti = tarfile.open(fileobj=io.BytesIO(blob)).getmember("config.xml")
    assert (ti.uid, ti.mode, ti.size) == (911, 0o640, len(b"<Config>x</Config>"))
```

- [ ] **Step 2:** run → FAIL (AttributeError).
- [ ] **Step 3: Implement** (add `import io, posixpath, tarfile` at top)

```python
    def read_file(self, container: str, path: str):
        """(bytes, TarInfo) of one file inside a container, or None if absent."""
        try:
            stream, _ = self._client().containers.get(container).get_archive(path)
        except docker.errors.NotFound:
            return None
        tf = tarfile.open(fileobj=io.BytesIO(b"".join(stream)))
        info = tf.getmembers()[0]
        if not info.isfile():
            return None
        return tf.extractfile(info).read(), info

    def write_file(self, container: str, path: str, data: bytes, like: tarfile.TarInfo) -> None:
        """Replace one file, keeping the original mode/owner (spec §3.1)."""
        info = tarfile.TarInfo(posixpath.basename(path))
        info.size, info.mode, info.uid, info.gid = len(data), like.mode, like.uid, like.gid
        info.mtime = int(time.time())
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w") as tf:
            tf.addfile(info, io.BytesIO(data))
        self._client().containers.get(container).put_archive(posixpath.dirname(path), buf.getvalue())

    def container_labels(self, container: str) -> dict:
        return self._client().containers.get(container).labels or {}

    def container_logs(self, container: str, tail: int = 20) -> str:
        raw = self._client().containers.get(container).logs(tail=tail)
        return raw.decode("utf-8", "replace")
```
(`import time` if not already imported.) Note `restart_container(container_id)` already exists and takes a name too (docker-py `containers.get` accepts names); pass `timeout=30` by changing it to `self._client().containers.get(container_id).restart(timeout=30)` if it doesn't already.

- [ ] **Step 4:** PASS, ruff.
- [ ] **Step 5: Commit** `feat(docker): read/write single files via the archive API, labels and log tail`

---

### Task 4: Mount planner

**Files:**
- Create: `app/services/mount_jobs.py` (planner part; runner added in Task 5)
- Test: `tests/test_mount_plan.py`

**Interfaces:**
- Consumes: `edit_config`, `read_config` (Task 2); `DockerManager.read_file/container_labels` (Task 3).
- Produces:
```python
@dataclass
class MountPlan:
    method: str | None            # "config_file" | None (= manual)
    path: str | None              # container file chosen
    fmt: str | None
    key: str | None
    changes: list[dict]           # [{"target": path, "key": key, "old": str|None, "new": str}]
    needs_consent: bool
    reason: str | None            # human text when method is None or nothing to do
def plan_mount(svc: ProxiedService, preset: ServicePreset | None, docker) -> MountPlan  # sync, call via asyncio.to_thread
```
New value is always `f"/{svc.slug}"`.

- [ ] **Step 1: Failing test**

```python
import tarfile
from unittest.mock import MagicMock
from app.models import ProxiedService, ServicePreset
from app.services.mount_jobs import plan_mount

SUB = {"methods": [{"type": "config_file", "paths": ["/config/config/network.xml", "/config/network.xml"],
                    "format": "xml", "key": "/NetworkConfiguration/BaseUrl"}],
       "restart": True, "verify_path": "/{slug}/health"}


def _svc(**kw):
    return ProxiedService(slug="jellyfin", name="Jellyfin", kind="docker-local",
                          container="jellyfin", container_port=8096, **kw)


def _docker(files: dict, labels=None):
    d = MagicMock()
    d.read_file.side_effect = lambda c, p: (files[p].encode(), tarfile.TarInfo("f")) if p in files else None
    d.container_labels.return_value = labels or {}
    return d


def test_second_path_used_when_first_missing():
    p = plan_mount(_svc(), ServicePreset(id="jellyfin", name="J", subpath=SUB),
                   _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl/></NetworkConfiguration>"}))
    assert p.method == "config_file" and p.path == "/config/network.xml"
    assert p.changes == [{"target": "/config/network.xml", "key": "/NetworkConfiguration/BaseUrl",
                          "old": "", "new": "/jellyfin"}]
    assert p.needs_consent is True


def test_styx_managed_label_skips_consent():
    p = plan_mount(_svc(), ServicePreset(id="jellyfin", name="J", subpath=SUB),
                   _docker({"/config/network.xml": "<NetworkConfiguration/>"}, {"styx.managed": "true"}))
    assert p.needs_consent is False


def test_already_set_gives_no_changes():
    p = plan_mount(_svc(), ServicePreset(id="jellyfin", name="J", subpath=SUB),
                   _docker({"/config/network.xml": "<NetworkConfiguration><BaseUrl>/jellyfin</BaseUrl></NetworkConfiguration>"}))
    assert p.method == "config_file" and p.changes == [] and "already" in p.reason


def test_no_file_found_is_manual():
    p = plan_mount(_svc(), ServicePreset(id="jellyfin", name="J", subpath=SUB), _docker({}))
    assert p.method is None and "can't find" in p.reason


def test_url_kind_or_no_subpath_is_manual():
    assert plan_mount(ProxiedService(slug="x", name="X", kind="url"), None, MagicMock()).method is None
    assert plan_mount(_svc(), ServicePreset(id="x", name="X"), MagicMock()).method is None


def test_env_only_preset_is_manual():
    sub = {"methods": [{"type": "env", "var": "ROUTER_BASE_PATH"}]}
    assert plan_mount(_svc(), ServicePreset(id="abs", name="A", subpath=sub), _docker({})).method is None
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement** top of `app/services/mount_jobs.py`

```python
"""Managed base path: plan + apply job (spec §3.1, §3.2)."""
from dataclasses import dataclass, field

from app.models import ProxiedService, ServicePreset
from app.services.mount_edit import read_config


@dataclass
class MountPlan:
    method: str | None = None
    path: str | None = None
    fmt: str | None = None
    key: str | None = None
    changes: list[dict] = field(default_factory=list)
    needs_consent: bool = True
    reason: str | None = None


def plan_mount(svc: ProxiedService, preset: ServicePreset | None, docker) -> MountPlan:
    if svc.kind != "docker-local" or not svc.container:
        return MountPlan(reason="Styx can only configure apps running as local containers.")
    methods = [m for m in ((preset.subpath or {}).get("methods", []) if preset else [])
               if m.get("type") == "config_file"]   # ponytail: env method not implemented (spec §3.1)
    if not methods:
        return MountPlan(reason="This app can't be configured by Styx. Set its base path by hand.")
    needs_consent = docker.container_labels(svc.container).get("styx.managed") != "true"
    new = f"/{svc.slug}"
    for m in methods:
        for path in m["paths"]:
            got = docker.read_file(svc.container, path)
            if got is None:
                continue
            old = read_config(got[0].decode("utf-8"), m["format"], m["key"])
            plan = MountPlan("config_file", path, m["format"], m["key"], [], needs_consent)
            if old == new:
                plan.reason = f"Base path is already {new}."
            else:
                plan.changes = [{"target": path, "key": m["key"], "old": old, "new": new}]
            return plan
    return MountPlan(needs_consent=needs_consent,
                     reason=f"Styx can't find {preset.name}'s settings file in the container.")
```

- [ ] **Step 4:** PASS, ruff.
- [ ] **Step 5: Commit** `feat(services): plan a managed base path from preset subpath rules`

---

### Task 5: Apply job runner + endpoints

**Files:**
- Modify: `app/services/mount_jobs.py` (runner)
- Create: `app/routers/service_mounts.py`
- Modify: `app/main.py` (include router at `/api/services`, startup sweep)
- Modify: `app/config.py` (`MOUNT_BACKUP_DIR: str = "./data/mount-backups"`)
- Test: `tests/test_mount_jobs.py`, `tests/test_service_mounts_api.py`

**Interfaces:**
- Consumes: `plan_mount`, `MountPlan` (Task 4); `edit_config` (Task 2); docker methods (Task 3); `upstream_base(svc)` (models).
- Produces:
  - `STEPS = [("backup","Back up settings"),("apply","Apply base path"),("restart","Restart app"),("verify","Check it answers")]`
  - `async def run_job(job_id: str, svc_id: str, plan: MountPlan, docker, session_factory, http_get=None) -> None`
  - `async def sweep_interrupted(session) -> int`
  - Endpoints (admin): `POST /api/services/{sid}/mount/plan` → `{method, changes, needs_consent, reason}`; `POST /api/services/{sid}/mount/apply` body `{"consent": bool}` → 202 `{"job_id"}`; `GET /api/services/{sid}/mount/jobs/latest` → `MountJobOut {id,state,steps,changes,backup_dir,log_excerpt,created_at,finished_at}` or 404.

- [ ] **Step 1: Failing runner tests** `tests/test_mount_jobs.py`

```python
import tarfile
from unittest.mock import MagicMock
import pytest
from sqlmodel import select
from app.models import MountJob, ProxiedService
from app.services.mount_jobs import MountPlan, run_job, sweep_interrupted

XML = b"<Config><UrlBase></UrlBase></Config>"
PLAN = MountPlan("config_file", "/config/config.xml", "xml", "/Config/UrlBase",
                 [{"target": "/config/config.xml", "key": "/Config/UrlBase", "old": "", "new": "/sonarr"}], True)


@pytest.fixture
def factory(session):
    class F:
        async def __aenter__(self): return session
        async def __aexit__(self, *a): return False
    return lambda: F()


async def _setup(session, tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.mount_jobs._settings.MOUNT_BACKUP_DIR", str(tmp_path))
    monkeypatch.setattr("app.services.mount_jobs.VERIFY_BUDGET_S", 0.2)
    monkeypatch.setattr("app.services.mount_jobs.VERIFY_INTERVAL_S", 0.05)
    svc = ProxiedService(slug="sonarr", name="Sonarr", kind="docker-local", container="sonarr",
                         container_port=8989, preset_id="sonarr")
    job = MountJob(service_id=svc.id)
    session.add_all([svc, job]); await session.commit()
    d = MagicMock(); d.read_file.return_value = (XML, tarfile.TarInfo("config.xml"))
    d.container_logs.return_value = "boom"
    return svc, job, d


async def test_happy_path(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def ok(url): return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok)
    await session.refresh(job); await session.refresh(svc)
    assert job.state == "done" and [s["state"] for s in job.steps] == ["done"] * 4
    assert b"/sonarr" in d.write_file.call_args.args[2]
    assert (tmp_path / svc.id).is_dir() and svc.mount_managed is True


async def test_verify_fail_rolls_back(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    calls = []
    async def get(url):
        calls.append(url); return 404 if url.endswith("/sonarr/ping") else 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=get, verify_path="/sonarr/ping",
                  old_verify_path="/ping")
    await session.refresh(job)
    assert job.state == "rolled_back" and job.log_excerpt == "boom"
    assert d.write_file.call_args.args[2] == XML          # original restored
    assert d.restart_container.call_count == 2


async def test_rollback_failure_marks_failed(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    async def down(url): return 503
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=down)
    await session.refresh(job)
    assert job.state == "failed" and job.backup_dir


async def test_no_changes_finishes_without_restart(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    await run_job(job.id, svc.id, MountPlan("config_file", "/c", "xml", "/C/U", [], True), d, factory)
    await session.refresh(job)
    assert job.state == "done" and d.restart_container.call_count == 0


async def test_keeps_last_five_backups(session, tmp_path, monkeypatch, factory):
    svc, job, d = await _setup(session, tmp_path, monkeypatch)
    for i in range(6):
        (tmp_path / svc.id / f"2026010{i}T000000Z").mkdir(parents=True)
    async def ok(url): return 200
    await run_job(job.id, svc.id, PLAN, d, factory, http_get=ok)
    assert len(list((tmp_path / svc.id).iterdir())) == 5


async def test_sweep_marks_running_failed(session):
    session.add(MountJob(service_id="s", state="running", backup_dir="/b")); await session.commit()
    assert await sweep_interrupted(session) == 1
    j = (await session.exec(select(MountJob))).first()
    assert j.state == "failed" and "Interrupted" in j.log_excerpt and "/b" in j.log_excerpt
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement runner** (append to `mount_jobs.py`; add imports `asyncio, shutil, datetime, Path, httpx, Settings, edit_config, upstream_base, MountJob`, `_settings = Settings()`)

```python
STEPS = [("backup", "Back up settings"), ("apply", "Apply base path"),
         ("restart", "Restart app"), ("verify", "Check it answers")]
VERIFY_BUDGET_S = 90
VERIFY_INTERVAL_S = 2
KEEP_BACKUPS = 5


async def _default_get(url: str) -> int:
    async with httpx.AsyncClient(timeout=5, follow_redirects=False) as c:
        try:
            return (await c.get(url)).status_code
        except httpx.HTTPError:
            return 0


async def _verify(get, url: str) -> bool:
    loop = asyncio.get_running_loop()
    end = loop.time() + VERIFY_BUDGET_S
    while True:
        if 200 <= await get(url) < 400:
            return True
        if loop.time() >= end:
            return False
        await asyncio.sleep(VERIFY_INTERVAL_S)


def _prune(svc_dir: Path) -> None:
    for old in sorted(p for p in svc_dir.iterdir() if p.is_dir())[:-KEEP_BACKUPS]:
        shutil.rmtree(old, ignore_errors=True)


async def run_job(job_id, svc_id, plan, docker, session_factory, http_get=None,
                  verify_path=None, old_verify_path=None) -> None:
    get = http_get or _default_get
    steps = [{"id": i, "label": label, "state": "pending", "detail": None} for i, label in STEPS]

    async def save(state=None, **kw):
        async with session_factory() as s:
            job = await s.get(MountJob, job_id)
            job.steps = [dict(x) for x in steps]
            if state:
                job.state = state
            for k, v in kw.items():
                setattr(job, k, v)
            if state in ("done", "rolled_back", "failed"):
                job.finished_at = datetime.now(timezone.utc)
            s.add(job); await s.commit()

    def mark(step_id, state, detail=None):
        for x in steps:
            if x["id"] == step_id:
                x["state"], x["detail"] = state, detail

    async with session_factory() as s:
        svc = await s.get(ProxiedService, svc_id)
    base = upstream_base(svc)
    verify_path = verify_path or f"/{svc.slug}"
    if not plan.changes:
        for i, _ in STEPS:
            mark(i, "skipped")
        await save("done", changes=[])
        await _set_managed(session_factory, svc_id)
        return
    await save("running", changes=plan.changes)
    c, path = svc.container, plan.path
    original, info = await asyncio.to_thread(docker.read_file, c, path)
    svc_dir = Path(_settings.MOUNT_BACKUP_DIR) / svc_id
    bdir = svc_dir / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mark("backup", "active"); await save()
    bdir.mkdir(parents=True, exist_ok=True)
    (bdir / Path(path).name).write_bytes(original)
    _prune(svc_dir)
    mark("backup", "done", str(bdir)); mark("apply", "active"); await save(backup_dir=str(bdir))
    try:
        new_text, _ = edit_config(original.decode("utf-8"), plan.fmt, plan.key, plan.changes[0]["new"])
        await asyncio.to_thread(docker.write_file, c, path, new_text.encode("utf-8"), info)
        mark("apply", "done"); mark("restart", "active"); await save()
        await asyncio.to_thread(docker.restart_container, c)
        mark("restart", "done"); mark("verify", "active"); await save()
        if await _verify(get, base + verify_path):
            mark("verify", "done"); await save("done")
            await _set_managed(session_factory, svc_id)
            return
        mark("verify", "failed", f"No answer at {verify_path} after {VERIFY_BUDGET_S}s")
    except Exception as e:  # noqa: BLE001 - any failure triggers rollback
        for x in steps:
            if x["state"] == "active":
                x["state"], x["detail"] = "failed", str(e)
    logs = await asyncio.to_thread(docker.container_logs, c, 20)
    await save(log_excerpt=logs)
    try:
        await asyncio.to_thread(docker.write_file, c, path, original, info)
        await asyncio.to_thread(docker.restart_container, c)
        ok = await _verify(get, base + (old_verify_path or "/"))
    except Exception:  # noqa: BLE001
        ok = False
    await save("rolled_back" if ok else "failed")


async def _set_managed(session_factory, svc_id):
    async with session_factory() as s:
        svc = await s.get(ProxiedService, svc_id)
        svc.mount_managed = True
        s.add(svc); await s.commit()


async def sweep_interrupted(session) -> int:
    rows = (await session.exec(select(MountJob).where(MountJob.state == "running"))).all()
    for j in rows:
        j.state = "failed"
        j.log_excerpt = f"Interrupted — backup kept at {j.backup_dir}"
        j.finished_at = datetime.now(timezone.utc)
        session.add(j)
    await session.commit()
    return len(rows)
```
`old_verify_path`: the router passes the preset `health_path` with the slug prefix removed (health as it was before the base path), e.g. `/ping`; default `/`.

- [ ] **Step 4:** runner tests PASS.
- [ ] **Step 5: Failing API tests** `tests/test_service_mounts_api.py` (reuse `docker_mock` pattern from `test_services_api.py`)

```python
import tarfile
from unittest.mock import MagicMock
import pytest
from app.main import app
from app.models import AuditLog, ProxiedService, ServicePreset
from app.routers import services as services_router
from sqlmodel import select

SUB = {"methods": [{"type": "config_file", "paths": ["/config/config.xml"], "format": "xml",
                    "key": "/Config/UrlBase"}], "restart": True, "verify_path": "/{slug}/ping"}


@pytest.fixture
def dk(monkeypatch):
    d = MagicMock(); d.read_file.return_value = (b"<Config><UrlBase/></Config>", tarfile.TarInfo("c"))
    d.container_labels.return_value = {}
    app.dependency_overrides[services_router.get_docker_manager] = lambda: d
    started = []
    monkeypatch.setattr("app.routers.service_mounts._start", lambda *a, **k: started.append(a))
    yield d, started
    app.dependency_overrides.pop(services_router.get_docker_manager, None)


async def _svc(session):
    session.add(ServicePreset(id="sonarr", name="Sonarr", subpath=SUB))
    s = ProxiedService(slug="sonarr", name="Sonarr", kind="docker-local", container="sonarr",
                       container_port=8989, preset_id="sonarr")
    session.add(s); await session.commit(); return s


async def test_plan(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/plan")
    assert r.status_code == 200 and r.json()["needs_consent"] is True
    assert r.json()["changes"][0]["new"] == "/sonarr"


async def test_apply_requires_consent_for_adopted(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": False})
    assert r.status_code == 409


async def test_apply_with_consent_starts_and_audits(admin_client, session, dk):
    s = await _svc(session)
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 202 and r.json()["job_id"] and len(dk[1]) == 1
    logs = (await session.exec(select(AuditLog).where(AuditLog.action == "service.mount_apply"))).all()
    assert logs and "/sonarr" in str(logs[0].details)


async def test_second_apply_conflicts(admin_client, session, dk):
    s = await _svc(session)
    await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 409 and "already running" in r.json()["detail"]


async def test_manual_plan_cannot_apply(admin_client, session, dk):
    s = await _svc(session); dk[0].read_file.return_value = None
    r = await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    assert r.status_code == 409 and "can't find" in r.json()["detail"]


async def test_latest_job_and_member_forbidden(admin_client, member_client, session, dk):
    s = await _svc(session)
    assert (await admin_client.get(f"/api/services/{s.id}/mount/jobs/latest")).status_code == 404
    await admin_client.post(f"/api/services/{s.id}/mount/apply", json={"consent": True})
    j = (await admin_client.get(f"/api/services/{s.id}/mount/jobs/latest")).json()
    assert j["state"] == "pending" and j["changes"][0]["new"] == "/sonarr"
    assert (await member_client.post(f"/api/services/{s.id}/mount/plan")).status_code == 403
```
(If `AuditLog` stores details under another attribute name, use the one `audit_request` writes — check `app/services/audit.py`.)

- [ ] **Step 6:** run → FAIL.
- [ ] **Step 7: Implement** `app/routers/service_mounts.py`

```python
"""Managed base path endpoints (spec §3.2, §9). Admin only."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.database import async_session_factory, get_session
from app.models import MountJob, ServicePreset, User
from app.routers.services import _get_or_404, _iso, get_docker_manager
from app.security.deps import require_admin
from app.services.audit import audit_request
from app.services.docker_manager import DockerManager
from app.services.mount_jobs import plan_mount, run_job

router = APIRouter()
_tasks: set[asyncio.Task] = set()


class ApplyBody(BaseModel):
    consent: bool = False


def _start(*args, **kw) -> None:
    t = asyncio.create_task(run_job(*args, **kw))
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def _plan(session, sid, docker):
    svc = await _get_or_404(session, sid)
    preset = await session.get(ServicePreset, svc.preset_id) if svc.preset_id else None
    return svc, preset, await asyncio.to_thread(plan_mount, svc, preset, docker)


@router.post("/{sid}/mount/plan")
async def mount_plan(sid: str, admin: User = Depends(require_admin),
                     session: AsyncSession = Depends(get_session),
                     docker: DockerManager = Depends(get_docker_manager)):
    _, _, p = await _plan(session, sid, docker)
    return {"method": p.method, "changes": p.changes, "needs_consent": p.needs_consent, "reason": p.reason}


@router.post("/{sid}/mount/apply", status_code=202)
async def mount_apply(sid: str, body: ApplyBody, request: Request,
                      admin: User = Depends(require_admin),
                      session: AsyncSession = Depends(get_session),
                      docker: DockerManager = Depends(get_docker_manager)):
    running = (await session.exec(select(MountJob).where(
        MountJob.service_id == sid, MountJob.state.in_(["pending", "running"])))).first()
    if running:
        raise HTTPException(409, "A change is already running for this service")
    svc, preset, p = await _plan(session, sid, docker)
    if p.method is None:
        raise HTTPException(409, p.reason or "Nothing to apply")
    if p.needs_consent and not body.consent:
        raise HTTPException(409, "This container wasn't created by Styx. Confirm the change first.")
    job = MountJob(service_id=sid, changes=p.changes)
    session.add(job)
    await audit_request(session, request, "service.mount_apply", user_id=admin.id,
                        details={"service": svc.slug, "changes": p.changes, "consent": body.consent})
    await session.commit()
    verify = ((preset.subpath or {}).get("verify_path") or "/{slug}").format(slug=svc.slug)
    old = (preset.health_path or "/").removeprefix(f"/{svc.slug}") or "/"
    _start(job.id, sid, p, docker, async_session_factory, verify_path=verify, old_verify_path=old)
    return {"job_id": job.id}


@router.get("/{sid}/mount/jobs/latest")
async def mount_latest(sid: str, admin: User = Depends(require_admin),
                       session: AsyncSession = Depends(get_session)):
    job = (await session.exec(select(MountJob).where(MountJob.service_id == sid)
                              .order_by(MountJob.created_at.desc()))).first()
    if job is None:
        raise HTTPException(404, "No changes yet")
    return {"id": job.id, "state": job.state, "steps": job.steps, "changes": job.changes,
            "backup_dir": job.backup_dir, "log_excerpt": job.log_excerpt,
            "created_at": _iso(job.created_at), "finished_at": _iso(job.finished_at)}
```
Check names before wiring: the async session factory in `app/database.py` (grep `async_sessionmaker` / `sessionmaker`) — use whatever it's called; the audit call signature in `app/services/audit.py` (match how `services.py` calls it; if it commits itself, drop the explicit commit ordering accordingly). If `audit_request` takes `detail=` instead of `details=`, follow the file.

`app/main.py`: `app.include_router(service_mounts.router, prefix="/api/services", tags=["services"])` **before** the services router include (so `/{sid}/mount/...` isn't shadowed). In lifespan after `init_db()`:
```python
    async with async_session_factory() as s:
        n = await sweep_interrupted(s)
        if n:
            logger.warning("Marked %d interrupted mount job(s) failed", n)
```

- [ ] **Step 8:** API + runner tests PASS; full suite; ruff.
- [ ] **Step 9: Commit** `feat(services): managed base path apply job with backup, verify and rollback`

---

### Task 6: Auth-check — bypass prefix/query, identity, focus open

**Files:**
- Modify: `app/routers/services_auth.py` (`bypass_matches`, `auth_check`, new `open_service` GET/POST)
- Modify: `app/services/service_routes.py` (authResponseHeaders + `X-Styx-Email`)
- Test: `tests/test_services_auth_mounts.py`

**Interfaces:**
- Produces: `GET /api/services/focus` → `{"slug": str | null}`; `bypass_matches(rules, uri, headers)` honoring `header_prefix` (case-insensitive startswith on stripped value, empty value never matches) and `required_query`; auth-check returns identity headers only when `svc.pass_identity`; `GET/POST /_styx/open/{slug}`.

- [ ] **Step 1: Failing tests**

```python
import pytest
from app.models import ProxiedService
from app.routers.services_auth import bypass_matches

JF = [{"path_prefix": "/jellyfin/", "required_header": "Authorization", "header_prefix": "MediaBrowser"},
      {"path_prefix": "/jellyfin/", "required_header": "X-Emby-Token"},
      {"path_prefix": "/jellyfin/", "required_query": "api_key"}]


@pytest.mark.parametrize("uri,headers,ok", [
    ("/jellyfin/Users", {"authorization": 'MediaBrowser Client="x", Token="t"'}, True),
    ("/jellyfin/Users", {"authorization": "Bearer t"}, False),
    ("/jellyfin/Users", {"authorization": ""}, False),
    ("/jellyfin/Users", {"x-emby-token": "abc"}, True),
    ("/jellyfin/Users", {"x-emby-token": "  "}, False),
    ("/jellyfin/Videos/1/stream?api_key=abc", {}, True),
    ("/jellyfin/Videos/1/stream?api_key=", {}, False),
    ("/jellyfin/Videos/1/stream?other=1", {}, False),
    ("/sonarr/api", {"x-emby-token": "abc"}, False),
])
def test_bypass(uri, headers, ok):
    assert bypass_matches(JF, uri, headers) is ok


async def _svc(session, **kw):
    s = ProxiedService(slug="graf", name="Graf", upstream_url="http://g", **kw)
    session.add(s); await session.commit(); return s


async def test_identity_headers_only_when_opted_in(admin_client, session):
    await _svc(session)
    await _svc(session, slug="graf2", pass_identity=True)
    r = await admin_client.get("/internal/services/graf/auth-check", headers={"x-forwarded-uri": "/graf/"})
    assert r.status_code == 200 and "x-styx-user" not in r.headers
    r = await admin_client.get("/internal/services/graf2/auth-check", headers={"x-forwarded-uri": "/graf2/"})
    assert r.headers["x-styx-user"] == "admin" and "x-styx-email" in r.headers and "x-styx-groups" in r.headers


async def test_open_same_origin_sets_cookie_and_redirects(admin_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root")
    r = await admin_client.get("/_styx/open/immich", headers={"sec-fetch-site": "same-origin"},
                               follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("/_styx/app/immich/")
    await _svc(session, slug="ha", mount_mode="cookie-root", frame_ok=False)
    r2 = await admin_client.get("/_styx/open/ha", headers={"sec-fetch-site": "none"}, follow_redirects=False)
    assert r2.headers["location"].endswith("/")  and "/_styx/app" not in r2.headers["location"]
    assert "styx_svc=immich" in r.headers["set-cookie"] and r.headers["clear-site-data"] == '"cache"'


async def test_open_cross_site_shows_confirm(admin_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root")
    r = await admin_client.get("/_styx/open/immich", headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 200 and "<form" in r.text and "styx_svc" not in r.headers.get("set-cookie", "")


async def test_open_confirm_post_requires_csrf(admin_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root")
    r = await admin_client.post("/_styx/open/immich", headers={"x-csrf-token": "wrong"})
    assert r.status_code == 403


async def test_focus_reports_cookie(admin_client):
    assert (await admin_client.get("/api/services/focus")).json() == {"slug": None}
    admin_client.cookies.set("styx_svc", "immich")
    assert (await admin_client.get("/api/services/focus")).json() == {"slug": "immich"}


async def test_open_denied_without_group(member_client, session):
    await _svc(session, slug="immich", mount_mode="cookie-root", allowed_groups=["family"])
    r = await member_client.get("/_styx/open/immich", headers={"sec-fetch-site": "same-origin",
                                                              "accept": "text/html"})
    assert r.status_code == 403
```
For the CSRF test, look at `app/security/csrf.py` for how the double-submit token is checked (form field vs header) and send a mismatching value the way that module reads it.

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: Implement**

`bypass_matches` rule loop body:
```python
        q = rule.get("required_query")
        if q:
            vals = parse_qs(uri.split("?", 1)[1] if "?" in uri else "").get(q, [])
            if any(v.strip() for v in vals):
                return True
            continue
        hdr = rule.get("required_header")
        if not hdr:
            return True
        val = (headers.get(hdr.lower()) or "").strip()
        pre = rule.get("header_prefix")
        if val and (not pre or val.lower().startswith(pre.lower())):
            return True
```
(`from urllib.parse import parse_qs, quote, unquote`). `headers` may be a plain dict in tests and Starlette `Headers` in prod — both support `.get(lowercase)`.

`auth_check` final return:
```python
    hdrs = clean_cookie_header(request)
    if svc.pass_identity:
        groups = await user_group_names(session, user.id)
        hdrs |= {"X-Styx-User": user.username, "X-Styx-Email": user.email or "",
                 "X-Styx-Groups": ",".join(groups)}
    return Response(status_code=200, headers=hdrs)
```
(Traefik's `authResponseHeaders` only copies headers present in the response, so omitted = not forwarded; `styx-strip-identity` still blanks client copies.)

`service_routes.py`: forwardAuth `authResponseHeaders: ["X-Styx-User", "X-Styx-Email", "X-Styx-Groups", "Cookie"]`; add `"X-Styx-Email"` to `IDENTITY_HEADERS`.

Open endpoints on `exit_router` (mounted at `/_styx`):
```python
_CONFIRM_HTML = """...styled page (Task 8 style), text:
<h1>Open {name}?</h1><p>A link from another site wants to switch the app you have open.</p>
<form method="post"><input type="hidden" name="csrf_token" value="{csrf}">
<button>Open {name}</button></form><p><a href="/">Stay in Styx</a></p>"""


def _focus_response(svc) -> RedirectResponse:
    # frame_ok=False ("Open without overlay"): straight to the bare app at /
    resp = RedirectResponse(f"/_styx/app/{svc.slug}/" if svc.frame_ok else "/", status_code=302)
    resp.set_cookie(COOKIE_NAME, svc.slug, path="/", httponly=True,
                    secure=_settings.COOKIE_SECURE, samesite="lax")
    resp.headers["Clear-Site-Data"] = '"cache"'
    return resp


async def _open_target(slug, request, session):
    user = await proxy_user_or_none(request, session)
    if user is None:
        return None, login_redirect(request, f"/_styx/open/{slug}")
    svc = await get_service_by_slug(session, slug)
    if svc is None or not svc.enabled or svc.mount_mode != "cookie-root":
        raise HTTPException(404, "Unknown service")
    if not await user_may_open(session, user, svc):
        return None, no_access(request, "No access to this service")
    return svc, None


@exit_router.get("/open/{slug}")
async def open_service(slug: str, request: Request, session: AsyncSession = Depends(get_session)):
    svc, deny = await _open_target(slug, request, session)
    if deny:
        return deny
    if request.headers.get("sec-fetch-site", "none") in ("same-origin", "none"):
        return _focus_response(svc)
    csrf = request.cookies.get("csrf_token", "")
    return HTMLResponse(_CONFIRM_HTML.format(name=html.escape(svc.name), csrf=html.escape(csrf)),
                        headers={"Cache-Control": "no-store"})


@exit_router.post("/open/{slug}")
async def open_service_confirm(slug: str, request: Request, session: AsyncSession = Depends(get_session)):
    form = await request.form()
    if not request.cookies.get("csrf_token") or form.get("csrf_token") != request.cookies.get("csrf_token"):
        raise HTTPException(403, "CSRF check failed")
    svc, deny = await _open_target(slug, request, session)
    return deny or _focus_response(svc)
```
Current focus (cookie is HttpOnly, so the SPA asks), on the `/api/services` `router` in the same file:
```python
@router.get("/focus")
async def current_focus(request: Request, user: User = Depends(get_current_user)):
    return {"slug": request.cookies.get(COOKIE_NAME)}
```
Check whether the global CSRF middleware already guards POSTs under `/_styx` (see `app/security/csrf.py` exempt paths); if it does via header only, add `/_styx/open/` to its exempt list and keep the explicit form check above. Keep `POST /api/services/{slug}/enter` (SP1) working — the frontend switches to `/_styx/open` in the frontend plan.

- [ ] **Step 4:** PASS. Existing tests in `tests/test_services_auth_check.py` (and any other) that expect `X-Styx-User`/`X-Styx-Groups` by default now need `pass_identity=True` on their service — update them (identity is opt-in per spec §5). Full suite + ruff.
- [ ] **Step 5: Commit** `feat(services): native-app bypass by header prefix/query, opt-in identity headers, /_styx/open`

---

### Task 7: Routes — shell router and SAMEORIGIN frames

**Files:**
- Modify: `app/services/service_routes.py`
- Modify: `app/services/route_writer.py` (LAN router for `/_styx/app` if LAN serving mirrors routers — follow how `frontend-lan` is built)
- Test: `tests/test_route_writer_services.py` (add cases)

- [ ] **Step 1: Failing tests** (append; reuse that file's helper that builds `config` for a list of services — read its top first)

```python
def test_shell_router_above_focus_and_exit():
    cfg, mws = _build([_svc("immich", mount_mode="cookie-root")])
    r = cfg["http"]["routers"]["styx-shell"]
    assert r["service"] == "frontend" and r["priority"] == 95
    assert "PathPrefix(`/_styx/app`)" in r["rule"]
    assert r["priority"] > cfg["http"]["routers"]["styx-exit"]["priority"]


def test_service_routers_force_sameorigin():
    cfg, mws = _build([_svc("sonarr")])
    assert "styx-frame-sameorigin" in cfg["http"]["routers"]["svc-sonarr"]["middlewares"]
    assert mws["styx-frame-sameorigin"]["headers"]["customFrameOptionsValue"] == "SAMEORIGIN"
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implement** in `add_service_routes`: append `"styx-frame-sameorigin"` to `BASE_MW`; after the `if not emitted: return`:
```python
    middlewares["styx-frame-sameorigin"] = {"headers": {"customFrameOptionsValue": "SAMEORIGIN"}}
    routers["styx-shell"] = {"rule": f"Host(`{domain}`) && PathPrefix(`/_styx/app`)",
                             "service": "frontend", "priority": 95,
                             "middlewares": ["styx-ratelimit"], **transport}
```
(The shell is only useful when services exist, so it lives behind `emitted` with the other service routers.)

- [ ] **Step 4:** PASS; ruff.
- [ ] **Step 5: Commit** `feat(routes): shell router at /_styx/app and SAMEORIGIN frame option on services`

---

### Task 8: Presets + Styx-styled error pages

**Files:**
- Modify: `templates/services/{sonarr,radarr,lidarr,prowlarr,jellyfin}.json`
- Create: `templates/services/homeassistant.json`, `templates/services/immich.json`
- Create: `app/security/page_style.py`; Modify: `app/security/nav.py`, `app/routers/services_auth.py` (`_UNAVAILABLE_HTML`, `_CONFIRM_HTML`)
- Test: `tests/test_seed_service_presets.py` (add), `tests/test_page_style.py`

- [ ] **Step 1: Failing tests**

```python
# tests/test_seed_service_presets.py (append)
import json, pathlib
PRESETS = pathlib.Path(__file__).resolve().parents[2] / "templates" / "services"

def test_servarr_presets_have_config_file_subpath():
    for app in ("sonarr", "radarr", "lidarr", "prowlarr"):
        sub = json.loads((PRESETS / f"{app}.json").read_text())["subpath"]
        m = sub["methods"][0]
        assert m == {"type": "config_file", "paths": ["/config/config.xml"], "format": "xml",
                     "key": "/Config/UrlBase"}
        assert sub["verify_path"] == "/{slug}/ping"

def test_jellyfin_native_rules():
    p = json.loads((PRESETS / "jellyfin.json").read_text())
    hdrs = {r.get("required_header") for r in p["bypass_rules"]}
    assert {"Authorization", "X-Emby-Authorization", "X-Emby-Token", "X-MediaBrowser-Token"} <= hdrs
    assert any(r.get("required_query") == "api_key" for r in p["bypass_rules"])
    assert p["auth_mode"] == "sso"     # native apps are opt-in (spec §5)

def test_focus_presets():
    for app in ("homeassistant", "immich"):
        assert json.loads((PRESETS / f"{app}.json").read_text())["mount_mode"] == "cookie-root"

# tests/test_page_style.py
from app.security.page_style import styx_page

def test_page_has_tokens_and_both_schemes():
    html = styx_page("No access", "<p>x</p>")
    assert "#0F1C22" in html and "#EDF1EF" in html and "prefers-color-scheme" in html
    assert "<title>No access</title>" in html
```

- [ ] **Step 2:** FAIL.
- [ ] **Step 3: Implement**

Each servarr preset: add (keep existing fields)
```json
  "subpath": {
    "methods": [{"type": "config_file", "paths": ["/config/config.xml"], "format": "xml", "key": "/Config/UrlBase"}],
    "restart": true,
    "verify_path": "/{slug}/ping"
  },
```
Jellyfin preset: `"auth_mode": "sso"`, and
```json
  "bypass_rules": [
    {"path_prefix": "/jellyfin/", "required_header": "Authorization", "header_prefix": "MediaBrowser"},
    {"path_prefix": "/jellyfin/", "required_header": "X-Emby-Authorization", "header_prefix": "MediaBrowser"},
    {"path_prefix": "/jellyfin/", "required_header": "X-Emby-Token"},
    {"path_prefix": "/jellyfin/", "required_header": "X-MediaBrowser-Token"},
    {"path_prefix": "/jellyfin/", "required_query": "api_key"}
  ],
  "subpath": {
    "methods": [{"type": "config_file",
                 "paths": ["/config/config/network.xml", "/config/network.xml"],
                 "format": "xml", "key": "/NetworkConfiguration/BaseUrl"}],
    "restart": true,
    "verify_path": "/{slug}/health"
  },
  "warnings": ["Allow native apps lets Jellyfin apps sign in with Jellyfin's own login, so that login is reachable from the internet."]
```
`homeassistant.json`:
```json
{"id": "homeassistant", "name": "Home Assistant", "icon": "🏠", "default_port": 8123,
 "mount_mode": "cookie-root", "auth_mode": "sso", "bypass_rules": [], "health_path": "/manifest.json",
 "verify_tls": true, "base_url_hint": null,
 "warnings": ["Home Assistant only runs at the root of a site, so it opens on its own (one focus app at a time)."]}
```
`immich.json`: same shape, `"id": "immich"`, `"name": "Immich"`, `"icon": "🖼️"`, `"default_port": 2283`, `"health_path": "/api/server/ping"`, warning text with "Immich".

`app/security/page_style.py`:
```python
"""Shared look for the few pages the backend renders (spec §7 tokens)."""
_CSS = """
:root{--bg:#EDF1EF;--fg:#0F1C22;--muted:#4A5A60;--link:#2A767C;--btn:#2A767C;--btn-fg:#EDF1EF}
@media (prefers-color-scheme:dark){:root{--bg:#0F1C22;--fg:#EDF1EF;--muted:#9FB0B4;--link:#6FB7BC;--btn:#2A767C}}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;padding:16px;
background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}
main{max-width:34rem}h1{font-size:1.56rem;line-height:1.2;margin:0 0 .5rem;font-weight:600}
p{color:var(--muted)}a{color:var(--link)}button{font:inherit;background:var(--btn);color:var(--btn-fg);
border:0;border-radius:.5rem;padding:.6rem 1rem;cursor:pointer}button:focus-visible,a:focus-visible{outline:2px solid var(--link);outline-offset:2px}
"""


def styx_page(title: str, body: str) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{title}</title><style>{_CSS}</style></head><body><main>{body}</main></body></html>")
```
`nav.py`: `_NO_ACCESS_HTML = styx_page("No access", "<h1>No access</h1><p>Your account can't open this app. Ask an administrator to add you to its group.</p><p><a href=\"/_styx/exit\">Back to Styx</a></p>")`. Do the same for `_UNAVAILABLE_HTML` in `services_auth.py` (keep its current wording; link to `/_styx/exit`) and build `_CONFIRM_HTML` with `styx_page` (title "Open app?"). (System font here: these pages must work with nothing else loaded.)

- [ ] **Step 4:** PASS; full suite; ruff.
- [ ] **Step 5: Commit** `feat(services): managed-path presets, Home Assistant/Immich focus presets, Styx-styled pages`

---

### Task 9: Backend wrap-up

- [ ] Full suite `.venv/bin/python -m pytest -q` and `ruff check app/ tests/` clean.
- [ ] `wc -l` every touched file < 500 (split `services_auth.py` into `services_open.py` if it crossed 500).
- [ ] Update `CLAUDE.md` structure block: `service_mounts.py`, `mount_jobs.py`, `mount_edit.py`, `page_style.py`.
- [ ] Commit `docs: note managed mount modules in CLAUDE.md`.
