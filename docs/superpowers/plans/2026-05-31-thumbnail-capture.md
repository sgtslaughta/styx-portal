# Instance Thumbnail Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture live thumbnails for every instance via a headless browser, so KasmVNC/LinuxServer.io apps (no `/screenshot` endpoint) get thumbnails just like Selkies.

**Architecture:** Replace the per-image capture logic in `ScreenshotService` with a single Playwright/Chromium path that navigates to the container's internal IP and screenshots the rendered desktop. A background loop refreshes a cached PNG per running instance every 30s. The frontend `IconViewport` displays the PNG with an icon fallback.

**Tech Stack:** Python 3.12, FastAPI, Playwright (async), Chromium, React/TypeScript, Tailwind.

---

## File Structure

- `backend/pyproject.toml` — add `playwright` dependency.
- `backend/Dockerfile` — install Chromium browser.
- `backend/app/config.py` — add `SCREENSHOT_INTERVAL_SECONDS`.
- `backend/app/services/screenshot.py` — rewrite `capture` (async, Playwright); drop httpx + grim.
- `backend/app/main.py` — add `_screenshot_capture_loop`, wire into lifespan.
- `backend/tests/test_screenshots.py` — rewrite for the Playwright path.
- `frontend/src/api/client.ts` — add `screenshotUrl`.
- `frontend/src/components/instances/icon-viewport.tsx` — display screenshot with tick refresh + icon fallback.

---

## Task 1: Dependencies, config, Docker

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/Dockerfile`
- Test: `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_config.py`:

```python
from app.config import Settings


def test_screenshot_interval_default():
    s = Settings()
    assert s.SCREENSHOT_INTERVAL_SECONDS == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'SCREENSHOT_INTERVAL_SECONDS'`

- [ ] **Step 3: Add the setting**

In `backend/app/config.py`, add after the `SCREENSHOT_CACHE_DIR` line:

```python
    SCREENSHOT_INTERVAL_SECONDS: int = 30
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Add the dependency**

In `backend/pyproject.toml`, add to the `dependencies` list (after `"pyyaml>=6.0",`):

```toml
    "playwright>=1.49.0",
```

Then install locally:

Run: `cd backend && .venv/bin/pip install playwright && .venv/bin/playwright install chromium`
Expected: Chromium downloads successfully.

- [ ] **Step 6: Update the Dockerfile**

In `backend/Dockerfile`, replace the single install line:

```dockerfile
RUN pip install --no-cache-dir .
```

with:

```dockerfile
RUN pip install --no-cache-dir .
RUN playwright install --with-deps chromium
```

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/Dockerfile backend/tests/test_config.py
git commit -m "feat(screenshots): add playwright dep, capture interval config, chromium in docker"
```

---

## Task 2: Rewrite ScreenshotService with Playwright

**Files:**
- Modify: `backend/app/services/screenshot.py` (full rewrite)
- Test: `backend/tests/test_screenshots.py` (full rewrite)

The service keeps a lazily-launched, reused Chromium browser. `__init__` and `get_path` stay synchronous; `capture` becomes async. The httpx `/screenshot` path and grim fallback are removed.

- [ ] **Step 1: Write the failing tests**

Replace the entire contents of `backend/tests/test_screenshots.py` with:

```python
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.screenshot import ScreenshotService


def _make_service(tmpdir, browser=None):
    svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
    if browser is not None:
        svc._browser = browser
    return svc


def test_screenshot_cache_dir_created():
    with tempfile.TemporaryDirectory() as tmpdir:
        ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert Path(tmpdir).is_dir()


def test_get_screenshot_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = ScreenshotService(cache_dir=tmpdir, docker_manager=MagicMock())
        assert svc.get_path("nonexistent") is None
        cached = Path(tmpdir) / "inst-1.png"
        cached.write_bytes(b"\x89PNG data")
        assert svc.get_path("inst-1") == cached


@pytest.mark.asyncio
async def test_capture_writes_png(monkeypatch):
    png_bytes = b"\x89PNG" + b"x" * 200

    page = AsyncMock()
    page.screenshot.return_value = png_bytes
    context = AsyncMock()
    context.new_page.return_value = page
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")

        result = await svc.capture("instance-123", "container-abc", 3001)

        assert result is True
        page.goto.assert_awaited_once()
        url = page.goto.call_args.args[0]
        assert url == "https://172.18.0.5:3001/"
        cached = Path(tmpdir) / "instance-123.png"
        assert cached.read_bytes() == png_bytes


@pytest.mark.asyncio
async def test_capture_no_ip_returns_false(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: None)
        result = await svc.capture("inst-1", "cont-1", 3001)
        assert result is False


@pytest.mark.asyncio
async def test_capture_keeps_previous_on_failure(monkeypatch):
    context = AsyncMock()
    context.new_page.side_effect = Exception("render boom")
    browser = AsyncMock()
    browser.new_context.return_value = context

    with tempfile.TemporaryDirectory() as tmpdir:
        svc = _make_service(tmpdir, browser=browser)
        monkeypatch.setattr(svc, "_ensure_browser", AsyncMock())
        monkeypatch.setattr(svc, "_resolve_ip", lambda cid: "172.18.0.5")
        stale = Path(tmpdir) / "inst-1.png"
        stale.write_bytes(b"OLD")

        result = await svc.capture("inst-1", "cont-1", 3001)

        assert result is False
        assert stale.read_bytes() == b"OLD"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/bin/python -m pytest tests/test_screenshots.py -v`
Expected: FAIL — `_resolve_ip` / `_ensure_browser` not found, or `capture` not awaitable.

- [ ] **Step 3: Rewrite the service**

Replace the entire contents of `backend/app/services/screenshot.py` with:

```python
import asyncio
import logging
from pathlib import Path

from playwright.async_api import async_playwright

from app.services.docker_manager import DockerManager

logger = logging.getLogger("selkies-hub")

_VIEWPORT = {"width": 1280, "height": 720}
_NAV_TIMEOUT_MS = 10000
_RENDER_WAIT_MS = 3000
_CLICK_WAIT_MS = 500


class ScreenshotService:
    def __init__(self, cache_dir: str, docker_manager: DockerManager):
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._docker = docker_manager
        self._pw = None
        self._browser = None
        self._sem = asyncio.Semaphore(2)

    def _resolve_ip(self, container_id: str) -> str | None:
        container = self._docker._client.containers.get(container_id)
        networks = container.attrs["NetworkSettings"]["Networks"]
        for net in networks.values():
            ip = net.get("IPAddress")
            if ip:
                return ip
        return None

    async def _ensure_browser(self):
        if self._browser is not None and self._browser.is_connected():
            return
        if self._pw is None:
            self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=["--no-sandbox", "--ignore-certificate-errors"],
        )

    async def capture(self, instance_id: str, container_id: str, port: int) -> bool:
        try:
            ip = await asyncio.to_thread(self._resolve_ip, container_id)
        except Exception:
            ip = None
        if not ip:
            return False

        try:
            await self._ensure_browser()
        except Exception:
            logger.debug("screenshot: browser launch failed", exc_info=True)
            return False

        async with self._sem:
            context = await self._browser.new_context(
                ignore_https_errors=True, viewport=_VIEWPORT,
            )
            try:
                page = await context.new_page()
                await page.goto(
                    f"https://{ip}:{port}/",
                    wait_until="networkidle",
                    timeout=_NAV_TIMEOUT_MS,
                )
                await page.wait_for_timeout(_RENDER_WAIT_MS)
                try:
                    await page.mouse.click(_VIEWPORT["width"] // 2, _VIEWPORT["height"] // 2)
                    await page.wait_for_timeout(_CLICK_WAIT_MS)
                except Exception:
                    pass
                png = await page.screenshot(type="png")
                (self._cache_dir / f"{instance_id}.png").write_bytes(png)
                return True
            except Exception:
                logger.debug("screenshot: capture failed for %s", instance_id, exc_info=True)
                return False
            finally:
                await context.close()

    async def close(self):
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None

    def get_path(self, instance_id: str) -> Path | None:
        path = self._cache_dir / f"{instance_id}.png"
        if path.exists():
            return path
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/bin/python -m pytest tests/test_screenshots.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: All pass, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/screenshot.py backend/tests/test_screenshots.py
git commit -m "feat(screenshots): playwright universal capture, drop httpx+grim paths"
```

---

## Task 3: Background capture loop

**Files:**
- Modify: `backend/app/main.py:99-103` (lifespan task wiring) and add a new loop function
- Test: `backend/tests/test_capture_loop.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_capture_loop.py`:

```python
from unittest.mock import AsyncMock

import pytest

from app.main import _capture_running_instances


@pytest.mark.asyncio
async def test_captures_only_running_instances():
    svc = AsyncMock()

    class Inst:
        def __init__(self, iid, status, cid, port=3001):
            self.id = iid
            self.status = status
            self.container_id = cid
            self.port = port

    instances = [
        Inst("a", "running", "c-a"),
        Inst("b", "idle", "c-b"),
        Inst("c", "stopped", "c-c"),
        Inst("d", "running", None),
    ]

    await _capture_running_instances(svc, instances)

    captured = {call.args[0] for call in svc.capture.await_args_list}
    assert captured == {"a", "b"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_capture_loop.py -v`
Expected: FAIL with `ImportError: cannot import name '_capture_running_instances'`

- [ ] **Step 3: Add the helper and loop**

In `backend/app/main.py`, add after `_metrics_collection_loop` (after line 144):

```python
async def _capture_running_instances(screenshots, instances):
    for inst in instances:
        if inst.status not in ("running", "idle") or not inst.container_id:
            continue
        try:
            await screenshots.capture(inst.id, inst.container_id, inst.port)
        except Exception:
            pass


async def _screenshot_capture_loop():
    from app.services.screenshot import ScreenshotService
    from app.models import ServiceTemplate

    docker = DockerManager(network_name=_settings.DOCKER_NETWORK)
    screenshots = ScreenshotService(
        cache_dir=_settings.SCREENSHOT_CACHE_DIR, docker_manager=docker,
    )
    try:
        while True:
            await asyncio.sleep(_settings.SCREENSHOT_INTERVAL_SECONDS)
            try:
                async with async_session() as session:
                    result = await session.exec(
                        select(Instance).where(Instance.status.in_(["running", "idle"]))
                    )
                    rows = result.all()
                    targets = []
                    for inst in rows:
                        tmpl = await session.get(ServiceTemplate, inst.template_id)
                        inst.port = tmpl.internal_port if tmpl else 3001
                        targets.append(inst)
                await _capture_running_instances(screenshots, targets)
            except Exception:
                pass
    finally:
        await screenshots.close()
```

Note: `inst.port` is set as a transient attribute on the SQLModel object purely to pass the template port into the capture helper. It is read inside the same loop iteration and never persisted.

- [ ] **Step 4: Wire the loop into lifespan**

In `backend/app/main.py`, change the lifespan task block (currently lines 99-103):

```python
    task = asyncio.create_task(_session_monitor_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    yield
    task.cancel()
    metrics_task.cancel()
```

to:

```python
    task = asyncio.create_task(_session_monitor_loop())
    metrics_task = asyncio.create_task(_metrics_collection_loop())
    screenshot_task = asyncio.create_task(_screenshot_capture_loop())
    yield
    task.cancel()
    metrics_task.cancel()
    screenshot_task.cancel()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_capture_loop.py -v`
Expected: PASS

- [ ] **Step 6: Run full suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: All pass, no lint errors.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py backend/tests/test_capture_loop.py
git commit -m "feat(screenshots): background loop captures running instances every 30s"
```

---

## Task 4: Frontend thumbnail display

**Files:**
- Modify: `frontend/src/api/client.ts:26` (add `screenshotUrl`)
- Modify: `frontend/src/components/instances/icon-viewport.tsx`

No frontend unit-test harness is configured in this project; verification is via the build. Display logic must degrade gracefully: show the icon until an image loads, fall back to the icon on error.

- [ ] **Step 1: Add the URL builder**

In `frontend/src/api/client.ts`, add inside the `api` object (after `listInstances`, line 27):

```typescript
  screenshotUrl: (id: string) => `${BASE}/instances/${id}/screenshot`,
```

- [ ] **Step 2: Display the screenshot in IconViewport**

Replace the entire contents of `frontend/src/components/instances/icon-viewport.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { statusMeta } from "@/lib/status";
import type { Instance } from "@/lib/types";

interface IconViewportProps {
  instance: Instance;
  icon: string | null;
}

const REFRESH_MS = 30000;

export function IconViewport({ instance, icon }: IconViewportProps) {
  const { dotClass, pulse } = statusMeta(instance.status);

  const isStopped = instance.status === "stopped" || instance.status === "error";
  const isPaused = instance.status === "paused";
  const isLive = instance.status === "running" || instance.status === "idle";

  const [tick, setTick] = useState(0);
  const [shotOk, setShotOk] = useState(false);

  useEffect(() => {
    if (!isLive) {
      setShotOk(false);
      return;
    }
    const t = setInterval(() => setTick((n) => n + 1), REFRESH_MS);
    return () => clearInterval(t);
  }, [isLive]);

  const iconContent = instance.status === "pulling" ? (
    <span className="text-[16rem] leading-none select-none">⏳</span>
  ) : icon?.startsWith("http") ? (
    <img src={icon} alt={instance.name} className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[130%] h-[130%] object-contain" draggable={false} />
  ) : (
    <span className="text-[16rem] leading-none select-none">{icon ?? "🖥️"}</span>
  );

  return (
    <div className="relative aspect-video w-full bg-secondary overflow-hidden flex items-center justify-center">
      {/* Static icon — shown until/unless a screenshot loads */}
      <div
        className={`relative flex items-center justify-center w-full h-full ${isStopped ? "grayscale opacity-20" : isPaused ? "opacity-40 saturate-50" : ""} ${shotOk ? "hidden" : ""}`}
      >
        {iconContent}
      </div>

      {/* Live screenshot thumbnail */}
      {isLive && (
        <img
          key={tick}
          src={`${api.screenshotUrl(instance.id)}?t=${tick}`}
          alt={instance.name}
          className={`absolute inset-0 w-full h-full object-cover ${shotOk ? "" : "opacity-0"}`}
          draggable={false}
          onLoad={() => setShotOk(true)}
          onError={() => setShotOk(false)}
        />
      )}

      {/* Name overlay gradient */}
      <div className="absolute bottom-0 left-0 right-0 px-3 pb-2 pt-8" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.7) 0%, transparent 100%)" }}>
        <h3 className="text-lg font-bold text-white truncate drop-shadow-lg">{instance.name}</h3>
      </div>

      {/* Status dot */}
      <div
        className={`absolute top-2.5 right-2.5 h-3 w-3 rounded-full ${dotClass} ${pulse ? "animate-pulse" : ""}`}
      />
    </div>
  );
}
```

- [ ] **Step 3: Build to verify**

Run: `cd frontend && npm run build`
Expected: Build succeeds, no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/components/instances/icon-viewport.tsx
git commit -m "feat(instances): show live screenshot thumbnail with icon fallback"
```

---

## Final Verification

- [ ] **Backend:** `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/` — all pass.
- [ ] **Frontend:** `cd frontend && npm run build` — succeeds.
- [ ] **Manual smoke (recommended, not yet done in any browser):** launch one Selkies instance and one LinuxServer.io (KasmVNC) instance, wait ~30s, confirm both cards show a live thumbnail and that stopped instances fall back to the icon.

## Notes / Risks

- WebRTC (Selkies) may need the synthetic center-click to start playback; the click is best-effort and wrapped in try/except.
- First capture after launch may 404 on the frontend until the first loop tick writes a PNG — the icon fallback covers this.
- Chromium adds ~400MB to the backend image (accepted tradeoff for one universal path).
- Local dev requires `playwright install chromium` once in `backend/.venv` (Task 1, Step 5).
```
