# Instances Configuration Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Two-tier instance configuration (zero-config easy mode + full advanced builder), custom templates (clone/registry/scratch) with owner sharing, a pragmatic expansion of the docker-option surface, admin-gated risk options, and path-prefix multi-port proxying.

**Architecture:** Backend (FastAPI/SQLModel) gains optional template fields that map to docker-py kwargs in `docker_manager`, an allowlist validator for the raw escape hatch, admin-gating in the templates router, a `shared` visibility flag, and extra-port path routers in `route_writer`. Frontend (React 19 + shadcn) gets a shared `TemplateBuilder` (left-rail sections + typed controls) mounted both inline in the launch modal (easy/advanced toggle) and on full-page routes.

**Tech Stack:** Python 3.12, FastAPI, SQLModel, docker-py, pytest. React 19, Vite, shadcn/ui (Radix + Tailwind v4), TanStack Query, vitest + React Testing Library.

**Reference spec:** `docs/superpowers/specs/2026-06-13-instances-config-overhaul-design.md`

**Conventions used throughout this plan:**
- `RESTART_POLICIES = ["no", "on-failure", "unless-stopped", "always"]`
- `RISK_FIELDS = {"devices", "entrypoint", "command", "privileged", "extra_docker_args", "dind", "cap_add", "security_opt"}`
- Backend tests: `cd backend && .venv/bin/python -m pytest <path> -v`
- Lint: `cd backend && .venv/bin/python -m ruff check app/ tests/`
- Frontend tests: `cd frontend && npm run test -- <path>`
- Typecheck: `cd frontend && npx tsc --noEmit`

---

## Phase A — Backend data model + docker pass-through

### Task A1: Add new fields to `ServiceTemplate`

**Files:**
- Modify: `backend/app/models.py:92-128` (the `ServiceTemplate` class)
- Test: `backend/tests/test_models_template_fields.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_models_template_fields.py
from app.models import ServiceTemplate


def test_template_new_fields_have_safe_defaults():
    t = ServiceTemplate(name="x", display_name="X", image="img")
    assert t.shared is False
    assert t.restart_policy == "no"
    assert t.read_only_rootfs is False
    assert t.tmpfs == []
    assert t.extra_hosts == {}
    assert t.ulimits == []
    assert t.extra_ports == []
    assert t.entrypoint is None
    assert t.command is None
    assert t.devices == []
    assert t.privileged is False
    assert t.extra_docker_args == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_models_template_fields.py -v`
Expected: FAIL — `AttributeError`/`TypeError` (fields do not exist).

- [ ] **Step 3: Add the fields**

In `backend/app/models.py`, inside `ServiceTemplate`, after the `tls_skip_verify` line (`:111`) add:

```python
    shared: bool = False
    restart_policy: str = "no"
    read_only_rootfs: bool = False
    tmpfs: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    extra_hosts: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    ulimits: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    extra_ports: list[dict] = Field(default_factory=list, sa_column=Column(JSON))
    entrypoint: list[str] | None = Field(default=None, sa_column=Column(JSON))
    command: list[str] | None = Field(default=None, sa_column=Column(JSON))
    devices: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    privileged: bool = False
    extra_docker_args: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
```

(`Any` is already imported in models.py; `Column`/`JSON` already imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_models_template_fields.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/tests/test_models_template_fields.py
git commit -m "feat(models): add pragmatic-tier template config fields"
```

---

### Task A2: Idempotent column migration on startup

**Files:**
- Modify: `backend/app/database.py` (add a column-add migration call in the init/startup path; follow the existing `error_message` column migration pattern)
- Test: `backend/tests/test_migration_template_columns.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_migration_template_columns.py
import sqlite3
from app.database import _ensure_template_columns  # to be created


def test_ensure_template_columns_adds_missing(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE service_templates (id TEXT PRIMARY KEY, name TEXT)"
    )
    conn.commit()
    _ensure_template_columns(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(service_templates)")}
    for c in ["shared", "restart_policy", "read_only_rootfs", "tmpfs",
              "extra_hosts", "ulimits", "extra_ports", "entrypoint",
              "command", "devices", "privileged", "extra_docker_args"]:
        assert c in cols
    # idempotent: second run does not raise
    _ensure_template_columns(conn)
    conn.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_migration_template_columns.py -v`
Expected: FAIL — `ImportError` (`_ensure_template_columns` not defined).

- [ ] **Step 3: Implement the migration helper**

In `backend/app/database.py` add (mirroring how the existing `error_message` instance column is handled — search the file for `PRAGMA table_info` / `ALTER TABLE` and place this beside it):

```python
_TEMPLATE_COLUMN_DDL = {
    "shared": "BOOLEAN DEFAULT 0",
    "restart_policy": "TEXT DEFAULT 'no'",
    "read_only_rootfs": "BOOLEAN DEFAULT 0",
    "tmpfs": "JSON DEFAULT '[]'",
    "extra_hosts": "JSON DEFAULT '{}'",
    "ulimits": "JSON DEFAULT '[]'",
    "extra_ports": "JSON DEFAULT '[]'",
    "entrypoint": "JSON",
    "command": "JSON",
    "devices": "JSON DEFAULT '[]'",
    "privileged": "BOOLEAN DEFAULT 0",
    "extra_docker_args": "JSON DEFAULT '{}'",
}


def _ensure_template_columns(conn) -> None:
    existing = {r[1] for r in conn.execute("PRAGMA table_info(service_templates)")}
    for col, ddl in _TEMPLATE_COLUMN_DDL.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE service_templates ADD COLUMN {col} {ddl}")
    conn.commit()
```

Then call it from the existing startup migration path. Find where the engine is created / tables initialized (e.g. `init_db` / `create_db_and_tables`) and, using the existing raw-connection approach there, call `_ensure_template_columns(raw_conn)` after `SQLModel.metadata.create_all`. If the existing pattern uses `engine.begin()`/`engine.raw_connection()`, reuse it verbatim.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_migration_template_columns.py -v`
Expected: PASS.

- [ ] **Step 5: Run full suite — ensure no regressions in DB init**

Run: `cd backend && .venv/bin/python -m pytest -q`
Expected: PASS (all existing tests green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/database.py backend/tests/test_migration_template_columns.py
git commit -m "feat(db): idempotent migration for new template columns"
```

---

### Task A3: `extra_docker_args` allowlist validator

**Files:**
- Create: `backend/app/services/docker_args.py`
- Test: `backend/tests/test_docker_args.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_docker_args.py
import pytest
from app.services.docker_args import validate_extra_args, DockerArgError


def test_allows_safe_kwargs():
    out = validate_extra_args({"hostname": "box", "init": True}, is_admin=True)
    assert out == {"hostname": "box", "init": True}


def test_rejects_host_network_for_everyone():
    with pytest.raises(DockerArgError):
        validate_extra_args({"network_mode": "host"}, is_admin=True)


def test_rejects_raw_port_publish():
    with pytest.raises(DockerArgError):
        validate_extra_args({"ports": {"80/tcp": 8080}}, is_admin=True)


def test_rejects_host_bind_mount():
    with pytest.raises(DockerArgError):
        validate_extra_args({"binds": ["/etc:/etc"]}, is_admin=True)


def test_admin_only_kwarg_blocked_for_non_admin():
    with pytest.raises(DockerArgError):
        validate_extra_args({"sysctls": {"net.x": "1"}}, is_admin=False)


def test_admin_only_kwarg_allowed_for_admin():
    out = validate_extra_args({"sysctls": {"net.x": "1"}}, is_admin=True)
    assert out == {"sysctls": {"net.x": "1"}}


def test_unknown_kwarg_rejected():
    with pytest.raises(DockerArgError):
        validate_extra_args({"made_up_kwarg": 1}, is_admin=True)


def test_labels_cannot_override_traefik():
    with pytest.raises(DockerArgError):
        validate_extra_args({"labels": {"traefik.enable": "false"}}, is_admin=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_args.py -v`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Implement the validator**

```python
# backend/app/services/docker_args.py
"""Allowlist validator for the raw `extra_docker_args` escape hatch.

Allowlist, not denylist: any kwarg not explicitly allowed is rejected. Some
kwargs are forbidden for everyone (escape/auth-bypass risks); some are gated
to admins. The router decides `is_admin`; this module enforces the surface.
"""
from typing import Any


class DockerArgError(ValueError):
    """Raised when extra_docker_args contains a forbidden or unknown kwarg."""


# Forbidden for everyone — would bypass isolation or Traefik auth.
_FORBIDDEN = {
    "ports",          # raw host publishing — all ingress must go via Traefik
    "binds",          # host bind mounts — named volumes only
    "volumes_from",
    "privileged",     # has a dedicated gated field
    "cap_add",        # dedicated gated field
    "devices",        # dedicated gated field
    "pid_mode",
    "ipc_mode",
    "userns_mode",
    "network_mode",   # host/container networking
}

# Allowed only when is_admin=True.
_ADMIN_ONLY = {
    "sysctls",
    "cgroup_parent",
    "runtime",
    "device_cgroup_rules",
    "security_opt",
    "tmpfs",
}

# Allowed for any caller who can reach the escape hatch.
_SAFE = {
    "hostname",
    "dns",
    "dns_search",
    "stop_signal",
    "stop_timeout",
    "working_dir",
    "init",
    "labels",
}


def validate_extra_args(args: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    if not args:
        return {}
    for key, value in args.items():
        if key in _FORBIDDEN:
            raise DockerArgError(f"'{key}' is not allowed via extra Docker args")
        if key in _ADMIN_ONLY:
            if not is_admin:
                raise DockerArgError(f"'{key}' requires admin")
            continue
        if key in _SAFE:
            if key == "labels" and isinstance(value, dict):
                if any(k.startswith("traefik.") for k in value):
                    raise DockerArgError("labels cannot override traefik.* keys")
            continue
        raise DockerArgError(f"Unknown Docker arg '{key}'")
    return dict(args)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_args.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/docker_args.py backend/tests/test_docker_args.py
git commit -m "feat(docker): allowlist validator for raw extra_docker_args"
```

---

### Task A4: Map new fields to docker-py kwargs in `create_container`

**Files:**
- Modify: `backend/app/services/docker_manager.py:44-129`
- Test: `backend/tests/test_docker_manager_new_opts.py` (create)

- [ ] **Step 1: Write the failing test**

The existing manager tests mock `docker.DockerClient.from_env()`. Follow `backend/tests/` patterns (look at the current `test_docker_manager*.py` for the fixture that captures `containers.create` kwargs).

```python
# backend/tests/test_docker_manager_new_opts.py
from unittest.mock import MagicMock, patch
from app.services.docker_manager import DockerManager


def _mgr_with_capture():
    client = MagicMock()
    client.images.get.return_value = True       # image present, no pull
    client.containers.get.side_effect = __import__("docker").errors.NotFound("x")
    created = {}
    def _create(**kwargs):
        created.update(kwargs)
        c = MagicMock(); c.id = "cid"; return c
    client.containers.create.side_effect = _create
    with patch("docker.DockerClient.from_env", return_value=client):
        mgr = DockerManager()
    return mgr, created


def test_restart_policy_and_flags_passed():
    mgr, created = _mgr_with_capture()
    mgr.create_container(
        name="selkies-x", image="img", labels={}, environment={}, volumes={},
        port=3001, restart_policy="unless-stopped", read_only_rootfs=True,
        tmpfs=["/tmp"], extra_hosts={"db": "10.0.0.2"},
        ulimits=[{"name": "nofile", "soft": 1024, "hard": 2048}],
        devices=["/dev/ttyUSB0:/dev/ttyUSB0"], entrypoint=["/bin/sh"],
        command=["-c", "sleep 1"], extra_docker_args={"hostname": "box"},
    )
    assert created["restart_policy"] == {"Name": "unless-stopped", "MaximumRetryCount": 0}
    assert created["read_only"] is True
    assert created["tmpfs"] == {"/tmp": ""}
    assert created["extra_hosts"] == {"db": "10.0.0.2"}
    assert created["devices"] == ["/dev/ttyUSB0:/dev/ttyUSB0"]
    assert created["entrypoint"] == ["/bin/sh"]
    assert created["command"] == ["-c", "sleep 1"]
    assert created["hostname"] == "box"
    assert len(created["ulimits"]) == 1


def test_restart_policy_no_is_omitted():
    mgr, created = _mgr_with_capture()
    mgr.create_container(name="selkies-x", image="img", labels={},
                         environment={}, volumes={}, port=3001,
                         restart_policy="no")
    assert "restart_policy" not in created
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_manager_new_opts.py -v`
Expected: FAIL — `create_container()` got unexpected keyword arguments.

- [ ] **Step 3: Extend the signature + kwarg mapping**

In `backend/app/services/docker_manager.py`, extend the `create_container` signature (after `network` param, `:61`) with:

```python
        restart_policy: str = "no",
        read_only_rootfs: bool = False,
        tmpfs: list[str] | None = None,
        extra_hosts: dict[str, str] | None = None,
        ulimits: list[dict] | None = None,
        devices: list[str] | None = None,
        entrypoint: list[str] | None = None,
        command: list[str] | None = None,
        extra_docker_args: dict | None = None,
```

Add the import at the top of the file alongside `DeviceRequest`:

```python
from docker.types import Ulimit
```

After the existing `shm_size`/`nano_cpus` block (`:110`), before the `images.get` call, insert:

```python
        if restart_policy and restart_policy != "no":
            kwargs["restart_policy"] = {"Name": restart_policy, "MaximumRetryCount": 0}
        if read_only_rootfs:
            kwargs["read_only"] = True
        if tmpfs:
            kwargs["tmpfs"] = {path: "" for path in tmpfs}
        if extra_hosts:
            kwargs["extra_hosts"] = dict(extra_hosts)
        if ulimits:
            kwargs["ulimits"] = [
                Ulimit(name=u["name"], soft=u.get("soft"), hard=u.get("hard"))
                for u in ulimits
            ]
        if devices:
            # merge with any GPU /dev/dri device added above
            kwargs["devices"] = list(kwargs.get("devices", [])) + list(devices)
        if entrypoint is not None:
            kwargs["entrypoint"] = entrypoint
        if command is not None:
            kwargs["command"] = command
        if extra_docker_args:
            # already allowlist-validated by the router; merge last, never
            # letting it clobber traefik labels or core kwargs
            for k, v in extra_docker_args.items():
                if k == "labels":
                    kwargs.setdefault("labels", {}).update(v)
                else:
                    kwargs[k] = v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_manager_new_opts.py -v`
Expected: PASS.

- [ ] **Step 5: Run full manager suite**

Run: `cd backend && .venv/bin/python -m pytest tests/ -k docker_manager -v`
Expected: PASS (existing manager tests unaffected).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/docker_manager.py backend/tests/test_docker_manager_new_opts.py
git commit -m "feat(docker): map new template fields to container kwargs"
```

---

## Phase B — Backend schemas, authz, sharing, routing

### Task B1: Extend Create/Update schemas + router field allowlist

**Files:**
- Modify: `backend/app/schemas.py:11-56` (`TemplateCreate`, `TemplateUpdate`)
- Modify: `backend/app/routers/templates.py:13-19` (`_TEMPLATE_UPDATE_FIELDS`)
- Test: `backend/tests/test_template_schema_fields.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_template_schema_fields.py
from app.schemas import TemplateCreate


def test_create_schema_accepts_new_fields():
    body = TemplateCreate(
        name="t", display_name="T", image="img",
        restart_policy="always", read_only_rootfs=True, tmpfs=["/tmp"],
        extra_hosts={"a": "1.2.3.4"}, ulimits=[{"name": "nofile", "soft": 1, "hard": 2}],
        extra_ports=[{"container_port": 8080, "label": "code", "slug": "code", "strip_prefix": True}],
        entrypoint=["/bin/sh"], command=["-c", "x"], devices=["/dev/dri:/dev/dri"],
        privileged=True, extra_docker_args={"hostname": "h"}, shared=True,
    )
    assert body.restart_policy == "always"
    assert body.extra_ports[0]["slug"] == "code"
    assert body.shared is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_schema_fields.py -v`
Expected: FAIL — unexpected keyword arguments / validation error.

- [ ] **Step 3: Add fields to schemas**

In `backend/app/schemas.py`, add to both `TemplateCreate` and `TemplateUpdate` (Update fields all `Optional`/defaulted). Add to `TemplateCreate`:

```python
    shared: bool = False
    restart_policy: str = "no"
    read_only_rootfs: bool = False
    tmpfs: list[str] = []
    extra_hosts: dict[str, str] = {}
    ulimits: list[dict] = []
    extra_ports: list[dict] = []
    entrypoint: list[str] | None = None
    command: list[str] | None = None
    devices: list[str] = []
    privileged: bool = False
    extra_docker_args: dict = {}
```

Mirror the same in `TemplateUpdate` (it likely uses `| None = None` per field — match its existing style).

In `backend/app/routers/templates.py`, extend `_TEMPLATE_UPDATE_FIELDS` to include all the new field names:

```python
    "shared", "restart_policy", "read_only_rootfs", "tmpfs", "extra_hosts",
    "ulimits", "extra_ports", "entrypoint", "command", "devices",
    "privileged", "extra_docker_args",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_schema_fields.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/templates.py backend/tests/test_template_schema_fields.py
git commit -m "feat(api): template schemas + update allowlist for new fields"
```

---

### Task B2: Admin-gate risk fields + validate extra_docker_args in router

**Files:**
- Modify: `backend/app/routers/templates.py` (the `create_template` `:36-60` and the update handler)
- Test: `backend/tests/test_template_admin_gate.py` (create)

- [ ] **Step 1: Write the failing test**

The suite has fixtures for admin + non-admin clients (look in `conftest.py` / existing auth tests for `admin_client` / `user_client` patterns). Use whatever those are named.

```python
# backend/tests/test_template_admin_gate.py
def test_non_admin_cannot_set_privileged(user_client):
    r = user_client.post("/templates", json={
        "name": "p", "display_name": "P", "image": "img", "privileged": True})
    assert r.status_code == 403


def test_non_admin_cannot_set_devices(user_client):
    r = user_client.post("/templates", json={
        "name": "d", "display_name": "D", "image": "img",
        "devices": ["/dev/dri:/dev/dri"]})
    assert r.status_code == 403


def test_non_admin_bad_extra_args_rejected_400(user_client):
    r = user_client.post("/templates", json={
        "name": "e", "display_name": "E", "image": "img",
        "extra_docker_args": {"network_mode": "host"}})
    assert r.status_code in (400, 403)


def test_admin_can_set_risk_fields(admin_client):
    r = admin_client.post("/templates", json={
        "name": "ok", "display_name": "OK", "image": "img",
        "privileged": True, "devices": ["/dev/dri:/dev/dri"],
        "extra_docker_args": {"sysctls": {"net.x": "1"}}})
    assert r.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_admin_gate.py -v`
Expected: FAIL — non-admin currently allowed (no gate on the new fields).

- [ ] **Step 3: Implement the gate + validation**

In `backend/app/routers/templates.py`, add near the top:

```python
from app.services.docker_args import validate_extra_args, DockerArgError

_RISK_FIELDS = ("devices", "entrypoint", "command", "privileged",
                "extra_docker_args", "dind", "cap_add", "security_opt")


def _enforce_risk_gate(body, user) -> None:
    if user.role == "admin":
        return
    for f in _RISK_FIELDS:
        val = getattr(body, f, None)
        if val:  # truthy: non-empty list/dict/str or True
            raise HTTPException(403, f"'{f}' requires admin")
```

In `create_template`, replace the existing dind/cap checks (`:45-49`) with:

```python
    _enforce_risk_gate(body, user)
    try:
        validate_extra_args(body.extra_docker_args or {}, is_admin=(user.role == "admin"))
    except DockerArgError as e:
        raise HTTPException(400, str(e))
```

Apply the same two calls in the update handler before persisting (use the incoming patch body; only enforce on fields actually present in the patch).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_admin_gate.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/templates.py backend/tests/test_template_admin_gate.py
git commit -m "feat(api): admin-gate risk fields + validate extra_docker_args"
```

---

### Task B3: Shared-template visibility + share authorization

**Files:**
- Modify: `backend/app/routers/templates.py` (`list_templates` `:22-33`, and the update handler for the `shared` toggle)
- Test: `backend/tests/test_template_sharing.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_template_sharing.py
def test_shared_template_visible_to_other_user(admin_client, user_client, second_user_client):
    # user creates a private template, then shares it
    r = user_client.post("/templates", json={
        "name": "mine", "display_name": "Mine", "image": "img"})
    tid = r.json()["id"]
    user_client.put(f"/templates/{tid}", json={"shared": True})
    names = {t["name"] for t in second_user_client.get("/templates").json()}
    assert "mine" in names


def test_non_owner_cannot_edit_shared_template(user_client, second_user_client):
    r = user_client.post("/templates", json={
        "name": "mine2", "display_name": "Mine2", "image": "img", "shared": True})
    tid = r.json()["id"]
    r2 = second_user_client.put(f"/templates/{tid}", json={"display_name": "Hacked"})
    assert r2.status_code in (403, 404)
```

If a `second_user_client` fixture does not exist, add one to `conftest.py` mirroring `user_client` with a different user id/token.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_sharing.py -v`
Expected: FAIL — shared template not visible / edit not blocked.

- [ ] **Step 3: Implement visibility + share rules**

In `list_templates`, change the non-admin filter (`:28-31`) to include shared:

```python
    if user.role != "admin":
        stmt = stmt.where(
            (ServiceTemplate.owner_id == user.id)
            | (ServiceTemplate.owner_id == None)  # noqa: E711
            | (ServiceTemplate.shared == True)     # noqa: E712
        )
```

The update handler must keep the existing owner-or-admin check (`require_owner_or_admin`) — setting `shared` is already covered by it (only owner/admin may PUT). Confirm the update path uses that dependency; if `shared` is in the patch and the caller is neither owner nor admin, the existing check returns 403/404. No new code needed beyond the allowlist entry from B1.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_template_sharing.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/templates.py backend/tests/test_template_sharing.py backend/tests/conftest.py
git commit -m "feat(api): shared template visibility for all users"
```

---

### Task B4: Pass new fields from instance launch to docker_manager

**Files:**
- Modify: `backend/app/routers/instances.py` (the `create_container(...)` call in `_build_and_start_container` / `_launch_instance_background`, around `:55-104` / `:119-238`)
- Test: `backend/tests/test_instance_launch_opts.py` (create)

- [ ] **Step 1: Write the failing test**

Instance tests mock `get_docker_manager`. Follow the existing instance-launch test pattern; assert the mock's `create_container` received the template's new fields.

```python
# backend/tests/test_instance_launch_opts.py
# (Skeleton — adapt fixtures to the existing instance test harness in tests/.)
def test_launch_passes_new_template_fields(launch_instance_capturing_create):
    template_fields = {
        "restart_policy": "unless-stopped",
        "devices": ["/dev/dri:/dev/dri"],
        "privileged": False,
        "extra_docker_args": {"hostname": "box"},
    }
    create_kwargs = launch_instance_capturing_create(template_fields)
    assert create_kwargs["restart_policy"] == "unless-stopped"
    assert create_kwargs["devices"] == ["/dev/dri:/dev/dri"]
    assert create_kwargs["extra_docker_args"] == {"hostname": "box"}
```

Implement `launch_instance_capturing_create` as a fixture in the test module that builds a template with the given fields, runs the launch path with a mocked docker manager, and returns the captured `create_container` kwargs. Model it on the existing instance launch tests (search `tests/` for `get_docker_manager` overrides).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_instance_launch_opts.py -v`
Expected: FAIL — new kwargs not forwarded.

- [ ] **Step 3: Forward the fields**

In `backend/app/routers/instances.py`, in the `docker.create_container(...)` call, add after the existing args (`network=net,`):

```python
            restart_policy=template.restart_policy,
            read_only_rootfs=template.read_only_rootfs,
            tmpfs=template.tmpfs,
            extra_hosts=template.extra_hosts,
            ulimits=template.ulimits,
            devices=template.devices,
            entrypoint=template.entrypoint,
            command=template.command,
            privileged=template.privileged,
            extra_docker_args=template.extra_docker_args,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_instance_launch_opts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/instances.py backend/tests/test_instance_launch_opts.py
git commit -m "feat(instances): forward new template fields to container launch"
```

---

### Task B5: Extra-port path routers in `route_writer`

**Files:**
- Modify: `backend/app/services/route_writer.py` (`build_routes_config` + the per-instance loop, and `refresh_routes_from_db` `:219-251` to include `extra_ports`)
- Test: `backend/tests/test_route_writer_extra_ports.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_route_writer_extra_ports.py
from app.services.route_writer import build_routes_config


def _instance(extra_ports):
    return {"id": "i1", "subdomain": "app", "port": 3001, "protocol": "https",
            "tls_skip_verify": True, "extra_ports": extra_ports}


def test_extra_port_router_subdomain_mode():
    cfg = build_routes_config(
        [_instance([{"container_port": 8080, "label": "code", "slug": "code",
                     "strip_prefix": True}])],
        domain="example.com", deploy_mode="direct")
    routers = cfg["http"]["routers"]
    rule = next(r["rule"] for k, r in routers.items() if "code" in k)
    assert "PathPrefix(`/p/code`)" in rule
    assert "Host(`app.example.com`)" in rule
    # a service for the extra port exists pointing at 8080
    svcs = cfg["http"]["services"]
    assert any(":8080" in str(s) or "8080" in str(s) for s in svcs.values())
    # strip-prefix middleware present
    assert any("stripprefix" in k.lower() or "stripPrefix" in str(v)
               for k, v in cfg["http"].get("middlewares", {}).items())


def test_no_extra_ports_unchanged():
    cfg = build_routes_config([_instance([])], domain="example.com", deploy_mode="direct")
    # only the single primary router for the instance
    assert sum(1 for k in cfg["http"]["routers"] if k.startswith("i1")) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer_extra_ports.py -v`
Expected: FAIL — extra-port routers not generated / `extra_ports` key ignored.

- [ ] **Step 3: Implement extra-port routers**

In `build_routes_config`, inside the loop that builds each instance's primary router/service, after the primary is added, append:

```python
        for ep in inst.get("extra_ports", []) or []:
            slug = ep["slug"]
            cport = ep["container_port"]
            rid = f"{inst['id']}-p-{slug}"
            # nest under the instance's primary route per deploy mode
            if deploy_mode == "lan":
                prefix = f"/i/{inst['subdomain']}/p/{slug}"
                rule = f"PathPrefix(`{prefix}`)"
            else:
                prefix = f"/p/{slug}"
                rule = f"Host(`{inst['subdomain']}.{domain}`) && PathPrefix(`{prefix}`)"
            router = {
                "rule": rule,
                "service": rid,
                "entrypoints": primary_entrypoints,   # reuse the same as primary
                "middlewares": list(primary_middlewares),  # same auth middleware
            }
            if ep.get("strip_prefix", True):
                mw_id = f"{rid}-strip"
                config["http"].setdefault("middlewares", {})[mw_id] = {
                    "stripPrefix": {"prefixes": [prefix]}
                }
                router["middlewares"] = router["middlewares"] + [mw_id]
            config["http"]["routers"][rid] = router
            scheme = inst.get("protocol", "https")
            config["http"]["services"][rid] = {
                "loadBalancer": {"servers": [{"url": f"{scheme}://selkies-{inst['subdomain']}:{cport}"}]}
            }
```

Use the same variable names the existing loop uses for `primary_entrypoints` / `primary_middlewares` / the service URL host. If the existing code derives the upstream host differently (e.g. container name vs network alias), match it exactly — read the primary-service block just above and mirror its URL construction, only swapping the port for `cport`.

In `refresh_routes_from_db` (`:240-247`), add `extra_ports` to the per-instance dict:

```python
        data.append({
            "id": i.id,
            "subdomain": i.subdomain,
            "port": tmpl.internal_port if tmpl else 3001,
            "protocol": tmpl.internal_protocol if tmpl else "https",
            "tls_skip_verify": bool(tmpl.tls_skip_verify) if tmpl else False,
            "extra_ports": tmpl.extra_ports if tmpl else [],
        })
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer_extra_ports.py -v`
Expected: PASS.

- [ ] **Step 5: Run full backend suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all PASS, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_writer.py backend/tests/test_route_writer_extra_ports.py
git commit -m "feat(routing): path-prefix routers for extra container ports"
```

---

## Phase C — Frontend shared controls + builder

> Follow existing shadcn patterns. Reuse `@/components/ui/*` (Slider, Select, Switch, Tooltip, Input, Label, Button). If a primitive is missing (e.g. Slider/Tooltip), add it via the project's shadcn convention (check `components/ui/` for what exists first).

### Task C1: Typed control primitives

**Files:**
- Create: `frontend/src/components/templates/builder/controls/slider-input.tsx`
- Create: `frontend/src/components/templates/builder/controls/locked-field.tsx`
- Create: `frontend/src/components/templates/builder/controls/field-tooltip.tsx`
- Test: `frontend/src/components/templates/builder/controls/__tests__/slider-input.test.tsx`
- Test: `frontend/src/components/templates/builder/controls/__tests__/locked-field.test.tsx`

- [ ] **Step 1: Write the failing tests**

```tsx
// slider-input.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { SliderInput } from "../slider-input";

test("typing in the box updates value", () => {
  const onChange = vi.fn();
  render(<SliderInput label="Memory" min={1} max={64} value={8} unit="GB" onChange={onChange} />);
  const box = screen.getByRole("spinbutton");
  fireEvent.change(box, { target: { value: "16" } });
  expect(onChange).toHaveBeenCalledWith(16);
});
```

```tsx
// locked-field.test.tsx
import { render, screen } from "@testing-library/react";
import { LockedField } from "../locked-field";

test("non-admin sees disabled wrapper + lock", () => {
  render(<LockedField locked label="Privileged"><input data-testid="ctl" /></LockedField>);
  expect(screen.getByTestId("ctl")).toBeDisabled();
  expect(screen.getByText(/requires admin/i)).toBeInTheDocument();
});

test("admin sees enabled control", () => {
  render(<LockedField locked={false} label="Privileged"><input data-testid="ctl" /></LockedField>);
  expect(screen.getByTestId("ctl")).not.toBeDisabled();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npm run test -- builder/controls`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement the controls**

```tsx
// field-tooltip.tsx
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Info } from "lucide-react";

export function FieldTooltip({ text }: { text: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Info className="h-3.5 w-3.5 text-muted-foreground inline ml-1 cursor-help" aria-label="info" />
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs">{text}</TooltipContent>
    </Tooltip>
  );
}
```

```tsx
// slider-input.tsx
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FieldTooltip } from "./field-tooltip";

interface Props {
  label: string; min: number; max: number; step?: number;
  value: number; unit?: string; tooltip?: string;
  onChange: (v: number) => void; disabled?: boolean;
}

export function SliderInput({ label, min, max, step = 1, value, unit, tooltip, onChange, disabled }: Props) {
  return (
    <div className="space-y-2">
      <Label className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}{unit ? ` · ${value} ${unit}` : ""}{tooltip && <FieldTooltip text={tooltip} />}
      </Label>
      <div className="flex items-center gap-3">
        <Slider min={min} max={max} step={step} value={[value]} disabled={disabled}
                onValueChange={(v) => onChange(v[0])} className="flex-1" />
        <Input type="number" role="spinbutton" min={min} max={max} step={step}
               value={value} disabled={disabled} className="w-20"
               onChange={(e) => onChange(Number(e.target.value))} />
      </div>
    </div>
  );
}
```

```tsx
// locked-field.tsx
import { cloneElement, isValidElement } from "react";
import { Lock } from "lucide-react";
import { Label } from "@/components/ui/label";

interface Props { locked: boolean; label: string; children: React.ReactNode; }

export function LockedField({ locked, label, children }: Props) {
  const child = isValidElement(children)
    ? cloneElement(children as React.ReactElement, locked ? { disabled: true } : {})
    : children;
  return (
    <div className={locked ? "opacity-70" : ""}>
      <Label className="text-xs flex items-center gap-1">
        {locked && <Lock className="h-3 w-3" />} {label}
        {locked && <span className="text-[10px] text-muted-foreground">(requires admin)</span>}
      </Label>
      {child}
    </div>
  );
}
```

If `@/components/ui/slider` or `tooltip` don't exist, scaffold them per shadcn (Radix `@radix-ui/react-slider`, `@radix-ui/react-tooltip`) before this step.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm run test -- builder/controls`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/templates/builder/controls
git commit -m "feat(ui): typed builder control primitives (slider/locked/tooltip)"
```

---

### Task C2: Extend `use-launch-config` with new fields + role-aware locking + clone

**Files:**
- Modify: `frontend/src/hooks/use-launch-config.ts`
- Test: `frontend/src/hooks/__tests__/use-launch-config-new.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// use-launch-config-new.test.ts
import { renderHook, act } from "@testing-library/react";
import { useLaunchConfig } from "../use-launch-config";

test("new fields default and serialize into buildTemplateData", () => {
  const { result } = renderHook(() => useLaunchConfig({}));
  act(() => result.current.setRestartPolicy("unless-stopped"));
  act(() => result.current.setExtraPorts([{ container_port: 8080, label: "code", slug: "code", strip_prefix: true }]));
  const data = result.current.buildTemplateData();
  expect(data.restart_policy).toBe("unless-stopped");
  expect(data.extra_ports[0].slug).toBe("code");
  expect(data.read_only_rootfs).toBe(false);
});

test("prefills new fields from a template (clone)", () => {
  const tmpl: any = { display_name: "G", image: "img", restart_policy: "always",
    devices: ["/dev/dri:/dev/dri"], extra_ports: [{ container_port: 9000, label: "api", slug: "api", strip_prefix: false }] };
  const { result } = renderHook(() => useLaunchConfig({ template: tmpl }));
  expect(result.current.restartPolicy).toBe("always");
  expect(result.current.extraPorts[0].slug).toBe("api");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- use-launch-config-new`
Expected: FAIL — setters/fields undefined.

- [ ] **Step 3: Extend the hook**

In `frontend/src/hooks/use-launch-config.ts`:

1. Add an `ExtraPortEntry` interface near the top:

```ts
export interface ExtraPortEntry {
  container_port: number;
  label: string;
  slug: string;
  strip_prefix: boolean;
}
```

2. Add to the `LaunchConfig` interface (state + setters):

```ts
  restartPolicy: string; setRestartPolicy: (v: string) => void;
  readOnlyRootfs: boolean; setReadOnlyRootfs: (v: boolean) => void;
  tmpfs: string[]; setTmpfs: (v: string[]) => void;
  extraHosts: Record<string, string>; setExtraHosts: (v: Record<string, string>) => void;
  ulimits: { name: string; soft: number; hard: number }[]; setUlimits: (v: { name: string; soft: number; hard: number }[]) => void;
  extraPorts: ExtraPortEntry[]; setExtraPorts: (v: ExtraPortEntry[]) => void;
  entrypoint: string[] | null; setEntrypoint: (v: string[] | null) => void;
  command: string[] | null; setCommand: (v: string[] | null) => void;
  devices: string[]; setDevices: (v: string[]) => void;
  privileged: boolean; setPrivileged: (v: boolean) => void;
  extraDockerArgs: Record<string, unknown>; setExtraDockerArgs: (v: Record<string, unknown>) => void;
  shared: boolean; setShared: (v: boolean) => void;
```

3. Add the matching `buildTemplateData()` return keys (backend names):

```ts
      restart_policy: restartPolicy,
      read_only_rootfs: readOnlyRootfs,
      tmpfs,
      extra_hosts: extraHosts,
      ulimits,
      extra_ports: extraPorts,
      entrypoint,
      command,
      devices,
      privileged,
      extra_docker_args: extraDockerArgs,
      shared,
```

4. Add the `useState` initializers (prefill from `template`):

```ts
  const [restartPolicy, setRestartPolicy] = useState(template?.restart_policy ?? "no");
  const [readOnlyRootfs, setReadOnlyRootfs] = useState(template?.read_only_rootfs ?? false);
  const [tmpfs, setTmpfs] = useState<string[]>(template?.tmpfs ?? []);
  const [extraHosts, setExtraHosts] = useState<Record<string, string>>(template?.extra_hosts ?? {});
  const [ulimits, setUlimits] = useState(template?.ulimits ?? []);
  const [extraPorts, setExtraPorts] = useState<ExtraPortEntry[]>(template?.extra_ports ?? []);
  const [entrypoint, setEntrypoint] = useState<string[] | null>(template?.entrypoint ?? null);
  const [command, setCommand] = useState<string[] | null>(template?.command ?? null);
  const [devices, setDevices] = useState<string[]>(template?.devices ?? []);
  const [privileged, setPrivileged] = useState(template?.privileged ?? false);
  const [extraDockerArgs, setExtraDockerArgs] = useState<Record<string, unknown>>(template?.extra_docker_args ?? {});
  const [shared, setShared] = useState(template?.shared ?? false);
```

5. Add all of these to the returned object.

Also add the new fields to the `ServiceTemplate` type in `frontend/src/lib/types.ts` (mirror the backend model field names/types).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npm run test -- use-launch-config-new`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/hooks/use-launch-config.ts frontend/src/lib/types.ts frontend/src/hooks/__tests__/use-launch-config-new.test.ts
git commit -m "feat(ui): extend launch config hook with new template fields"
```

---

### Task C3: Builder sections + orchestrator

**Files:**
- Create: `frontend/src/components/templates/builder/template-builder.tsx`
- Create: `frontend/src/components/templates/builder/sections/{basics,resources,storage,ports-network,environment,security,raw-docker}.tsx`
- Create: `frontend/src/components/templates/builder/controls/repeatable-rows.tsx`
- Test: `frontend/src/components/templates/builder/__tests__/template-builder.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// template-builder.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { TemplateBuilder } from "../template-builder";
import { useLaunchConfig } from "@/hooks/use-launch-config";

function Harness({ isAdmin }: { isAdmin: boolean }) {
  const cfg = useLaunchConfig({});
  return <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />;
}

test("renders section rail and switches panels", () => {
  render(<Harness isAdmin />);
  fireEvent.click(screen.getByRole("button", { name: /resources/i }));
  expect(screen.getByText(/memory/i)).toBeInTheDocument();
});

test("non-admin sees security section locked", () => {
  render(<Harness isAdmin={false} />);
  fireEvent.click(screen.getByRole("button", { name: /security/i }));
  expect(screen.getAllByText(/requires admin/i).length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- template-builder`
Expected: FAIL — modules not found.

- [ ] **Step 3: Implement `repeatable-rows.tsx`**

```tsx
// controls/repeatable-rows.tsx
import { Button } from "@/components/ui/button";
import { Plus, X } from "lucide-react";

interface Props<T> {
  rows: T[];
  blank: T;
  onChange: (rows: T[]) => void;
  render: (row: T, update: (r: T) => void) => React.ReactNode;
  addLabel?: string;
}

export function RepeatableRows<T>({ rows, blank, onChange, render, addLabel = "Add" }: Props<T>) {
  return (
    <div className="space-y-2">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <div className="flex-1">{render(row, (r) => onChange(rows.map((x, j) => (j === i ? r : x))))}</div>
          <Button variant="ghost" size="icon" aria-label="remove"
                  onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            <X className="h-4 w-4" />
          </Button>
        </div>
      ))}
      <Button variant="outline" size="sm" onClick={() => onChange([...rows, { ...blank }])}>
        <Plus className="h-3 w-3 mr-1" /> {addLabel}
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Implement the section components**

Each section receives `{ cfg, isAdmin }`. Keep each file focused (<150 lines). Examples for the two most representative; build the rest the same way using the C1 controls + `RepeatableRows`.

```tsx
// sections/resources.tsx
import { SliderInput } from "../controls/slider-input";
import { EnumSelect } from "../controls/enum-select";  // thin wrapper over shadcn Select (create alongside)
import { ToggleField } from "../controls/toggle-field"; // thin wrapper over shadcn Switch (create alongside)
import type { LaunchConfig } from "@/hooks/use-launch-config";

const RESTART_POLICIES = ["no", "on-failure", "unless-stopped", "always"];

function gb(v: string) { return Number(String(v).replace(/g$/i, "")) || 0; }

export function ResourcesSection({ cfg }: { cfg: LaunchConfig; isAdmin: boolean }) {
  return (
    <div className="space-y-5">
      <SliderInput label="Memory" min={1} max={64} unit="GB" value={gb(cfg.memoryLimit)}
        tooltip="Hard RAM cap for the container. Container is killed if it exceeds this."
        onChange={(v) => cfg.setMemoryLimit(`${v}g`)} />
      <SliderInput label="CPU" min={1} max={16} step={0.5} unit="vCPU" value={Number(cfg.cpuLimit) || 1}
        tooltip="Max CPU cores. Fractional allowed (e.g. 2.5)."
        onChange={(v) => cfg.setCpuLimit(String(v))} />
      <SliderInput label="Shared memory" min={0.25} max={8} step={0.25} unit="GB" value={gb(cfg.shmSize)}
        tooltip="/dev/shm size. Browsers/Chromium need ≥1GB."
        onChange={(v) => cfg.setShmSize(`${v}g`)} />
      <EnumSelect label="Restart policy" value={cfg.restartPolicy} options={RESTART_POLICIES}
        tooltip="When Docker should auto-restart the container."
        onChange={cfg.setRestartPolicy} />
      <ToggleField label="GPU passthrough" checked={cfg.gpuEnabled}
        tooltip="Expose the host GPU (NVIDIA device-requests or /dev/dri)."
        onChange={cfg.setGpuEnabled} />
    </div>
  );
}
```

```tsx
// sections/security.tsx  (every control wrapped in LockedField for non-admin)
import { LockedField } from "../controls/locked-field";
import { ToggleField } from "../controls/toggle-field";
import { RepeatableRows } from "../controls/repeatable-rows";
import { Input } from "@/components/ui/input";
import type { LaunchConfig } from "@/hooks/use-launch-config";

export function SecuritySection({ cfg, isAdmin }: { cfg: LaunchConfig; isAdmin: boolean }) {
  return (
    <div className="space-y-5">
      <LockedField locked={!isAdmin} label="Privileged mode">
        <ToggleField label="" checked={cfg.privileged}
          tooltip="DANGER: full host access. Required only for nested Docker."
          onChange={cfg.setPrivileged} />
      </LockedField>
      <LockedField locked={!isAdmin} label="Device passthrough">
        <RepeatableRows rows={cfg.devices.map((d) => ({ v: d }))} blank={{ v: "" }}
          addLabel="Add device"
          onChange={(rows) => cfg.setDevices(rows.map((r) => r.v).filter(Boolean))}
          render={(row, update) => (
            <Input placeholder="/dev/ttyUSB0:/dev/ttyUSB0" value={row.v}
              disabled={!isAdmin} onChange={(e) => update({ v: e.target.value })} />
          )} />
      </LockedField>
    </div>
  );
}
```

Create thin `controls/enum-select.tsx` and `controls/toggle-field.tsx` wrappers over the shadcn `Select`/`Switch` with a `FieldTooltip` and label (same shape as `SliderInput`). Build `basics`, `storage`, `ports-network`, `environment`, `raw-docker` sections analogously:
- **basics**: name, image, icon, display name (Inputs), category, tags.
- **storage**: volumes (RepeatableRows of name+mount, reuse existing volume editing), `read_only_rootfs` ToggleField, tmpfs RepeatableRows.
- **ports-network**: primary `internal_port`+`internal_protocol`, then `extra_ports` RepeatableRows (container_port, label, slug, strip_prefix ToggleField) with the path-prefix warning text + base-URL hint, `extra_hosts` KeyValueEditor.
- **environment**: reuse `env-editor.tsx`; add a small "LinuxServer.io" helper row binding PUID/PGID/TZ into `envVars`.
- **raw-docker**: LockedField-wrapped — entrypoint/command (Inputs split on spaces), `extra_docker_args` KeyValueEditor.

- [ ] **Step 5: Implement the orchestrator**

```tsx
// template-builder.tsx
import { useState } from "react";
import { cn } from "@/lib/utils";
import { BasicsSection } from "./sections/basics";
import { ResourcesSection } from "./sections/resources";
import { StorageSection } from "./sections/storage";
import { PortsNetworkSection } from "./sections/ports-network";
import { EnvironmentSection } from "./sections/environment";
import { SecuritySection } from "./sections/security";
import { RawDockerSection } from "./sections/raw-docker";
import { Lock } from "lucide-react";
import type { LaunchConfig } from "@/hooks/use-launch-config";

const SECTIONS = [
  { id: "basics", label: "Basics", Comp: BasicsSection, risk: false },
  { id: "resources", label: "Resources", Comp: ResourcesSection, risk: false },
  { id: "storage", label: "Storage", Comp: StorageSection, risk: false },
  { id: "ports", label: "Ports & Network", Comp: PortsNetworkSection, risk: false },
  { id: "environment", label: "Environment", Comp: EnvironmentSection, risk: false },
  { id: "security", label: "Security", Comp: SecuritySection, risk: true },
  { id: "raw", label: "Raw Docker", Comp: RawDockerSection, risk: true },
] as const;

export function TemplateBuilder({ cfg, isAdmin }: { cfg: LaunchConfig; isAdmin: boolean }) {
  const [active, setActive] = useState("basics");
  const Active = SECTIONS.find((s) => s.id === active)!.Comp;
  return (
    <div className="flex gap-4 min-h-[300px]">
      <nav className="w-40 shrink-0 space-y-1">
        {SECTIONS.map((s) => (
          <button key={s.id} onClick={() => setActive(s.id)}
            className={cn("w-full text-left text-sm px-3 py-2 rounded-md flex items-center gap-1.5",
              active === s.id ? "bg-primary/15 text-foreground" : "text-muted-foreground hover:bg-muted")}>
            {s.risk && <Lock className="h-3 w-3" />} {s.label}
          </button>
        ))}
      </nav>
      <div className="flex-1 min-w-0">
        <Active cfg={cfg} isAdmin={isAdmin} />
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd frontend && npm run test -- template-builder`
Expected: PASS.

- [ ] **Step 7: Typecheck + commit**

Run: `cd frontend && npx tsc --noEmit`
Expected: clean.

```bash
git add frontend/src/components/templates/builder
git commit -m "feat(ui): shared TemplateBuilder with section rail + typed sections"
```

---

## Phase D — Easy mode, routes, custom templates

### Task D1: Easy mode (layout B) + advanced toggle in launch modal

**Files:**
- Modify: `frontend/src/components/templates/launch-modal.tsx`
- Create: `frontend/src/components/templates/easy-launch.tsx`
- Test: `frontend/src/components/templates/__tests__/launch-modal-modes.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// launch-modal-modes.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { LaunchModal } from "../launch-modal";
// wrap in the app's QueryClientProvider test util if one exists

test("opens in easy mode with what-you-get summary", () => {
  render(<LaunchModal open onClose={() => {}} template={{ id: "1", display_name: "Gaming", image: "img", gpu_enabled: true, memory_limit: "16g", cpu_limit: "8" } as any} />);
  expect(screen.getByText(/what you get/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /launch/i })).toBeInTheDocument();
});

test("switch to advanced reveals the builder section rail", () => {
  render(<LaunchModal open onClose={() => {}} template={{ id: "1", display_name: "Gaming", image: "img" } as any} />);
  fireEvent.click(screen.getByRole("button", { name: /advanced/i }));
  expect(screen.getByRole("button", { name: /resources/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- launch-modal-modes`
Expected: FAIL — easy mode/summary/advanced toggle not present.

- [ ] **Step 3: Implement `easy-launch.tsx` (layout B)**

```tsx
// easy-launch.tsx
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Cpu, HardDrive, Globe, ShieldCheck } from "lucide-react";
import type { LaunchConfig } from "@/hooks/use-launch-config";

export function EasyLaunch({ cfg, domain, onLaunch, onAdvanced, launching }: {
  cfg: LaunchConfig; domain: string; onLaunch: () => void; onAdvanced: () => void; launching: boolean;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-[44%_56%] gap-4">
      <div className="rounded-lg bg-muted/40 p-4 space-y-2">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">What you get</div>
        <ul className="text-sm space-y-1.5">
          <li className="flex items-center gap-2"><Cpu className="h-4 w-4" />{cfg.gpuEnabled ? "GPU · " : ""}{cfg.memoryLimit} RAM · {cfg.cpuLimit} vCPU</li>
          <li className="flex items-center gap-2"><HardDrive className="h-4 w-4" />Persistent storage</li>
          <li className="flex items-center gap-2"><Globe className="h-4 w-4" />Streams at {cfg.subdomain}.{domain}</li>
          <li className="flex items-center gap-2"><ShieldCheck className="h-4 w-4" />Auth required</li>
        </ul>
      </div>
      <div className="space-y-3">
        <div><Label>Name</Label><Input value={cfg.name} onChange={(e) => cfg.setName(e.target.value)} /></div>
        <div><Label>Address</Label><Input value={cfg.subdomain} onChange={(e) => cfg.setSubdomain(e.target.value)} /></div>
        <Button className="w-full" onClick={onLaunch} disabled={launching}>{launching ? "Launching..." : "Launch"}</Button>
        <button className="w-full text-xs text-muted-foreground hover:text-foreground" onClick={onAdvanced}>Switch to Advanced →</button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire the toggle into `launch-modal.tsx`**

Add `const [mode, setMode] = useState<"easy" | "advanced">("easy");` and `const isAdmin = useAuth().user?.role === "admin";` (use the project's auth hook). Replace the `<LaunchConfigFields .../>` line with:

```tsx
        {mode === "easy" ? (
          <EasyLaunch cfg={cfg} domain={DOMAIN} launching={createInstance.isPending}
            onLaunch={handleSaveAndLaunch} onAdvanced={() => setMode("advanced")} />
        ) : (
          <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />
        )}
```

Keep the existing footer buttons visible only in advanced mode (easy mode has its own Launch). Import `DOMAIN` from the app config/env the project already uses for building instance URLs (search for where `.${domain}` is rendered today).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npm run test -- launch-modal-modes`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/templates/easy-launch.tsx frontend/src/components/templates/launch-modal.tsx frontend/src/components/templates/__tests__/launch-modal-modes.test.tsx
git commit -m "feat(ui): easy/advanced launch modes (layout B + builder)"
```

---

### Task D2: Full-page builder routes + create entry points + sharing

**Files:**
- Create: `frontend/src/pages/template-builder-page.tsx`
- Modify: the app router (where routes are registered — search for the existing route table, e.g. `App.tsx` / a routes file) to add `/templates/new` and `/templates/:id/edit`
- Modify: `frontend/src/components/templates/template-grid.tsx` (add a "New template" menu: Clone / From registry image / From scratch; badge shared templates)
- Test: `frontend/src/pages/__tests__/template-builder-page.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// template-builder-page.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { TemplateBuilderPage } from "../template-builder-page";

test("scratch mode renders empty builder with Save + Save & Share", () => {
  render(<TemplateBuilderPage mode="scratch" />);  // wrap in router/query providers per project test utils
  expect(screen.getByRole("button", { name: /save & share/i })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npm run test -- template-builder-page`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the page**

```tsx
// template-builder-page.tsx
import { useParams } from "react-router-dom";        // match the project's router lib
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { TemplateBuilder } from "@/components/templates/builder/template-builder";
import { useLaunchConfig } from "@/hooks/use-launch-config";
import { useCreateTemplate, useUpdateTemplate, useTemplate } from "@/hooks/use-templates";
import { useAuth } from "@/hooks/use-auth";            // match project's auth hook
import { toast } from "sonner";

export function TemplateBuilderPage({ mode }: { mode: "new" | "edit" | "scratch" | "clone" }) {
  const { id } = useParams();
  const existing = mode === "edit" || mode === "clone" ? useTemplate(id).data : null;
  const cfg = useLaunchConfig({ template: existing });
  const isAdmin = useAuth().user?.role === "admin";
  const create = useCreateTemplate();
  const update = useUpdateTemplate();
  const [saving, setSaving] = useState(false);

  async function save(share: boolean) {
    setSaving(true);
    try {
      cfg.setShared(share);
      const data = { ...cfg.buildTemplateData(), shared: share };
      if (mode === "edit" && id) await update.mutateAsync({ id, data });
      else await create.mutateAsync(data);
      toast.success(share ? "Template saved & shared" : "Template saved");
    } catch (e) { toast.error((e as Error).message); }
    finally { setSaving(false); }
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-4">
      <h1 className="text-lg font-semibold">{mode === "edit" ? "Edit template" : "New template"}</h1>
      <TemplateBuilder cfg={cfg} isAdmin={isAdmin} />
      <div className="flex gap-2">
        <Button onClick={() => save(false)} disabled={saving}>Save</Button>
        <Button variant="secondary" onClick={() => save(true)} disabled={saving}>Save & Share</Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Register routes + grid entry points**

Add routes (match the project's router registration style):

```tsx
<Route path="/templates/new" element={<TemplateBuilderPage mode="scratch" />} />
<Route path="/templates/:id/edit" element={<TemplateBuilderPage mode="edit" />} />
```

In `template-grid.tsx`, add a "New template" dropdown with three items:
- **Clone existing** → navigate to `/templates/new` seeded by a selected template (pass via route state or a `?clone=<id>` query the page reads).
- **From registry image** → open the existing `RegistryBrowser` flow.
- **From scratch** → navigate `/templates/new`.

Badge shared templates: in `template-card.tsx`, if `template.shared && template.owner_id !== currentUserId`, show a "shared" chip and render launch-only (hide edit/delete for non-owners).

- [ ] **Step 5: Run test + typecheck**

Run: `cd frontend && npm run test -- template-builder-page && npx tsc --noEmit`
Expected: PASS, clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/template-builder-page.tsx frontend/src/components/templates/template-grid.tsx frontend/src/components/templates/template-card.tsx
git commit -m "feat(ui): full-page template builder, create entry points, sharing badge"
```

---

### Task D3: Final verification

- [ ] **Step 1: Backend full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all PASS, ruff clean.

- [ ] **Step 2: Frontend full suite + typecheck + build**

Run: `cd frontend && npm run test && npx tsc --noEmit && npm run build`
Expected: all PASS, build succeeds.

- [ ] **Step 3: Manual smoke (document results)**

Boot the stack (`docker compose up -d`, backend dev server). Verify:
1. Launch modal opens in easy mode; "Launch" works with defaults.
2. Switch to Advanced; sliders/selects/toggles render; tooltips show.
3. As non-admin, Security + Raw Docker controls are disabled with "requires admin".
4. Create a custom template from scratch, Save & Share; confirm a second user sees it.
5. Add an extra port to a template, launch, confirm `host/p/<slug>` routes through Traefik with auth.

- [ ] **Step 4: Commit any fixes from smoke**

```bash
git add -A && git commit -m "fix: address issues found in instances-config smoke test"
```

---

## Self-review notes (author)

- Spec §1 fields → A1/A2/B1. §2 docker mapping → A4; allowlist → A3; admin gate → B2. §2.4 visibility → B3. §3 ports → B5 (mode-aware). §4 frontend → C1–C3, D1–D2. §5 risk gating double-enforced (UI LockedField + server B2). §6 testing → per-task + D3.
- Type consistency: `extra_ports` entry shape `{container_port, label, slug, strip_prefix}` used identically in B1/B5/C2/C3. `restart_policy` enum identical in A4/B1/C3. Backend field names reused verbatim in `buildTemplateData` (C2) to avoid the existing `security_opts` plural drift.
- Known follow-up (out of scope, note for executor): the pre-existing `security_opts`/`custom_opts` plural keys in `buildTemplateData` don't match the singular model field; not fixed here to avoid scope creep — flag if it surfaces.
