# Stopped-Instance Dynamic Redirect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hitting a not-running instance URL (`/i/{subdomain}/`) redirects to the My Instances page with a toast, instead of a Cloudflare/Traefik error.

**Architecture:** A backend HTML page (`/api/instance-unavailable`) whose JS derives the subdomain from the URL and redirects to `/?stopped={sub}`. Traefik delivers it two ways: a low-priority `/i/` catch-all router (cleanly-stopped / unknown), and an `errors` middleware on each instance router (dead-origin 5xx). A shared `refresh_routes_from_db` helper plus an auto-stop/crashed-container reconciler removes stale routes so the 5xx rarely happens. The frontend reads `?stopped` and shows a toast.

**Tech Stack:** FastAPI, Traefik v3 (file provider via `route_writer.py`), SQLModel, React/TypeScript, sonner.

---

## File Structure

- `backend/app/services/route_writer.py` — extract pure `build_routes_config()`; add fallback router + two middlewares + per-instance errors middleware; add async `refresh_routes_from_db()`.
- `backend/app/main.py` — `/api/instance-unavailable` endpoint; use `refresh_routes_from_db` in lifespan; extract `_run_monitor_pass()` (auto-stop + crashed reconcile) and refresh routes when it reports changes.
- `backend/app/routers/instances.py` — `_refresh_routes` delegates to `refresh_routes_from_db`.
- `backend/tests/test_route_writer.py` — new; config-shape tests.
- `backend/tests/test_redirect.py` — new; endpoint + reconcile/refresh tests.
- `frontend/src/App.tsx` — read `?stopped`, toast, clean URL.

---

## Task 1: Backend redirect page endpoint

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_redirect.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_redirect.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_instance_unavailable_page(client):
    resp = await client.get("/api/instance-unavailable")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    body = resp.text
    # JS derives subdomain from the path and redirects to /?stopped=...
    assert "location.replace" in body
    assert "/i/" in body
    assert "stopped=" in body
    # no-JS fallback to My Instances
    assert 'href="/"' in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_redirect.py -v`
Expected: FAIL — 404 (route not defined).

- [ ] **Step 3: Add the endpoint**

In `backend/app/main.py`, add this import near the top (with the other fastapi imports):

```python
from fastapi.responses import HTMLResponse
```

Then add this endpoint after the existing `@app.get("/api/health")` handler:

```python
_INSTANCE_UNAVAILABLE_HTML = """<!doctype html>
<meta charset="utf-8">
<title>Instance unavailable</title>
<meta http-equiv="refresh" content="3;url=/">
<script>
  (function () {
    var m = location.pathname.match(/^\\/i\\/([^\\/]+)/);
    var q = m ? "?stopped=" + encodeURIComponent(m[1]) : "";
    location.replace("/" + q);
  })();
</script>
<p>Instance unavailable. Redirecting&hellip; <a href="/">My Instances</a></p>
"""


@app.get("/api/instance-unavailable", response_class=HTMLResponse)
async def instance_unavailable():
    return HTMLResponse(content=_INSTANCE_UNAVAILABLE_HTML)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_redirect.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_redirect.py
git commit -m "feat(redirect): backend /api/instance-unavailable page"
```

---

## Task 2: route_writer — fallback router, middlewares, shared helper

**Files:**
- Modify: `backend/app/services/route_writer.py`
- Test: `backend/tests/test_route_writer.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_route_writer.py`:

```python
from app.services.route_writer import build_routes_config


def test_static_routers_present():
    cfg = build_routes_config([], "example.com")
    routers = cfg["http"]["routers"]
    assert routers["frontend"]["priority"] == 1
    assert routers["api"]["priority"] == 100
    # catch-all fallback for /i/ paths
    fb = routers["instances_fallback"]
    assert fb["rule"] == "Host(`example.com`) && PathPrefix(`/i/`)"
    assert fb["priority"] == 10
    assert fb["service"] == "api"
    assert fb["middlewares"] == ["unavailable-rewrite"]


def test_static_middlewares_present():
    cfg = build_routes_config([], "example.com")
    mws = cfg["http"]["middlewares"]
    assert mws["unavailable-rewrite"] == {
        "replacePath": {"path": "/api/instance-unavailable"}
    }
    assert mws["instance-unavailable-errors"] == {
        "errors": {
            "status": ["500-599"],
            "service": "api",
            "query": "/api/instance-unavailable",
        }
    }


def test_instance_router_wraps_errors_then_strip():
    inst = {"id": "abc", "subdomain": "dev", "port": 3001, "protocol": "https"}
    cfg = build_routes_config([inst], "example.com")
    router = cfg["http"]["routers"]["abc"]
    assert router["rule"] == "Host(`example.com`) && PathPrefix(`/i/dev`)"
    assert router["priority"] == 50
    # errors middleware must wrap (come before) the strip middleware
    assert router["middlewares"] == ["instance-unavailable-errors", "strip-dev"]
    assert cfg["http"]["middlewares"]["strip-dev"] == {
        "stripPrefix": {"prefixes": ["/i/dev"]}
    }
    # https service keeps insecure-skip transport
    assert cfg["http"]["services"]["abc"]["loadBalancer"]["serversTransport"] == "selkies-transport"
    assert cfg["http"]["serversTransports"]["selkies-transport"] == {"insecureSkipVerify": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer.py -v`
Expected: FAIL — `build_routes_config` does not exist.

- [ ] **Step 3: Refactor route_writer with the pure builder + helper**

Replace the ENTIRE contents of `backend/app/services/route_writer.py` with:

```python
import yaml
from pathlib import Path

from app.config import Settings

_settings = Settings()


def build_routes_config(instances: list[dict], domain: str) -> dict:
    """Build the Traefik dynamic config dict for all services + running instances.

    Always emits the static `unavailable-rewrite` / `instance-unavailable-errors`
    middlewares and the low-priority `instances_fallback` router so stopped /
    unknown `/i/` requests get redirected to the My Instances page.
    """
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
    }
    config: dict = {
        "http": {
            "routers": {
                "frontend": {
                    "rule": f"Host(`{domain}`)",
                    "entryPoints": ["web"],
                    "service": "frontend",
                    "priority": 1,
                },
                "api": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/api`)",
                    "entryPoints": ["web"],
                    "service": "api",
                    "priority": 100,
                },
                "dashboard": {
                    "rule": f"Host(`traefik.{domain}`)",
                    "entryPoints": ["web"],
                    "service": "api@internal",
                },
                "instances_fallback": {
                    "rule": f"Host(`{domain}`) && PathPrefix(`/i/`)",
                    "entryPoints": ["web"],
                    "middlewares": ["unavailable-rewrite"],
                    "service": "api",
                    "priority": 10,
                },
            },
            "services": {
                "frontend": {
                    "loadBalancer": {"servers": [{"url": "http://frontend:3000"}]}
                },
                "api": {
                    "loadBalancer": {"servers": [{"url": "http://backend:8000"}]}
                },
            },
        }
    }

    has_https = False
    for inst in instances:
        inst_id = inst["id"]
        subdomain = inst["subdomain"]
        port = inst.get("port", 3001)
        protocol = inst.get("protocol", "https")
        container_name = f"selkies-{subdomain}"

        strip_mw = f"strip-{subdomain}"
        middlewares[strip_mw] = {"stripPrefix": {"prefixes": [f"/i/{subdomain}"]}}

        config["http"]["routers"][inst_id] = {
            "rule": f"Host(`{domain}`) && PathPrefix(`/i/{subdomain}`)",
            "entryPoints": ["web"],
            "middlewares": ["instance-unavailable-errors", strip_mw],
            "service": inst_id,
            "priority": 50,
        }
        svc_config: dict = {
            "servers": [{"url": f"{protocol}://{container_name}:{port}"}],
        }
        if protocol == "https":
            svc_config["serversTransport"] = "selkies-transport"
            has_https = True
        config["http"]["services"][inst_id] = {"loadBalancer": svc_config}

    config["http"]["middlewares"] = middlewares
    if has_https:
        config["http"]["serversTransports"] = {
            "selkies-transport": {"insecureSkipVerify": True}
        }
    return config


def write_routes(instances: list[dict], domain: str | None = None):
    """Render the Traefik dynamic config to the file provider directory."""
    domain = domain or _settings.DOMAIN
    out_dir = Path(_settings.TRAEFIK_DYNAMIC_DIR)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        return
    config = build_routes_config(instances, domain)
    (out_dir / "routes.yml").write_text(yaml.dump(config, default_flow_style=False))


async def refresh_routes_from_db(session):
    """Query running/idle instances and (re)write the Traefik routes file."""
    from sqlmodel import select
    from app.models import Instance, ServiceTemplate

    result = await session.exec(
        select(Instance).where(Instance.status.in_(["running", "idle"]))
    )
    running = result.all()
    data = []
    for i in running:
        tmpl = await session.get(ServiceTemplate, i.template_id)
        data.append({
            "id": i.id,
            "subdomain": i.subdomain,
            "port": tmpl.internal_port if tmpl else 3001,
            "protocol": tmpl.internal_protocol if tmpl else "https",
        })
    write_routes(data)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_route_writer.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/route_writer.py backend/tests/test_route_writer.py
git commit -m "feat(routing): /i/ fallback router + errors middleware + shared refresh helper"
```

---

## Task 3: Wire shared helper + auto-stop/crashed reconcile

**Files:**
- Modify: `backend/app/routers/instances.py:36-50` (`_refresh_routes`)
- Modify: `backend/app/main.py` (lifespan startup block + `_session_monitor_loop`)
- Test: `backend/tests/test_redirect.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_redirect.py`:

```python
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.models import Instance, ServiceTemplate
from app.services.route_writer import refresh_routes_from_db
from app.services.session_monitor import SessionMonitor
from app.main import _run_monitor_pass


async def _make_template(session):
    t = ServiceTemplate(
        name="t", display_name="T", image="img:latest",
        internal_port=3001, internal_protocol="https",
    )
    session.add(t)
    await session.commit()
    await session.refresh(t)
    return t


@pytest.mark.asyncio
async def test_refresh_routes_from_db_only_running(session, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        "app.services.route_writer.write_routes",
        lambda data, domain=None: captured.setdefault("data", data),
    )
    t = await _make_template(session)
    session.add(Instance(template_id=t.id, name="a", subdomain="a", status="running", container_id="c-a"))
    session.add(Instance(template_id=t.id, name="b", subdomain="b", status="stopped", container_id=None))
    await session.commit()

    await refresh_routes_from_db(session)

    subs = {d["subdomain"] for d in captured["data"]}
    assert subs == {"a"}
    assert captured["data"][0]["protocol"] == "https"


@pytest.mark.asyncio
async def test_monitor_pass_marks_crashed_container_stopped(session):
    t = await _make_template(session)
    inst = Instance(template_id=t.id, name="x", subdomain="x", status="running", container_id="c-x")
    session.add(inst)
    await session.commit()

    docker = MagicMock()
    docker.get_container_status.return_value = {"status": "exited"}
    monitor = SessionMonitor(docker)

    changed = await _run_monitor_pass(session, monitor, docker)
    await session.commit()
    await session.refresh(inst)

    assert changed is True
    assert inst.status == "stopped"


@pytest.mark.asyncio
async def test_monitor_pass_auto_stops_idle(session):
    t = await _make_template(session)
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    inst = Instance(
        template_id=t.id, name="y", subdomain="y", status="idle",
        container_id="c-y", last_activity=old, started_at=old,
        session_config={"idle_timeout": "30m", "grace_period": "5m"},
    )
    session.add(inst)
    await session.commit()

    docker = MagicMock()
    docker.get_container_status.return_value = {"status": "running"}
    docker.stop_container.return_value = None
    monitor = SessionMonitor(docker)

    changed = await _run_monitor_pass(session, monitor, docker)
    await session.commit()
    await session.refresh(inst)

    assert changed is True
    assert inst.status == "stopped"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_redirect.py -v`
Expected: FAIL — `_run_monitor_pass` not importable from `app.main`.

- [ ] **Step 3: Delegate `_refresh_routes` in instances.py**

In `backend/app/routers/instances.py`, replace the whole `_refresh_routes` function (lines 36-50) with:

```python
async def _refresh_routes(session: AsyncSession):
    from app.services.route_writer import refresh_routes_from_db

    await refresh_routes_from_db(session)
```

- [ ] **Step 4: Add `datetime` import + `_run_monitor_pass` to main.py**

In `backend/app/main.py`, add this import near the top (after the existing imports):

```python
from datetime import datetime, timezone
```

Add `_run_monitor_pass` just above `_session_monitor_loop`:

```python
async def _run_monitor_pass(session, monitor, docker) -> bool:
    """One reconcile pass over running/idle instances. Marks crashed containers
    stopped and applies idle auto-stop. Returns True if any instance stopped."""
    result = await session.exec(
        select(Instance).where(Instance.status.in_(["running", "idle"]))
    )
    instances = result.all()
    changed = False
    for inst in instances:
        if inst.container_id:
            status = await asyncio.to_thread(docker.get_container_status, inst.container_id)
            if status["status"] in ("not_found", "exited"):
                inst.status = "stopped"
                inst.stopped_at = datetime.now(timezone.utc)
                session.add(inst)
                changed = True
                continue
        actions = monitor.check_instance(inst, session)
        if "auto_stopped" in actions:
            changed = True
    return changed
```

- [ ] **Step 5: Use the pass + refresh in `_session_monitor_loop`**

In `backend/app/main.py`, replace the body of `_session_monitor_loop` (the `while True:` block) with:

```python
async def _session_monitor_loop():
    from app.services.route_writer import refresh_routes_from_db

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    monitor = SessionMonitor(docker)
    while True:
        await asyncio.sleep(60)
        try:
            async with async_session() as session:
                changed = await _run_monitor_pass(session, monitor, docker)
                await session.commit()
                if changed:
                    await refresh_routes_from_db(session)
        except Exception:
            pass
```

- [ ] **Step 6: Replace the lifespan startup route block with the helper**

In `backend/app/main.py`, replace the startup route-writing block (currently the `from app.services.route_writer import write_routes` block that builds `instances_data` and calls `write_routes`) with:

```python
    # Write initial Traefik routes on startup
    from app.services.route_writer import refresh_routes_from_db
    async with async_session() as session:
        await refresh_routes_from_db(session)
```

- [ ] **Step 7: Run tests + full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, no lint errors.

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/app/routers/instances.py backend/tests/test_redirect.py
git commit -m "fix(routing): refresh routes on auto-stop + reconcile crashed containers"
```

---

## Task 4: Frontend `?stopped` toast

**Files:**
- Modify: `frontend/src/App.tsx`

No frontend unit harness; verify via build.

- [ ] **Step 1: Import useEffect + toast**

In `frontend/src/App.tsx`, change the first import line:

```tsx
import { useState } from "react";
```

to:

```tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
```

- [ ] **Step 2: Add the effect inside the `App` component**

In `frontend/src/App.tsx`, add this effect right after the `useState` declarations inside `export default function App()` (before the `handleImportRegistry` function):

```tsx
  useEffect(() => {
    const sp = new URLSearchParams(window.location.search);
    const stopped = sp.get("stopped");
    if (stopped) {
      toast.error(`Instance "${stopped}" is stopped`);
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, []);
```

- [ ] **Step 3: Build to verify**

Run: `cd frontend && npm run build`
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat(instances): toast when redirected from a stopped instance"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/` — all pass.
- [ ] **Frontend:** `cd frontend && npm run build` — succeeds.
- [ ] **Manual smoke (after `docker compose up -d --build backend frontend`):** stop an instance, then open `/i/{subdomain}/` → lands on My Instances with a "stopped" toast. Let an instance idle-timeout, confirm its route is removed (no 502) and the URL redirects.

## Notes / Risks

- Cloudflare passes origin 5xx bodies through, so the `errors`-middleware page renders; the reconciler is the primary mechanism keeping routes fresh.
- `write_routes` no-ops on `PermissionError` (dev/test where `TRAEFIK_DYNAMIC_DIR` isn't writable) — tests assert on `build_routes_config` (pure) instead.
- The `instances_fallback` router (priority 10) sits below per-instance routers (50) and above `frontend` (1), so it only catches `/i/` paths with no live instance.
