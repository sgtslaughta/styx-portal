# Onboarding & Diagnostics Phase 3 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use the **frontend-design** skill for the Health page (Task 6).

**Goal:** Operability + onboarding per spec `docs/superpowers/specs/2026-06-10-onboarding-diagnostics-phase3-design.md`: admin diagnostics with history + Health page, first-run setup validation, docker pull progress, and split docs.

**Architecture:** Backend adds a `diagnostics` service (timed, never-raising component checks) + a `health_store` ring buffer (reuse the `metrics_store` pattern) + a 60s sampler loop; admin endpoints expose current + historical health. Pull progress streams docker layer events into an in-memory store surfaced through the EXISTING instance status poll (no new transport). Frontend gets an admin Health page and a setup preflight panel; docs split into four files.

**Tech Stack:** FastAPI, SQLModel, pytest (backend); React 19 + TS, React Query, framer-motion (frontend, no unit runner — verify with `tsc --noEmit` + `vite build`).

**Conventions:**
- Backend dir `/home/user/code/remote-access/backend`; tests `.venv/bin/python -m pytest <path> -v`; lint `.venv/bin/python -m ruff check app/ tests/`. TDD: failing test first.
- Frontend dir `/home/user/code/remote-access/frontend`; verify `npx tsc --noEmit` + `npm run build`; manual checks (no unit runner).
- Commits: Conventional Commits, body ends `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Current baseline: 267 backend tests pass.

---

## File map

| File | Responsibility | Tasks |
|---|---|---|
| `backend/app/services/docker_manager.py` | add `ping()` + `version()` helpers | 1 |
| `backend/app/services/health_store.py` (new) | health-sample ring buffer | 2 |
| `backend/app/services/diagnostics.py` (new) | `run_diagnostics(session)` — timed checks | 3 |
| `backend/app/main.py` | diagnostics endpoints + 60s sampler loop | 4 |
| `frontend/src/api/client.ts` | diagnostics types + api methods | 5 |
| `frontend/src/components/system/health-panel.tsx` (new) | admin Health page | 6 |
| `frontend/src/components/settings/nav-config.tsx`, settings render switch | wire Health nav entry | 6 |
| `backend/app/routers/auth.py`, `backend/app/schemas.py` | `setup-preflight` endpoint | 7 |
| `frontend/src/pages/SetupWizard.tsx`, `frontend/src/api/client.ts` | preflight panel | 8 |
| `backend/app/services/pull_progress.py` (new), `docker_manager.py`, `routers/instances.py`, `schemas.py` | streaming pull + progress fields | 9 |
| `frontend/src/components/instances/*`, `frontend/src/api/client.ts` | pull progress bar | 10 |
| `README.md`, `docs/QUICKSTART.md`, `docs/PRODUCTION.md`, `docs/GPU.md`, `docs/ADMIN.md` (new) | docs split | 11 |

---

### Task 1: DockerManager `ping` + `version` helpers

**Files:** Modify `backend/app/services/docker_manager.py`. Test: `backend/tests/test_docker_manager.py`.

- [ ] **Step 1: Failing tests** (append; mirror the file's existing `mock_docker` fixture that patches `docker.DockerClient`):

```python
def test_ping_returns_true(mock_docker):
    mock_docker.ping.return_value = True
    assert DockerManager().ping() is True

def test_ping_false_on_error(mock_docker):
    mock_docker.ping.side_effect = Exception("down")
    assert DockerManager().ping() is False

def test_version_returns_string(mock_docker):
    mock_docker.version.return_value = {"Version": "29.5.2"}
    assert DockerManager().version() == "29.5.2"

def test_version_none_on_error(mock_docker):
    mock_docker.version.side_effect = Exception("x")
    assert DockerManager().version() is None
```

- [ ] **Step 2: Run, verify fail** — `pytest tests/test_docker_manager.py -k "ping or version" -v` → AttributeError.

- [ ] **Step 3: Implement** — add methods to `DockerManager`:

```python
    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except Exception:
            return False

    def version(self) -> str | None:
        try:
            return self._client.version().get("Version")
        except Exception:
            return None
```

- [ ] **Step 4: Run** — those tests + full suite → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(diagnostics): docker ping/version helpers via configured socket"`

---

### Task 2: `health_store` ring buffer

**Files:** Create `backend/app/services/health_store.py`. Test: `backend/tests/test_health_store.py`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_health_store.py
from app.services import health_store


def setup_function():
    health_store.reset()


def test_record_and_history():
    health_store.record(1000.0, {"docker": True, "disk": False}, {"docker": 5, "disk": 0})
    health_store.record(1060.0, {"docker": True, "disk": True}, {"docker": 4, "disk": 0})
    h = health_store.get_history("1h")
    assert h["timestamps"] == [1000.0, 1060.0]
    assert h["status"]["docker"] == [True, True]
    assert h["status"]["disk"] == [False, True]
    assert h["latency_ms"]["docker"] == [5, 4]


def test_range_slicing():
    for i in range(200):
        health_store.record(float(i), {"docker": True}, {"docker": 1})
    assert len(health_store.get_history("1h")["timestamps"]) == 120  # 1h = 120 samples
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement** — `backend/app/services/health_store.py`:

```python
"""In-memory ring buffer of diagnostic samples (status + latency per check).

Resets on process restart — acceptable for a single-host portal; not persisted."""
import time
from collections import deque
from threading import Lock

_MAXLEN = 2880  # 24h at 60s
_lock = Lock()
_timestamps: deque[float] = deque(maxlen=_MAXLEN)
_status: dict[str, deque[bool]] = {}
_latency: dict[str, deque[int]] = {}

_RANGES = {"1h": 60, "6h": 360, "24h": 2880}  # samples at 60s cadence


def reset() -> None:
    with _lock:
        _timestamps.clear()
        _status.clear()
        _latency.clear()


def record(ts: float, status: dict[str, bool], latency: dict[str, int]) -> None:
    with _lock:
        _timestamps.append(ts)
        n = len(_timestamps)
        for key, ok in status.items():
            _status.setdefault(key, deque(maxlen=_MAXLEN))
            # pad new keys so all series align to the timestamp length
            while len(_status[key]) < n - 1:
                _status[key].append(ok)
            _status[key].append(ok)
        for key, ms in latency.items():
            _latency.setdefault(key, deque(maxlen=_MAXLEN))
            while len(_latency[key]) < n - 1:
                _latency[key].append(ms)
            _latency[key].append(ms)


def get_history(range_str: str = "1h") -> dict:
    count = _RANGES.get(range_str, 60)
    with _lock:
        ts = list(_timestamps)[-count:]
        status = {k: list(v)[-count:] for k, v in _status.items()}
        latency = {k: list(v)[-count:] for k, v in _latency.items()}
    return {"timestamps": ts, "status": status, "latency_ms": latency}
```

(Note: `_RANGES["1h"] = 60` at 60s cadence. The test records 200 samples and expects 120 for "1h" — adjust: set `_RANGES = {"1h": 120, "6h": 720, "24h": 2880}` to match the metrics_store convention and the test. Use **120/720/2880**.)

Fix `_RANGES` to `{"1h": 120, "6h": 720, "24h": 2880}` so the slicing test passes.

- [ ] **Step 4: Run** — `pytest tests/test_health_store.py -v` + full suite → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(diagnostics): health-sample ring buffer"`

---

### Task 3: `diagnostics.run_diagnostics`

**Files:** Create `backend/app/services/diagnostics.py`. Test: `backend/tests/test_diagnostics.py`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_diagnostics.py
import pytest
from unittest.mock import MagicMock

from app.services import diagnostics


class _FakeDocker:
    def __init__(self, ok=True): self._ok = ok
    def ping(self): return self._ok
    def version(self): return "29.5.2" if self._ok else None


@pytest.mark.asyncio
async def test_all_ok(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    (tmp_path / "routes.yml").write_text("x")
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(True))
    keys = {c["key"] for c in result["checks"]}
    assert keys == {"docker", "database", "traefik_routes", "disk", "gpu"}
    assert all("latency_ms" in c for c in result["checks"])
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_docker_down_sets_not_ok(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(False))
    docker_check = next(c for c in result["checks"] if c["key"] == "docker")
    assert docker_check["ok"] is False
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_gpu_absence_is_informational(session, tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics._settings, "TRAEFIK_DYNAMIC_DIR", str(tmp_path))
    monkeypatch.setattr(diagnostics, "detect_gpu", lambda: {"available": False, "type": None})
    result = await diagnostics.run_diagnostics(session, docker=_FakeDocker(True))
    gpu = next(c for c in result["checks"] if c["key"] == "gpu")
    assert gpu["ok"] is True  # absence is not a failure
```

(Uses the `session` fixture from conftest. `detect_gpu` is imported into diagnostics so it's monkeypatchable there.)

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement** — `backend/app/services/diagnostics.py`:

```python
"""Component health checks. Every check is timed and never raises — a failure
becomes {ok: False, detail: <reason>}, not an exception."""
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app.config import Settings
from app.services.docker_manager import DockerManager, detect_gpu

_settings = Settings()
_DISK_FREE_WARN_PCT = 10.0


async def _timed(fn):
    start = time.monotonic()
    ok, detail = await fn()
    return ok, detail, round((time.monotonic() - start) * 1000)


async def _check_docker(docker) -> tuple[bool, str]:
    if not docker.ping():
        return False, "Docker not reachable (socket-proxy down?)"
    v = docker.version()
    return True, f"Engine {v or 'unknown'} via socket-proxy"


async def _check_database(session) -> tuple[bool, str]:
    try:
        await session.exec(text("SELECT 1"))
        return True, "writable"
    except Exception as e:  # noqa: BLE001
        return False, f"error: {e}"


def _check_traefik_routes() -> tuple[bool, str]:
    d = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    if not d.is_dir():
        return False, f"{d} missing"
    routes = d / "routes.yml"
    if routes.exists():
        age = int(time.time() - routes.stat().st_mtime)
        # writability probe
        try:
            (d / ".w").write_text("x"); (d / ".w").unlink()
        except Exception:  # noqa: BLE001
            return False, "directory not writable by backend user"
        return True, f"writable, routes.yml {age}s old"
    try:
        (d / ".w").write_text("x"); (d / ".w").unlink()
        return True, "writable, no routes yet"
    except Exception:  # noqa: BLE001
        return False, "directory not writable by backend user"


def _check_disk() -> tuple[bool, str]:
    du = shutil.disk_usage("/")
    free_pct = du.free / du.total * 100
    used_gb = (du.total - du.free) / 1024**3
    total_gb = du.total / 1024**3
    ok = free_pct >= _DISK_FREE_WARN_PCT
    return ok, f"{free_pct:.0f}% free ({used_gb:.0f}/{total_gb:.0f} GB)"


def _check_gpu() -> tuple[bool, str]:
    info = detect_gpu()
    return True, (f"{info['type']} detected" if info.get("available") else "none")


async def run_diagnostics(session, docker: DockerManager | None = None) -> dict:
    docker = docker or DockerManager(network_name=_settings.DOCKER_NETWORK)
    checks = []

    ok, detail, ms = await _timed(lambda: _check_docker(docker))
    checks.append({"key": "docker", "ok": ok, "latency_ms": ms, "detail": detail})

    ok, detail, ms = await _timed(lambda: _check_database(session))
    checks.append({"key": "database", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _tr(): return _check_traefik_routes()
    ok, detail, ms = await _timed(_tr)
    checks.append({"key": "traefik_routes", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _dk(): return _check_disk()
    ok, detail, ms = await _timed(_dk)
    checks.append({"key": "disk", "ok": ok, "latency_ms": ms, "detail": detail})

    async def _gp(): return _check_gpu()
    ok, detail, ms = await _timed(_gp)
    checks.append({"key": "gpu", "ok": ok, "latency_ms": ms, "detail": detail})

    # gpu is informational — exclude from overall ok
    overall = all(c["ok"] for c in checks if c["key"] != "gpu")
    return {
        "ok": overall,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
```

- [ ] **Step 4: Run** — `pytest tests/test_diagnostics.py -v` + full suite → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(diagnostics): timed component health checks"`

---

### Task 4: Diagnostics endpoints + background sampler

**Files:** Modify `backend/app/main.py`. Test: `backend/tests/test_diagnostics_api.py`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_diagnostics_api.py
def test_diagnostics_requires_admin(user_client):
    assert user_client.get("/api/system/diagnostics").status_code in (401, 403)

def test_diagnostics_admin_ok(admin_client):
    r = admin_client.get("/api/system/diagnostics")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body and "ok" in body

def test_diagnostics_history_admin_ok(admin_client):
    r = admin_client.get("/api/system/diagnostics/history?range=1h")
    assert r.status_code == 200
    assert "timestamps" in r.json()
```

(Reuse admin/user client fixtures. The admin diagnostics call will hit a real DockerManager → ping returns False in tests (no docker), which is fine: endpoint still 200 with docker check ok:false.)

- [ ] **Step 2: Run, verify fail** — 404.

- [ ] **Step 3: Implement** — in `main.py`, add endpoints near the other `/api/system/*`:

```python
@app.get("/api/system/diagnostics")
async def system_diagnostics(
    session: AsyncSession = Depends(get_session),
    admin: User = Depends(require_admin),
):
    from app.services.diagnostics import run_diagnostics
    return await run_diagnostics(session)


@app.get("/api/system/diagnostics/history")
async def system_diagnostics_history(
    range: str = "1h",
    admin: User = Depends(require_admin),
):
    from app.services.health_store import get_history
    return get_history(range)
```

Add a sampler loop + register it in `lifespan` (next to `_metrics_collection_loop`):

```python
async def _health_sample_loop():
    from app.services.diagnostics import run_diagnostics
    from app.services.health_store import record
    import time as _t
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                result = await run_diagnostics(session)
            status = {c["key"]: c["ok"] for c in result["checks"]}
            latency = {c["key"]: c["latency_ms"] for c in result["checks"]}
            record(_t.time(), status, latency)
        except Exception:
            pass
```

In `lifespan`, add `health_task = asyncio.create_task(_health_sample_loop())` alongside the others and `health_task.cancel()` on shutdown.

- [ ] **Step 4: Run** — `pytest tests/test_diagnostics_api.py -v` + full suite → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(diagnostics): admin endpoints + 60s sampler loop"`

---

### Task 5: Frontend diagnostics API types

**Files:** Modify `frontend/src/api/client.ts`.

- [ ] **Step 1: Add types + methods.** Add types near the other exports:

```tsx
export type DiagCheck = { key: string; ok: boolean; latency_ms: number; detail: string };
export type Diagnostics = { ok: boolean; checked_at: string; checks: DiagCheck[] };
export type DiagHistory = {
  timestamps: number[];
  status: Record<string, boolean[]>;
  latency_ms: Record<string, number[]>;
};
```

Add to the `api` object:

```tsx
  getDiagnostics: () => request<Diagnostics>("/system/diagnostics"),
  getDiagnosticsHistory: (range: string) =>
    request<DiagHistory>(`/system/diagnostics/history?range=${range}`),
```

- [ ] **Step 2: Verify** — `npx tsc --noEmit` + `npm run build`.
- [ ] **Step 3: Commit** — `git add -A && git commit -m "feat(diagnostics): frontend api types"`

---

### Task 6: Health page (admin)

**Files:** Create `frontend/src/components/system/health-panel.tsx`; wire into settings nav + render switch (`nav-config.tsx` + the settings content switch — find where `id: "monitoring"` items map to components).

- [ ] **Step 1: Use the frontend-design skill** for the panel layout/polish.

- [ ] **Step 2: Create `health-panel.tsx`:**

```tsx
import { useQuery } from "@tanstack/react-query";
import { api, type DiagCheck } from "@/api/client";
import { Button } from "@/components/ui/button";
import { RefreshCw, CheckCircle2, XCircle } from "lucide-react";

const LABELS: Record<string, string> = {
  docker: "Docker engine",
  database: "Database",
  traefik_routes: "Traefik routing",
  disk: "Disk space",
  gpu: "GPU",
};

const HINTS: Record<string, string> = {
  traefik_routes: "Routes volume must be writable by the backend user — see Production guide.",
  docker: "Is the docker-socket-proxy container healthy?",
  disk: "Free space is low — prune images or expand storage.",
};

export function HealthPanel() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["diagnostics"],
    queryFn: api.getDiagnostics,
    refetchInterval: 30000,
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">System health</h2>
        <Button size="sm" variant="secondary" disabled={isFetching} onClick={() => refetch()}>
          <RefreshCw className={`mr-2 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
          Run checks
        </Button>
      </div>

      {data && (
        <div className={`rounded-md border p-3 text-sm font-medium ${
          data.ok ? "border-success/40 bg-success/5 text-success"
                  : "border-destructive/40 bg-destructive/5 text-destructive"}`}>
          {data.ok ? "All systems operational" : "One or more checks are failing"}
        </div>
      )}

      <div className="space-y-2">
        {(data?.checks ?? []).map((c: DiagCheck) => (
          <div key={c.key} className="flex items-start gap-3 rounded-md border border-border p-3">
            {c.ok ? <CheckCircle2 className="mt-0.5 h-4 w-4 text-success" />
                  : <XCircle className="mt-0.5 h-4 w-4 text-destructive" />}
            <div className="flex-1">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{LABELS[c.key] ?? c.key}</span>
                <span className="text-xs text-muted-foreground">{c.latency_ms} ms</span>
              </div>
              <p className="text-xs text-muted-foreground">{c.detail}</p>
              {!c.ok && HINTS[c.key] && (
                <p className="mt-1 text-xs text-warning">{HINTS[c.key]}</p>
              )}
            </div>
          </div>
        ))}
        {isLoading && <p className="text-sm text-muted-foreground">Running checks…</p>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add a status-over-time strip.** Below the checks, fetch history and render simple up/down bars per check:

```tsx
import { type DiagHistory } from "@/api/client";
// inside component:
const { data: history } = useQuery({
  queryKey: ["diagnostics-history"],
  queryFn: () => api.getDiagnosticsHistory("1h"),
  refetchInterval: 60000,
});
```

Render after the checks list:

```tsx
{history && Object.keys(history.status).length > 0 && (
  <div className="space-y-2">
    <h3 className="text-sm font-medium">Last hour</h3>
    {Object.entries(history.status).map(([key, series]) => (
      <div key={key} className="flex items-center gap-2">
        <span className="w-28 shrink-0 text-xs text-muted-foreground">{LABELS[key] ?? key}</span>
        <div className="flex flex-1 gap-px">
          {(series as boolean[]).map((up, i) => (
            <span key={i} className={`h-3 flex-1 rounded-sm ${up ? "bg-success/70" : "bg-destructive/70"}`} />
          ))}
        </div>
      </div>
    ))}
  </div>
)}
```

- [ ] **Step 4: Wire into settings nav.** In `nav-config.tsx`, add a Health sub-item under the `monitoring` category (admin-only already): `{ id: "health", label: "Health", icon: Activity, ... }` (match the existing sub-item shape). Then in the settings content switch (where `id` values render their component — grep for `"overview"`/`"sessions"` JSX or a map), add a case rendering `<HealthPanel />` for `id === "health"`. Read those files to match the exact wiring pattern (icon imports from lucide-react).

- [ ] **Step 5: Verify** — `npx tsc --noEmit` + `npm run build`. Manual: as admin, Settings → Monitoring → Health shows the check list (in dev without docker, Docker check is red with the hint; DB/disk green), auto-refreshes, "Run checks" works, the last-hour strip appears after the sampler has data (or is empty initially).
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(diagnostics): admin Health page with checks and history strip"`

---

### Task 7: Setup preflight endpoint

**Files:** Modify `backend/app/routers/auth.py`, `backend/app/config.py` (read DEPLOY_MODE — already exists). Test: `backend/tests/test_setup_preflight.py`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_setup_preflight.py
def test_preflight_available_before_setup(client):
    # fresh db, no users
    r = client.get("/api/auth/setup-preflight")
    assert r.status_code == 200
    body = r.json()
    assert "docker" in body and "deploy_mode" in body and "domain_set" in body and "data_writable" in body

def test_preflight_404_after_user_exists(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "Str0ng-passw0rd!"})
    assert client.get("/api/auth/setup-preflight").status_code == 404
```

(Match the conftest client fixture + the setup payload shape used by existing auth tests. Setup is CSRF-exempt so no header needed.)

- [ ] **Step 2: Run, verify fail** — 404 on the first test.

- [ ] **Step 3: Implement** — in `auth.py`:

```python
@router.get("/setup-preflight")
async def setup_preflight(session: AsyncSession = Depends(get_session)):
    # Only meaningful during genuine first-run; hide once an admin exists so we
    # never expose infra status post-setup without auth.
    if await users_exist(session):
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    from app.services.docker_manager import DockerManager
    from pathlib import Path
    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    reachable = await __import__("asyncio").to_thread(docker.ping)
    data_dir = Path(_settings.SCREENSHOT_CACHE_DIR).parent  # /app/data
    try:
        (data_dir / ".w").write_text("x"); (data_dir / ".w").unlink()
        writable = True
    except Exception:  # noqa: BLE001
        writable = False
    return {
        "docker": {"ok": reachable,
                   "detail": "reachable" if reachable else "not reachable — is docker-proxy running?"},
        "deploy_mode": _settings.DEPLOY_MODE,
        "domain_set": bool(_settings.DOMAIN) and _settings.DOMAIN != "localhost",
        "data_writable": writable,
    }
```

(Clean up the inline `__import__("asyncio")` — add `import asyncio` at the top of auth.py if not present and use `await asyncio.to_thread(docker.ping)`.)

- [ ] **Step 4: Run** — `pytest tests/test_setup_preflight.py -v` + full suite → PASS.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(onboarding): first-run setup preflight endpoint"`

---

### Task 8: Setup wizard preflight panel

**Files:** Modify `frontend/src/pages/SetupWizard.tsx`, `frontend/src/api/client.ts`.

- [ ] **Step 1: API.** Add to `client.ts`:

```tsx
export type SetupPreflight = {
  docker: { ok: boolean; detail: string };
  deploy_mode: string;
  domain_set: boolean;
  data_writable: boolean;
};
// in api object:
  setupPreflight: () => request<SetupPreflight>("/auth/setup-preflight"),
```

- [ ] **Step 2: SetupWizard panel.** Add a query + render a panel above the create-admin form:

```tsx
import { useQuery } from "@tanstack/react-query";
// inside component:
const { data: pre } = useQuery({ queryKey: ["setup-preflight"], queryFn: api.setupPreflight, retry: false });
```

Render above the form (non-blocking):

```tsx
{pre && (
  <div className="space-y-1 rounded-md border border-border p-3 text-xs">
    <p className="font-medium">Environment check</p>
    <PreRow ok={pre.docker.ok} label="Docker" detail={pre.docker.detail} />
    <PreRow ok={pre.data_writable} label="Data volume" detail={pre.data_writable ? "writable" : "not writable"} />
    <PreRow ok={pre.domain_set} label="Domain" detail={pre.domain_set ? "configured" : "DOMAIN not set — using localhost"} warnOnly />
    <p className="text-muted-foreground">Ingress mode: {pre.deploy_mode}</p>
  </div>
)}
```

Add a small `PreRow` helper component in the file:

```tsx
function PreRow({ ok, label, detail, warnOnly }: { ok: boolean; label: string; detail: string; warnOnly?: boolean }) {
  const color = ok ? "text-success" : warnOnly ? "text-warning" : "text-destructive";
  return (
    <div className="flex items-center justify-between">
      <span>{label}</span>
      <span className={color}>{ok ? "✓" : warnOnly ? "!" : "✗"} {detail}</span>
    </div>
  );
}
```

- [ ] **Step 3: Verify** — `npx tsc --noEmit` + `npm run build`. Manual: with no users, `/setup` shows the env-check panel (Docker red in dev without proxy, data writable green, domain warning if localhost); the create-admin form still works below it.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(onboarding): setup wizard environment preflight panel"`

---

### Task 9: Docker pull progress (backend)

**Files:** Create `backend/app/services/pull_progress.py`; modify `backend/app/services/docker_manager.py`, `backend/app/routers/instances.py`, `backend/app/schemas.py`. Test: `backend/tests/test_pull_progress.py`.

- [ ] **Step 1: Failing tests**

```python
# backend/tests/test_pull_progress.py
from app.services import pull_progress


def setup_function():
    pull_progress.clear("i1")


def test_set_and_get():
    pull_progress.set_progress("i1", 42, "Downloading")
    p = pull_progress.get("i1")
    assert p == {"percent": 42, "detail": "Downloading"}


def test_get_missing_returns_none():
    assert pull_progress.get("nope") is None


def test_clear():
    pull_progress.set_progress("i1", 10, "x")
    pull_progress.clear("i1")
    assert pull_progress.get("i1") is None


def test_overall_percent_from_layers():
    events = [
        {"id": "a", "progressDetail": {"current": 50, "total": 100}},
        {"id": "b", "progressDetail": {"current": 0, "total": 100}},
    ]
    assert pull_progress.overall_percent(events) == 25
```

- [ ] **Step 2: Run, verify fail** — ImportError.

- [ ] **Step 3: Implement** — `backend/app/services/pull_progress.py`:

```python
"""In-memory per-instance image-pull progress, surfaced via the instance status
poll (no new transport). Resets on restart."""
from threading import Lock

_lock = Lock()
_progress: dict[str, dict] = {}


def set_progress(instance_id: str, percent: int, detail: str) -> None:
    with _lock:
        _progress[instance_id] = {"percent": percent, "detail": detail}


def get(instance_id: str) -> dict | None:
    with _lock:
        return _progress.get(instance_id)


def clear(instance_id: str) -> None:
    with _lock:
        _progress.pop(instance_id, None)


def overall_percent(layers: list[dict]) -> int:
    """Rough overall % across layers that report totals."""
    cur = tot = 0
    for ev in layers:
        d = ev.get("progressDetail") or {}
        if d.get("total"):
            cur += d.get("current", 0)
            tot += d["total"]
    return int(cur / tot * 100) if tot else 0
```

- [ ] **Step 4: Streaming pull in DockerManager.** Add a method that streams and reports progress via callback:

```python
    def pull_image_streaming(self, image, on_progress=None):
        """Pull with layer-progress events. on_progress(percent:int, detail:str)."""
        repo, _, tag = image.partition(":")
        layers: dict[str, dict] = {}
        for ev in self._client.api.pull(repo, tag=tag or "latest", stream=True, decode=True):
            if ev.get("id"):
                layers[ev["id"]] = ev
            if on_progress:
                from app.services.pull_progress import overall_percent
                on_progress(overall_percent(list(layers.values())),
                            ev.get("status", "Pulling"))
```

In the launch path (`instances.py` `_launch_instance_background`), when `needs_pull`, call the streaming pull BEFORE `create_container`, writing progress to the store; then create_container finds the image present (its internal `images.get` succeeds, no re-pull):

```python
            if needs_pull:
                from app.services import pull_progress
                def _cb(pct, detail, _id=instance.id):
                    pull_progress.set_progress(_id, pct, detail)
                await asyncio.to_thread(docker.pull_image_streaming, template.image, _cb)
                pull_progress.clear(instance.id)
```

(Place this right after setting status "pulling" + commit, before the volume/create steps. The existing `create_container` internal pull stays as a fallback for the no-progress path.)

- [ ] **Step 5: Surface in status.** `schemas.py` `InstanceStatus` — add:

```python
    pull_percent: int | None = None
    pull_detail: str | None = None
```

`instances.py` status endpoint — read the store:

```python
    from app.services import pull_progress
    pp = pull_progress.get(instance_id)
    return InstanceStatus(
        ...,  # existing fields
        pull_percent=pp["percent"] if pp else None,
        pull_detail=pp["detail"] if pp else None,
    )
```

- [ ] **Step 6: Run** — `pytest tests/test_pull_progress.py -v` + full suite → PASS. (Mock note: existing launch tests mock the docker manager; `pull_image_streaming` on a MagicMock is a no-op — verify those tests still pass.)
- [ ] **Step 7: Commit** — `git add -A && git commit -m "feat(instances): streaming image pull with progress in status poll"`

---

### Task 10: Pull progress bar (frontend)

**Files:** Modify `frontend/src/api/client.ts` (InstanceStatus type), and the component that renders a `pulling` instance (`instance-card.tsx` and/or `instance-detail-pane.tsx` — whichever shows pull state; it polls `getInstanceStatus`).

- [ ] **Step 1: Type.** In `client.ts`, the `getInstanceStatus` return type — add `pull_percent: number | null; pull_detail: string | null;` (find the inline type on `getInstanceStatus` or the `InstanceStatus` type in `lib/types.ts`).

- [ ] **Step 2: Render.** Where an instance shows `pulling` status, if a status poll is available with `pull_percent`, render a thin bar:

```tsx
{status?.pull_percent != null && (
  <div className="space-y-1">
    <div className="flex justify-between text-xs text-muted-foreground">
      <span>{status.pull_detail ?? "Pulling image"}</span>
      <span>{status.pull_percent}%</span>
    </div>
    <div className="h-1.5 overflow-hidden rounded-full bg-muted">
      <div className="h-full bg-primary transition-all" style={{ width: `${status.pull_percent}%` }} />
    </div>
  </div>
)}
```

If the component doesn't already poll status during `pulling`, add a `useQuery` keyed `["instance-status", id]` with `queryFn: () => api.getInstanceStatus(id)` and `refetchInterval: 2000` ENABLED ONLY while `instance.status === "pulling"` (`enabled: instance.status === "pulling"`). Read the file to see if a status poll already exists (the idle/keepalive work in Phase 2 may have added one) and reuse it.

Fallback: when `pull_percent` is null but status is `pulling`, show an indeterminate "Pulling image…" label (no bar).

- [ ] **Step 3: Verify** — `npx tsc --noEmit` + `npm run build`. Manual (needs a real pull, so optional in dev): launch a template whose image isn't cached → card shows a progress bar climbing; cached image → goes straight to starting with no bar.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(instances): image pull progress bar while pulling"`

---

### Task 11: Docs split

**Files:** Modify `README.md`; create `docs/QUICKSTART.md`, `docs/PRODUCTION.md`, `docs/GPU.md`, `docs/ADMIN.md`.

- [ ] **Step 1: QUICKSTART.md** — the 5-minute happy path: prerequisites (Docker + compose), `git clone`, `cp .env.example .env`, set `DOMAIN` + `CF_TUNNEL_TOKEN` (tunnel mode, the default), leave `JWT_SECRET` empty, `docker compose up -d`, open the domain, create the admin account in the wizard. One screen, tunnel mode only.

- [ ] **Step 2: PRODUCTION.md** — checklist: direct-mode TLS (`COMPOSE_PROFILES=direct`, `DEPLOY_MODE=direct`, `LE_EMAIL`, `CF_DNS_API_TOKEN`, the wildcard DNS-01 note); backups (back up the `db-data` volume incl. `secrets.json` — losing it logs everyone out + invalidates OAuth secrets); security posture (socket-proxy with EXEC/BUILD/SYSTEM denied, confined containers, DinD admin-only + needs limits, audit log at `GET /api/audit`, Traefik dashboard off); health monitoring (`GET /api/system/diagnostics`, the Health page); the Phase-1 host-only gates (seed-template capability tuning, `VIDEO_GID`/`RENDER_GID`); upgrade notes (migrations auto-run on boot).

- [ ] **Step 3: GPU.md** — NVIDIA driver + container runtime prerequisites; `VIDEO_GID`/`RENDER_GID` via `getent group video render`; how to verify GPU inside a container; gpu_enabled/gpu_count template fields; troubleshooting (device not found, driver mismatch).

- [ ] **Step 4: ADMIN.md** — inviting users (the invite-link box, 72h single-use); roles + SSO providers (OIDC/OAuth, `trust_email`, `allow_signup`, `auto_promote_admins`, role mapping); templates (custom images, resource limits, DinD admin-only + mandatory limits, `cap_add`/`security_opt` admin-gated); reading the audit log + Health page; quotas (`MAX_INSTANCES_PER_USER`).

- [ ] **Step 5: Slim README.md** — keep the architecture overview; replace the stale "Authentik ForwardAuth" auth framing with "native JWT + OIDC/OAuth SSO"; add a "## Documentation" section linking the four docs:

```markdown
## Documentation
- [Quick Start](docs/QUICKSTART.md) — get running in 5 minutes
- [Production Deployment](docs/PRODUCTION.md) — TLS, backups, hardening, monitoring
- [GPU Setup](docs/GPU.md) — drivers, runtime, troubleshooting
- [Admin Guide](docs/ADMIN.md) — users, SSO, templates, audit, quotas
```

Keep the existing "Upgrading from Selkies Hub" + Development sections.

- [ ] **Step 6: Verify** — no code; eyeball each doc renders (headings, code fences). `docs/` already tracked (the `/plans/` gitignore anchor from Phase 1 doesn't block `docs/`).
- [ ] **Step 7: Commit** — `git add -A README.md docs/ && git commit -m "docs: split into quick-start, production, gpu, admin guides"`

---

## Spec coverage map

| Spec group | Tasks |
|---|---|
| A — Diagnostics endpoint + history | 1, 2, 3, 4 |
| B — Health page | 5, 6 |
| C — Setup-wizard validation | 7, 8 |
| D — Docker pull progress | 9, 10 |
| E — Docs split | 11 |

## Notes for the executor

- Backend tasks (1–4, 7, 9) follow TDD with pytest; full suite + ruff green before each commit.
- Frontend tasks (5, 6, 8, 10) verify with `tsc --noEmit` + `vite build` + the manual checks (no unit runner).
- Diagnostic checks must NEVER raise — the `_timed` wrapper + per-check try/except enforce this; keep it.
- Pull progress reuses the existing status poll — do NOT add SSE/WebSocket.
- Health history + pull progress are in-memory (reset on restart) — that's the spec's accepted tradeoff; don't add DB persistence.
- Use the **frontend-design** skill for Task 6 (the Health page is the one design-substantive piece).
