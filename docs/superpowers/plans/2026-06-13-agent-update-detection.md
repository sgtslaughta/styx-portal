# Outdated-agent detection + update command — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Flag enrolled workstation agents running an old build and give admins a copy-paste command to update them.

**Architecture:** Server parses the `AGENT_VERSION` of the `styx_agent.py` it serves as the "latest" version. Each `WorkstationOut` reports `agent_outdated`. A new admin endpoint returns a lan/public copy-paste command that re-pulls the agent `.py` files from the public `/api/enroll/*` endpoints and restarts the user service. The admin panel shows an "Outdated" badge + "Update" button.

**Tech Stack:** FastAPI + SQLModel (backend), pytest, React + TypeScript (frontend).

---

## File structure

- `backend/app/services/workstations.py` — add `get_latest_agent_version()`, `build_update_command()`, `AGENT_UPDATE_FILES`.
- `backend/app/schemas.py` — add `WorkstationOut.agent_outdated`, new `WorkstationUpdateCommandOut`.
- `backend/app/routers/workstations.py` — pass latest version into `_out`; add `GET /{ws_id}/update-command`.
- `backend/tests/test_workstation_admin_api.py` — tests for version parse, outdated flag, update-command endpoint.
- `frontend/src/api/client.ts` — `Workstation.agent_outdated`, `WorkstationUpdateCommand` type, `api.workstationUpdateCommand`.
- `frontend/src/components/system/workstations-panel.tsx` — version line + "Outdated" badge + "Update" button + command dialog.

Commands (run from `backend/`):
- Test: `.venv/bin/python -m pytest <path> -v`
- Lint: `.venv/bin/python -m ruff check app/ tests/`

Frontend (run from `frontend/`): `npx tsc --noEmit`

---

## Task 1: `get_latest_agent_version()` helper

**Files:**
- Modify: `backend/app/services/workstations.py`
- Test: `backend/tests/test_workstation_admin_api.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_workstation_admin_api.py`:

```python
def test_get_latest_agent_version_parses_served_file(tmp_path):
    from app.services.workstations import get_latest_agent_version, _version_cache
    _version_cache.clear()
    (tmp_path / "styx_agent.py").write_text('X = 1\nAGENT_VERSION = "0.9.3"\nY = 2\n')
    assert get_latest_agent_version(str(tmp_path)) == "0.9.3"


def test_get_latest_agent_version_missing_file_returns_empty(tmp_path):
    from app.services.workstations import get_latest_agent_version, _version_cache
    _version_cache.clear()
    assert get_latest_agent_version(str(tmp_path / "nope")) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k latest_agent_version -v`
Expected: FAIL with `ImportError`/`cannot import name 'get_latest_agent_version'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/workstations.py`, add near the top (after the existing
`import re` / settings block — `re` and `Settings` are already imported):

```python
from pathlib import Path

_version_cache: dict[str, tuple[float, str]] = {}


def get_latest_agent_version(agent_dir: str | None = None) -> str:
    """The AGENT_VERSION of the styx_agent.py this server serves — the build a
    fresh enrollment would install. Cached per path+mtime. Empty when the file
    is missing/unparseable (callers then flag nothing as outdated)."""
    path = Path(agent_dir or _settings.AGENT_DIR) / "styx_agent.py"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return ""
    cached = _version_cache.get(str(path))
    if cached and cached[0] == mtime:
        return cached[1]
    m = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', path.read_text())
    version = m.group(1) if m else ""
    _version_cache[str(path)] = (mtime, version)
    return version
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k latest_agent_version -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workstations.py backend/tests/test_workstation_admin_api.py
git commit -m "feat(workstations): parse served agent version (get_latest_agent_version)"
```

---

## Task 2: `agent_outdated` on the workstation list

**Files:**
- Modify: `backend/app/schemas.py:224-244` (`WorkstationOut`)
- Modify: `backend/app/routers/workstations.py:59-74` (`_out`), `:96-102` (list endpoint)
- Test: `backend/tests/test_workstation_admin_api.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_workstation_admin_api.py` (uses existing `admin_client`
+ `session` fixtures; mirrors the existing `_make_ws`-style direct insert — adjust
field names if a local helper already exists):

```python
@pytest.mark.asyncio
async def test_list_marks_outdated_agents(admin_client, session, monkeypatch):
    import app.routers.workstations as wr
    from app.models import User, Workstation
    from sqlmodel import select
    monkeypatch.setattr(wr, "get_latest_agent_version", lambda: "0.4.2")
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    for sub, ver in [("a", "0.4.1"), ("b", "0.4.2"), ("c", "")]:
        session.add(Workstation(name=sub, subdomain=sub, hostname=sub,
                                status="online", agent_version=ver,
                                created_by=admin.id))
    await session.commit()

    r = await admin_client.get("/api/workstations")
    assert r.status_code == 200
    by_sub = {w["subdomain"]: w["agent_outdated"] for w in r.json()}
    assert by_sub["a"] is True     # old build
    assert by_sub["b"] is False    # current
    assert by_sub["c"] is False    # pending / never reported
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k outdated -v`
Expected: FAIL — `KeyError: 'agent_outdated'` (field not in response).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas.py`, add to `WorkstationOut` (after `agent_version: str`):

```python
    agent_outdated: bool = False
```

In `backend/app/routers/workstations.py`, import the helper — extend the existing
`from app.services.workstations import ...` line to include
`get_latest_agent_version`.

Change `_out`'s signature and body:

```python
def _out(ws: Workstation, allowed: list[str],
         occupant: User | None = None,
         viewer_id: str | None = None,
         latest_version: str = "") -> WorkstationOut:
    in_use = ws.active_connections > 0 and ws.occupied_by is not None
    return WorkstationOut(
        id=ws.id, name=ws.name, subdomain=ws.subdomain, hostname=ws.hostname,
        lan_ip=ws.lan_ip, port=ws.port, status=ws.status,
        display_server=ws.display_server, gpu_info=ws.gpu_info,
        os_info=ws.os_info, agent_version=ws.agent_version,
        agent_outdated=bool(latest_version)
        and ws.agent_version not in ("", latest_version),
        stream_settings=ws.stream_settings, all_users=ws.all_users,
        last_heartbeat=ws.last_heartbeat.isoformat() if ws.last_heartbeat else None,
        last_error=ws.last_error, created_at=ws.created_at.isoformat(),
        allowed_user_ids=allowed,
        in_use=in_use,
        in_use_by=occupant.username if (in_use and occupant) else None,
        in_use_self=bool(in_use and viewer_id and ws.occupied_by == viewer_id))
```

Update the list endpoint to compute latest once and pass it:

```python
@router.get("", response_model=list[WorkstationOut])
async def list_workstations(admin: User = Depends(require_admin),
                            session: AsyncSession = Depends(get_session)):
    rows = (await session.exec(select(Workstation))).all()
    latest = get_latest_agent_version()
    return [_out(ws, await _allowed_ids(session, ws.id),
                 occupant=await _occupant(session, ws), viewer_id=admin.id,
                 latest_version=latest)
            for ws in rows]
```

Note: other callers of `_out` (e.g. `/mine`, PATCH, PUT) keep working — they omit
`latest_version`, so those rows simply report `agent_outdated=False`. Leave them
unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k outdated -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/workstations.py backend/tests/test_workstation_admin_api.py
git commit -m "feat(workstations): report agent_outdated on the admin list"
```

---

## Task 3: `build_update_command()` helper

**Files:**
- Modify: `backend/app/services/workstations.py`
- Test: `backend/tests/test_workstation_admin_api.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_update_command_pulls_files_and_restarts():
    from app.services.workstations import build_update_command
    cmd = build_update_command("https://styx.example.com")
    assert "https://styx.example.com/api/enroll/${f%%:*}" in cmd
    assert "agent.py:styx_agent.py" in cmd
    assert "gateway.py:gateway.py" in cmd
    assert "systemctl --user restart styx-agent" in cmd
    assert "curl -fsSL " in cmd          # secure by default
    assert " -k " not in cmd


def test_build_update_command_insecure_for_lan():
    from app.services.workstations import build_update_command
    cmd = build_update_command("https://192.168.1.10", insecure=True)
    assert "curl -fsSLk " in cmd          # self-signed LAN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k build_update_command -v`
Expected: FAIL — `cannot import name 'build_update_command'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/workstations.py`, add (near `build_enroll_command`):

```python
# (remote endpoint name, local filename in the install dir)
AGENT_UPDATE_FILES = [
    ("agent.py", "styx_agent.py"),
    ("engine.py", "engine.py"),
    ("gateway.py", "gateway.py"),
    ("selkies_launcher.py", "selkies_launcher.py"),
]


def build_update_command(base: str, *, insecure: bool = False) -> str:
    """Copy-paste one-liner that re-pulls the agent python files from the public
    /api/enroll/* endpoints and restarts the user service. No enrollment token
    needed; the venv/wheels/artifacts are left untouched (code-only update)."""
    flag = "-fsSLk" if insecure else "-fsSL"
    pairs = " ".join(f"{remote}:{local}" for remote, local in AGENT_UPDATE_FILES)
    return (
        'INSTALL="$HOME/.local/share/styx-agent"; '
        f'for f in {pairs}; do '
        f'curl {flag} "{base}/api/enroll/${{f%%:*}}" -o "$INSTALL/${{f##*:}}"; '
        'done; '
        'systemctl --user restart styx-agent'
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k build_update_command -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workstations.py backend/tests/test_workstation_admin_api.py
git commit -m "feat(workstations): build_update_command (code-only agent update)"
```

---

## Task 4: `GET /{ws_id}/update-command` endpoint

**Files:**
- Modify: `backend/app/schemas.py` (add `WorkstationUpdateCommandOut`)
- Modify: `backend/app/routers/workstations.py` (new route + imports)
- Test: `backend/tests/test_workstation_admin_api.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_update_command_endpoint(admin_client, session, monkeypatch):
    import app.routers.workstations as wr
    from app.models import User, Workstation
    from sqlmodel import select
    monkeypatch.setattr(wr, "get_latest_agent_version", lambda: "0.4.2")
    admin = (await session.exec(select(User).where(User.role == "admin"))).first()
    ws = Workstation(name="u", subdomain="u", hostname="u", status="online",
                     agent_version="0.4.1", created_by=admin.id)
    session.add(ws)
    await session.commit()
    await session.refresh(ws)

    r = await admin_client.get(f"/api/workstations/{ws.id}/update-command")
    assert r.status_code == 200
    body = r.json()
    assert body["latest_version"] == "0.4.2"
    assert body["current_version"] == "0.4.1"
    assert "/api/enroll/agent.py" in body["public_command"]
    assert "systemctl --user restart styx-agent" in body["public_command"]


@pytest.mark.asyncio
async def test_update_command_unknown_id_404(admin_client):
    r = await admin_client.get("/api/workstations/does-not-exist/update-command")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k update_command_endpoint -v`
Expected: FAIL — 404/405 (route does not exist) so the body asserts fail.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/schemas.py`, add:

```python
class WorkstationUpdateCommandOut(BaseModel):
    latest_version: str
    current_version: str
    lan_command: str | None
    public_command: str
    lan_url_source: str            # env | detected | none
```

In `backend/app/routers/workstations.py`:
- Extend the `from app.services.workstations import ...` line to also import
  `build_update_command`, `lan_enroll_url`, `lan_ca_pin` (import only those not
  already imported there — `lan_enroll_url`/`lan_ca_pin` are already used by
  `mint_enroll_token`).
- Add `WorkstationUpdateCommandOut` to the `from app.schemas import ...` line.
- Add the route (place after `mint_enroll_token`):

```python
@router.get("/{ws_id}/update-command", response_model=WorkstationUpdateCommandOut)
async def update_command(ws_id: str,
                         admin: User = Depends(require_admin),
                         session: AsyncSession = Depends(get_session)):
    ws = await _get_or_404(session, ws_id)
    lan_base, lan_source = lan_enroll_url()
    lan_command = None
    if lan_base:
        lan_command = build_update_command(lan_base, insecure=True)
    return WorkstationUpdateCommandOut(
        latest_version=get_latest_agent_version(),
        current_version=ws.agent_version,
        lan_command=lan_command,
        public_command=build_update_command(f"https://{_settings.DOMAIN}"),
        lan_url_source=lan_source)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_workstation_admin_api.py -k "update_command_endpoint or update_command_unknown" -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Full backend suite + lint**

Run: `.venv/bin/python -m pytest -q` → Expected: all pass.
Run: `.venv/bin/python -m ruff check app/ tests/` → Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas.py backend/app/routers/workstations.py backend/tests/test_workstation_admin_api.py
git commit -m "feat(workstations): GET /{id}/update-command endpoint"
```

---

## Task 5: Frontend API types + method

**Files:**
- Modify: `frontend/src/api/client.ts:11-19` (`Workstation` type), `:215-226` (api methods)

- [ ] **Step 1: Add the `agent_outdated` field to the `Workstation` type**

In `frontend/src/api/client.ts`, change the `Workstation` type line:

```typescript
  agent_version: string; agent_outdated: boolean;
  stream_settings: { encoder: string; framerate: number; bitrate_kbps: number };
```

- [ ] **Step 2: Add the `WorkstationUpdateCommand` type**

After the `EnrollToken` type:

```typescript
export type WorkstationUpdateCommand = {
  latest_version: string;
  current_version: string;
  lan_command: string | null;
  public_command: string;
  lan_url_source: "env" | "detected" | "none";
};
```

- [ ] **Step 3: Add the api method**

In the `api` object, next to `mintEnrollToken`/`revokeWorkstation`:

```typescript
  workstationUpdateCommand: (id: string) =>
    request<WorkstationUpdateCommand>(`/workstations/${id}/update-command`),
```

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "feat(ui): workstation update-command api + agent_outdated type"
```

---

## Task 6: Panel — version line, "Outdated" badge, "Update" dialog

**Files:**
- Modify: `frontend/src/components/system/workstations-panel.tsx`

- [ ] **Step 1: Add state for the update dialog**

Near the other `useState` calls (around line 20-21):

```typescript
  const [updateCmd, setUpdateCmd] = useState<import("@/api/client").WorkstationUpdateCommand | null>(null);
  const [updCopied, setUpdCopied] = useState<"lan" | "public" | null>(null);
```

Add a handler (near the other handlers, e.g. after `toggleUser`):

```typescript
  async function openUpdate(ws: Workstation) {
    setUpdateCmd(await api.workstationUpdateCommand(ws.id));
  }
  async function copyUpd(text: string, which: "lan" | "public") {
    await navigator.clipboard.writeText(text);
    setUpdCopied(which);
    setTimeout(() => setUpdCopied(null), 1500);
  }
```

- [ ] **Step 2: Show version + "Outdated" badge + "Update" button in each row**

In the row header `<div className="flex gap-2">` (the Revoke/Trash group, ~line 172),
add an "Update" button before "Revoke", shown only when outdated:

```tsx
                <div className="flex gap-2">
                  {ws.agent_outdated && (
                    <Button onClick={() => openUpdate(ws)} variant="secondary" size="sm">
                      Update
                    </Button>
                  )}
                  <Button
                    onClick={() => setRevokeTarget(ws)}
                    variant="secondary"
                    size="sm"
                    disabled={ws.status === "revoked"}
                  >
                    Revoke
                  </Button>
```

And surface the version in the `<dl>` grid (after the "Last seen" `<div>`, ~line 198):

```tsx
                <div><dt className="inline">Agent: </dt>
                  <dd className="inline">{ws.agent_version || "—"}
                    {ws.agent_outdated && (
                      <span className="ml-1 rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] text-amber-400">
                        outdated
                      </span>
                    )}
                  </dd></div>
```

- [ ] **Step 3: Add the update-command dialog**

Reuse the existing `Dialog` import already used by this panel (it imports
`ConfirmDialog`; add a plain `Dialog` if not present — check the existing imports
and add `import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";`
if missing). Place near the other dialogs at the end of the component (after the
revoke/purge `ConfirmDialog`s):

```tsx
      <Dialog open={updateCmd !== null} onOpenChange={(o) => { if (!o) setUpdateCmd(null); }}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>Update agent</DialogTitle>
          </DialogHeader>
          {updateCmd && (
            <div className="space-y-3 text-sm">
              <p className="text-muted-foreground">
                Run on the workstation to update {updateCmd.current_version || "—"} →{" "}
                {updateCmd.latest_version}. Restarts the agent; the desktop stays up.
              </p>
              {updateCmd.lan_command && (
                <div>
                  <p className="mb-1 text-xs text-muted-foreground">LAN</p>
                  <code className="block overflow-x-auto rounded bg-muted p-2 text-xs">
                    {updateCmd.lan_command}
                  </code>
                  <Button size="sm" variant="secondary" className="mt-1"
                          onClick={() => copyUpd(updateCmd.lan_command!, "lan")}>
                    <Copy className="h-4 w-4" /> {updCopied === "lan" ? "Copied" : "Copy"}
                  </Button>
                </div>
              )}
              <div>
                <p className="mb-1 text-xs text-muted-foreground">Public</p>
                <code className="block overflow-x-auto rounded bg-muted p-2 text-xs">
                  {updateCmd.public_command}
                </code>
                <Button size="sm" variant="secondary" className="mt-1"
                        onClick={() => copyUpd(updateCmd.public_command, "public")}>
                  <Copy className="h-4 w-4" /> {updCopied === "public" ? "Copied" : "Copy"}
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
```

- [ ] **Step 4: Typecheck**

Run (from `frontend/`): `npx tsc --noEmit`
Expected: no new errors. (Confirm `Copy` icon is already imported in this file — it
is used by the enroll-command copy buttons; if not, add it to the `lucide-react` import.)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/system/workstations-panel.tsx
git commit -m "feat(ui): outdated agent badge + update-command dialog"
```

---

## Done-when

- Admin list returns `agent_outdated` per workstation; old builds flagged, current/pending not.
- `GET /api/workstations/{id}/update-command` returns lan/public copy-paste commands (admin-gated, 404 unknown).
- Panel shows the agent version, an amber "outdated" badge, and an "Update" button opening a copy dialog.
- `pytest -q` green, `ruff` clean, `tsc --noEmit` clean.
