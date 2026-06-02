# Admin-gated DinD Templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let admins author templates that run a real isolated Docker daemon (DinD) inside the desktop instance, with nested images persisted on a per-instance volume.

**Architecture:** A boolean `dind` flag on `ServiceTemplate`. When set, the backend launches the container `privileged`, injects `START_DOCKER=true` (the linuxserver selkies base auto-starts its bundled dockerd), and mounts a deterministic per-instance named volume at `/var/lib/docker` for overlay2 + persistence. Authoring a DinD template (create/update with `dind=true`) requires `role == "admin"`; launching is open to any user.

**Tech Stack:** FastAPI, SQLModel, SQLite, docker-py, pytest, React/TypeScript.

---

## File Structure

- `backend/app/models.py` — add `dind` column to `ServiceTemplate`.
- `backend/app/database.py` — migration row for `service_templates.dind`.
- `backend/app/schemas.py` — `dind` on `TemplateCreate` + `TemplateUpdate`.
- `backend/app/services/docker_manager.py` — `dind` param on `create_container`.
- `backend/app/routers/instances.py` — pass `dind`, manage dockerstore volume (2 paths).
- `backend/app/routers/templates.py` — admin gate when `dind=true`.
- `backend/tests/conftest.py` — `member_client` fixture (non-admin).
- `backend/tests/test_docker_manager.py` — DinD kwargs tests.
- `backend/tests/test_templates_api.py` — admin-gate tests.
- `backend/tests/test_instances_api.py` — dockerstore volume lifecycle test.
- `frontend/src/lib/types.ts` — `dind` on `Template` + `TemplateCreate`.
- `frontend/src/components/templates/template-card.tsx` — DinD badge.
- `templates/dev-desktop.json` — enable `dind` on the custom desktop seed.

---

### Task 1: Add `dind` to the data model + migration

**Files:**
- Modify: `backend/app/models.py` (ServiceTemplate, after `shm_size` ~L102)
- Modify: `backend/app/database.py` (`_run_migrations` list ~L31)
- Test: `backend/tests/test_models.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_models.py`:

```python
def test_service_template_dind_defaults_false():
    from app.models import ServiceTemplate
    t = ServiceTemplate(name="x", display_name="X", image="img:latest")
    assert t.dind is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_models.py::test_service_template_dind_defaults_false -v`
Expected: FAIL — `AttributeError`/`TypeError` (no `dind` attr).

- [ ] **Step 3: Add the model field**

In `backend/app/models.py`, in `ServiceTemplate`, immediately after the `shm_size` line:

```python
    dind: bool = False
```

- [ ] **Step 4: Add the migration row**

In `backend/app/database.py`, in the `migrations` list inside `_run_migrations`, add:

```python
        ("service_templates", "dind", "BOOLEAN"),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_models.py::test_service_template_dind_defaults_false -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/database.py backend/tests/test_models.py
git commit -m "feat(model): add dind flag to ServiceTemplate + migration"
```

---

### Task 2: Add `dind` to the API schemas

**Files:**
- Modify: `backend/app/schemas.py` (`TemplateCreate` ~L13, `TemplateUpdate` ~L32)
- Test: `backend/tests/test_templates_api.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_templates_api.py`:

```python
@pytest.mark.asyncio
async def test_create_template_accepts_dind(admin_client):
    payload = {**TEMPLATE_PAYLOAD, "name": "dind-tpl", "dind": True}
    resp = await admin_client.post("/api/templates", json=payload)
    assert resp.status_code == 201, resp.text
    assert resp.json()["dind"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_templates_api.py::test_create_template_accepts_dind -v`
Expected: FAIL — response `dind` is `False`/absent (schema ignores unknown field).

- [ ] **Step 3: Add the schema fields**

In `backend/app/schemas.py`, in `TemplateCreate` after `shm_size`:

```python
    dind: bool = False
```

In `TemplateUpdate` after `shm_size`:

```python
    dind: bool | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_templates_api.py::test_create_template_accepts_dind -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/tests/test_templates_api.py
git commit -m "feat(schema): add dind to TemplateCreate/TemplateUpdate"
```

---

### Task 3: `create_container` honors `dind`

**Files:**
- Modify: `backend/app/services/docker_manager.py` (signature ~L52, kwargs ~L54-65)
- Test: `backend/tests/test_docker_manager.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_docker_manager.py`:

```python
def test_create_container_dind(mock_docker):
    manager, client = mock_docker
    mock_container = MagicMock()
    mock_container.id = "dind-container"
    client.containers.create.return_value = mock_container

    manager.create_container(
        name="dind-instance",
        image="selkies-desktop:latest",
        labels={},
        environment={"PUID": "1000"},
        volumes={"dind-store": {"bind": "/var/lib/docker", "mode": "rw"}},
        port=3001,
        dind=True,
    )

    call_kwargs = client.containers.create.call_args[1]
    assert call_kwargs["privileged"] is True
    assert call_kwargs["environment"]["START_DOCKER"] == "true"
    assert call_kwargs["volumes"]["dind-store"]["bind"] == "/var/lib/docker"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_docker_manager.py::test_create_container_dind -v`
Expected: FAIL — `create_container() got an unexpected keyword argument 'dind'`.

- [ ] **Step 3: Implement**

In `backend/app/services/docker_manager.py`, add the param to the `create_container` signature (after `privileged: bool = False,`):

```python
        dind: bool = False,
```

Then, immediately before the `kwargs: dict = {` assignment, normalize the flags:

```python
        if dind:
            privileged = True
            environment = {**environment, "START_DOCKER": "true"}
```

(The existing kwargs already spread `**environment` and set `"privileged": privileged`, so no further change is needed there. The `/var/lib/docker` mount is supplied by the caller via `volumes`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_docker_manager.py::test_create_container_dind -v`
Expected: PASS

- [ ] **Step 5: Run the full docker_manager suite (no regressions)**

Run: `.venv/bin/python -m pytest tests/test_docker_manager.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/docker_manager.py backend/tests/test_docker_manager.py
git commit -m "feat(docker): create_container dind -> privileged + START_DOCKER"
```

---

### Task 4: Wire `dind` + dockerstore volume through instance launch

**Files:**
- Modify: `backend/app/routers/instances.py` — `_build_and_start_container` (~L42-74) and `_launch_instance_background` (~L105-138)
- Test: `backend/tests/test_instances_api.py`

**Design note:** the dockerstore volume name is deterministic — `selkies-{instance.id}-dockerstore` — so rebuild/restart re-mounts the same volume. It is appended to `instance.volume_names` (skipping duplicates) so the existing delete path (`delete_instance` ~L459 iterates `volume_names`) cleans it up. Do NOT rely on `zip(template.volumes, volume_names)`; handle the dockerstore volume explicitly because it has no matching `template.volumes` entry.

- [ ] **Step 1: Write the failing test**

First inspect `backend/tests/test_instances_api.py` for the existing instance-launch test and its helper for creating a template + launching (look for the test that asserts `create_container` was called and how the mocked docker manager is reached). Then add a test that launches a `dind=true` template and asserts the dockerstore volume is requested.

Add to `backend/tests/test_instances_api.py` (adapt the template-create + launch helpers to match the file's existing style):

```python
@pytest.mark.asyncio
async def test_launch_dind_instance_mounts_docker_store(admin_client):
    tpl = {
        "name": "dind-desk", "display_name": "DinD Desk",
        "image": "selkies-desktop:latest", "internal_port": 3001,
        "dind": True,
    }
    tr = await admin_client.post("/api/templates", json=tpl)
    assert tr.status_code == 201, tr.text
    template_id = tr.json()["id"]

    lr = await admin_client.post("/api/instances", json={"template_id": template_id})
    assert lr.status_code in (200, 201), lr.text
    instance_id = lr.json()["id"]

    gr = await admin_client.get(f"/api/instances/{instance_id}")
    vol_names = gr.json()["volume_names"]
    assert any(v.endswith("-dockerstore") for v in vol_names)
```

> If launch runs in a background task and `volume_names` is not yet populated synchronously, assert against the mocked docker manager's `create_container` call kwargs instead (the conftest `client` fixture builds the mock fresh per request, so prefer the `volume_names` assertion if the synchronous `_build_and_start_container` path is used; otherwise follow the pattern the existing launch test in this file already uses to observe container creation).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_instances_api.py::test_launch_dind_instance_mounts_docker_store -v`
Expected: FAIL — no `-dockerstore` volume present.

- [ ] **Step 3: Add a helper for the dockerstore volume**

In `backend/app/routers/instances.py`, add a module-level helper near the top (after imports):

```python
def _dind_store_volume(instance_id: str) -> str:
    return f"selkies-{instance_id}-dockerstore"
```

- [ ] **Step 4: Wire `_build_and_start_container`**

In `_build_and_start_container`, after the `for vol, vol_name in zip(...)` loop that fills `volumes` (~L47-49) and before `env = {...}`, add:

```python
    if template.dind:
        store = _dind_store_volume(instance.id)
        if store not in instance.volume_names:
            instance.volume_names = [*instance.volume_names, store]
        await asyncio.to_thread(docker.create_volume, store)
        volumes[store] = {"bind": "/var/lib/docker", "mode": "rw"}
```

Then add `dind=template.dind,` to the `docker.create_container(...)` call kwargs (alongside `gpu_enabled=...`).

- [ ] **Step 5: Wire `_launch_instance_background`**

In `_launch_instance_background`, after the `volumes = {}` / `for vol, vol_name in zip(...)` block (~L112-114) and before `env = {...}` (~L116), add:

```python
            if template.dind:
                store = _dind_store_volume(instance.id)
                if store not in instance.volume_names:
                    instance.volume_names = [*instance.volume_names, store]
                await asyncio.to_thread(docker.create_volume, store)
                volumes[store] = {"bind": "/var/lib/docker", "mode": "rw"}
```

Then add `dind=template.dind,` to this path's `docker.create_container(...)` call kwargs (~L126-138, alongside `gpu_enabled=...`).

- [ ] **Step 6: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_instances_api.py::test_launch_dind_instance_mounts_docker_store -v`
Expected: PASS

- [ ] **Step 7: Run the full instances suite (no regressions)**

Run: `.venv/bin/python -m pytest tests/test_instances_api.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/routers/instances.py backend/tests/test_instances_api.py
git commit -m "feat(instances): launch dind templates with persistent /var/lib/docker volume"
```

---

### Task 5: Admin gate for DinD authoring

**Files:**
- Modify: `backend/app/routers/templates.py` — `create_template` (~L28-47), `update_template` (~L64-79)
- Modify: `backend/tests/conftest.py` — add `member_client` fixture
- Test: `backend/tests/test_templates_api.py`

- [ ] **Step 1: Add a non-admin client fixture**

In `backend/tests/conftest.py`, add (imports `AsyncClient`, `ASGITransport`, `app` already used by the file's `client` fixture; reuse them):

```python
@pytest.fixture
async def member_client(session):
    from app.models import User
    from app.security.passwords import hash_password
    session.add(User(
        username="member",
        password_hash=hash_password("correct horse battery staple"),
        role="member",
        is_active=True,
    ))
    await session.commit()
    c = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    r = await c.post("/api/auth/login", json={
        "username": "member", "password": "correct horse battery staple"})
    assert r.status_code == 200, r.text
    c.headers.update({"X-CSRF-Token": c.cookies.get("csrf_token")})
    yield c
    await c.aclose()
```

- [ ] **Step 2: Write the failing tests**

Add to `backend/tests/test_templates_api.py`:

```python
@pytest.mark.asyncio
async def test_member_cannot_create_dind_template(member_client):
    payload = {**TEMPLATE_PAYLOAD, "name": "dind-blocked", "dind": True}
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 403

@pytest.mark.asyncio
async def test_member_can_create_non_dind_template(member_client):
    payload = {**TEMPLATE_PAYLOAD, "name": "plain-ok", "dind": False}
    resp = await member_client.post("/api/templates", json=payload)
    assert resp.status_code == 201, resp.text

@pytest.mark.asyncio
async def test_member_cannot_update_template_to_dind(member_client):
    create = await member_client.post(
        "/api/templates", json={**TEMPLATE_PAYLOAD, "name": "to-upgrade"})
    tid = create.json()["id"]
    resp = await member_client.put(f"/api/templates/{tid}", json={"dind": True})
    assert resp.status_code == 403
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_templates_api.py -k "dind" -v`
Expected: the two 403 tests FAIL (currently 201/200 — no gate).

- [ ] **Step 4: Implement the gate**

In `backend/app/routers/templates.py`, in `create_template`, after the image validation (`if not body.image...` ~L33-34) add:

```python
    if body.dind and user.role != "admin":
        raise HTTPException(403, "DinD templates require admin")
```

In `update_template`, after the `require_owner_or_admin(template.owner_id, user)` line (~L74) add:

```python
    if body.dind and user.role != "admin":
        raise HTTPException(403, "DinD templates require admin")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_templates_api.py -k "dind" -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/templates.py backend/tests/conftest.py backend/tests/test_templates_api.py
git commit -m "feat(templates): gate dind authoring to admins"
```

---

### Task 6: Frontend — types + DinD badge

**Files:**
- Modify: `frontend/src/lib/types.ts` (`Template` ~L17, `TemplateCreate` ~L97)
- Modify: `frontend/src/components/templates/template-card.tsx`

- [ ] **Step 1: Add the type fields**

In `frontend/src/lib/types.ts`, in the `Template` interface near `gpu_enabled: boolean;`:

```typescript
  dind: boolean;
```

In the `TemplateCreate` (partial) interface near `gpu_enabled?: boolean;`:

```typescript
  dind?: boolean;
```

- [ ] **Step 2: Add a DinD badge to the card**

In `frontend/src/components/templates/template-card.tsx`, locate where existing tags/indicators render (e.g. the GPU indicator) and add a conditional badge:

```tsx
{template.dind && (
  <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
    DinD
  </span>
)}
```

(Match the surrounding badge/className conventions already used in this card — copy an adjacent badge's wrapper if one exists rather than introducing new layout.)

- [ ] **Step 3: Verify the frontend builds**

Run: `cd frontend && npm run build`
Expected: tsc + build succeed, no type errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/types.ts frontend/src/components/templates/template-card.tsx
git commit -m "feat(frontend): dind type field + template card badge"
```

---

### Task 7: Enable DinD on the custom desktop seed

**Files:**
- Modify: `templates/dev-desktop.json`

**Note:** `seed_templates` only inserts templates that do not already exist by name (`database.py` ~L63-65). On an existing DB the `dev-desktop` row will NOT be updated by this change — it only affects fresh seeds. Document this; an admin can set `dind` on an existing template via the API/PUT.

- [ ] **Step 1: Add the flag to the seed**

In `templates/dev-desktop.json` (image `selkies-desktop:latest`), add a top-level key:

```json
  "dind": true,
```

- [ ] **Step 2: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('templates/dev-desktop.json'))"`
Expected: no output (valid JSON).

- [ ] **Step 3: Commit**

```bash
git add templates/dev-desktop.json
git commit -m "feat(seed): enable dind on dev-desktop template"
```

---

### Task 8: Full suite + lint gate

- [ ] **Step 1: Run the whole backend suite**

Run: `cd backend && .venv/bin/python -m pytest -v`
Expected: all PASS (139 prior tests + new ones).

- [ ] **Step 2: Lint**

Run: `cd backend && .venv/bin/python -m ruff check app/ tests/`
Expected: no errors.

- [ ] **Step 3: Commit any lint fixes (if needed)**

```bash
git add -A && git commit -m "chore: lint fixes for dind feature"
```

---

## Self-Review

**Spec coverage:**
- Image no-change → noted in Architecture (no task needed). ✓
- Model `dind` + migration → Task 1. ✓
- `create_container` privileged + START_DOCKER + /var/lib/docker → Task 3 (mount via caller) + Task 4 (caller supplies mount). ✓
- Instance lifecycle both paths + dockerstore volume + cleanup-via-volume_names → Task 4. ✓
- Admin gate create+update → Task 5. ✓
- Schemas → Task 2. ✓
- Frontend (reduced: no template-form UI exists, so types + badge only; admin gate enforced server-side) → Task 6. Deviation from spec §6 documented here. ✓
- Tests → Tasks 1-5 inline. ✓
- Seed enablement → Task 7 (beyond spec, harmless convenience). ✓

**Placeholder scan:** none — all steps carry concrete code/commands. Task 4 Step 1 intentionally instructs inspecting the existing launch test to match its assertion style; the fallback is spelled out.

**Type consistency:** `dind` (snake_case) used consistently across model/schema/JSON/backend; `dind` (camel-free, same word) in TS. Volume name helper `_dind_store_volume` used in both launch paths. `START_DOCKER` string `"true"` consistent with base image contract.
