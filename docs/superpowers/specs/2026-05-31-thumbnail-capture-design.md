# Instance Thumbnail Capture — Design Spec

**Date:** 2026-05-31
**Status:** Approved, pending plan

## Problem

Instance cards show only a static template icon. The existing screenshot
infrastructure (`backend/app/services/screenshot.py`) captures live thumbnails
via two paths:

1. HTTP `GET https://{ip}:{port}/screenshot` — works only for **Selkies**
   images (`baseimage-selkies`).
2. `docker exec grim` — works only for **Wayland** displays.

Registry-launched LinuxServer.io apps (webtop, firefox, etc.) are **KasmVNC**
based: no `/screenshot` endpoint, X11 not Wayland. Both existing paths fail, so
those instances can never produce a thumbnail. We need one capture mechanism
that works for every web-accessible desktop, current and future.

## Decision

Replace the per-image capture logic with a single **headless-browser** capture
path (Playwright + Chromium). The browser renders whatever the desktop serves
(Selkies WebRTC `<video>` or KasmVNC `<canvas>`) and screenshots the viewport.
This eliminates per-image branching — the root cause of prior
Selkies-vs-KasmVNC bugs.

Periodic snapshots (not live preview): a background loop refreshes a cached PNG
per running instance every ~30s. Frontend displays the PNG with an icon
fallback.

### Auth bypass (confirmed feasible)

authentik auth lives at the **Traefik layer**, not the container. Capture hits
the container IP directly on the internal Docker network (same pattern the
current `screenshot.py` already uses), so no auth challenge. Self-signed TLS is
ignored (`ignore_https_errors`).

## Components

### 1. Capture engine — `ScreenshotService` (rewrite `capture`)

- Shared headless Chromium launched once at app startup (FastAPI lifespan),
  reused across captures. Relaunch on crash.
- Per capture:
  1. Resolve container IP from Docker `NetworkSettings` (existing logic).
  2. New page → `goto("https://{ip}:{internal_port}/", ignore_https_errors=True)`.
  3. Wait for render: `networkidle` + fixed ~3s delay. Issue a synthetic click
     (center of viewport) to kick WebRTC playback if needed.
  4. `page.screenshot()` → write `{cache_dir}/{instance_id}.png`.
  5. Close page.
- Per-page navigation/render timeout ~10s. On any failure: return `False`,
  leave the previous cached PNG intact (no delete).
- Concurrency bounded by an `asyncio.Semaphore` so the loop never opens many
  pages at once.
- **Removed:** the httpx `/screenshot` path and the `grim` docker-exec fallback.
- **Unchanged:** `get_path(instance_id)` and the
  `GET /api/instances/{id}/screenshot` endpoint.

The service becomes async (Playwright async API). Browser lifecycle handles
(`playwright`, `browser`) are owned by the service and started/stopped in the
app lifespan.

### 2. Background capture loop

- Runs in the app lifespan alongside the session monitor.
- Every ~30s: query instances with status in `{running, idle}`, call
  `capture()` for each (semaphore-limited). Failures are logged at debug and
  ignored.
- Interval configurable via settings (`SCREENSHOT_INTERVAL_SECONDS`, default 30).

### 3. Frontend display — `IconViewport`

- When a screenshot is available, render
  `<img src="{screenshotUrl(id)}?t={tick}">` as the viewport background; the
  template icon becomes the **fallback** shown on `404`/`onError`.
- `tick` is a timestamp refreshed on a ~30s interval so the thumbnail updates
  live without a full reload. Cache-busting only.
- Status dot and name-gradient overlays stay on top of the image.
- Applies to card views that use `IconViewport` (`instance-card`,
  `instance-card-sm`). Compact row view unchanged.

### 4. Configuration

- `SCREENSHOT_CACHE_DIR` — existing, unchanged.
- `SCREENSHOT_INTERVAL_SECONDS` — new, default `30`.

### 5. Dependencies / Docker

- Add `playwright` to `backend/pyproject.toml`.
- Backend Dockerfile: `playwright install --with-deps chromium` (image grows
  ~400MB — accepted tradeoff for one universal path).

## Data flow

```
background loop (30s)
  → ScreenshotService.capture(instance)        [Playwright → container IP:port]
    → write {cache_dir}/{instance_id}.png
GET /api/instances/{id}/screenshot              [serves cached PNG or 404]
  → frontend <img ?t=tick>                      [icon fallback on 404/error]
```

## Error handling

- Capture failure (timeout, no IP, render error): return `False`, keep prior
  PNG, log at debug. Never throws into the loop.
- Browser crash: service detects closed browser, relaunches on next capture.
- No PNG yet: endpoint returns 404 → frontend shows icon fallback.
- TLS errors ignored (self-signed container certs).

## Testing

- Unit: mock Playwright `browser`/`page`; assert `goto` called with correct
  `https://{ip}:{port}/` URL, `screenshot` invoked, bytes written to cache.
- Failure cases: no container IP, navigation timeout → `capture` returns `False`
  and does not delete existing cache.
- Loop: mock `ScreenshotService`; assert only `{running, idle}` instances are
  captured, semaphore bounds respected.
- Existing `get_path` and endpoint tests remain.

## Out of scope

- Live (real-time) preview / embedded sessions.
- On-demand (hover-triggered) capture.
- Thumbnails for the template registry browser (separate hover-iframe feature,
  unchanged).
```
