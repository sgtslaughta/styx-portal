# Thumbnails for workstations and proxied services — plan (2026-10-31)

Today only Docker instances get previews (`backend/app/services/screenshot.py`, `frontend/src/components/instances/instance-thumbnail.tsx`).
Instances on k8s are out of scope (they need k8s-native instances first).

## API contract (all tasks rely on this)

| Route | Who | Body / result |
|---|---|---|
| `POST /api/agent/thumbnail` | agent (Bearer agent token, `get_agent_workstation`) | raw `image/jpeg` body, max 512 KiB, must start with `FF D8 FF`. 204. |
| `GET /api/workstations/{id}/thumbnail` | user with access to that workstation (same check as connecting) | `image/jpeg`, 404 when none |
| `GET /api/services/{id}/thumbnail` | user allowed to see that service (same check as listing it) | `image/png`, 404 when none |

Files: `{SCREENSHOT_CACHE_DIR}/ws-{id}.jpg`, `{SCREENSHOT_CACHE_DIR}/svc-{id}.png`. Write atomically (tmp + `os.replace`).
Delete them when the workstation / service is deleted.

## Task A — agent + workstation endpoints (agent 0.9.20)

1. New `agent/seat_thumb.py` (<80 lines). `capture(out: Path) -> bool`: on the seat bus (`gnome-bus.addr`),
   `org.gnome.Mutter.ScreenCast.CreateSession({})` -> `RecordMonitor("", {"cursor-mode": UInt32(0)})` -> wait for
   `PipeWireStreamAdded(node)` -> `Start()`; run `gst-launch-1.0 -q pipewiresrc path=<node> num-buffers=1 ! videoconvert !
   videoscale ! video/x-raw,width=640,height=360 ! jpegenc quality=80 ! filesink location=<tmp>` with Popen, kill it as
   soon as the file is non-empty (pipewiresrc never EOSes), timeout 10 s; always `Stop()` the session.
   Working prototype: `docs/superpowers/plans/2026-10-31-thumbnails-mshot-prototype.py` (copy its approach).
   `upload(cfg, data)`: POST raw bytes, `Content-Type: image/jpeg`, Bearer token (add `api_post_bytes` to `portal_api.py`).
   `on_heartbeat(cfg)`: if >= 60 s since last capture, run capture+upload in a daemon thread (one at a time). Never raises.
2. `agent/styx_agent.py`: call `seat_thumb.on_heartbeat(cfg)` next to `favicon.on_heartbeat(...)`, GNOME seat mode only.
   File is at 500 lines: keep the change to 1-2 lines.
3. Ship `seat_thumb.py`: `agent/enroll.sh` file list + `backend/app/services/workstations.py` ship list. Bump `AGENT_VERSION` to 0.9.20.
4. Backend: upload route in `backend/app/routers/agent.py`, GET route in `backend/app/routers/workstations.py` (or wherever
   the user-facing workstation routes live; reuse its access check). Tests in `backend/tests/` (size cap, magic check,
   access denied for a user without access, 404 when none). Agent unit test: `on_heartbeat` throttles to 60 s (mock capture).

## Task B — proxied service captures (backend)

1. `ScreenshotService.capture_url(key: str, url: str) -> bool` in `screenshot.py`: new context with the same network jail
   (`_origin_allowed` with the target's host/port/scheme, dead proxy bypassing only that host:port), `page.goto`, wait 3 s,
   `page.screenshot` 1280x800, save `svc-{id}.png`. No `#shared`/canvas logic. If `screenshot.py` passes 400 lines, put it in
   `screenshot_url.py`.
2. Loop: every 5 min capture each enabled proxied service's internal target URL (field used by `service_routes.py`/health loop).
   Runs on k8s too (no Docker needed). Separate task in `main.py` lifespan or folded into `_screenshot_capture_loop`.
3. GET route in `backend/app/routers/services.py`. Tests: route access + 404; `capture_url` jail (reuse existing jail tests).

## Task C — frontend

1. Generalize `instance-thumbnail.tsx` into a component taking `src` (URL) instead of `instanceId`; keep instance usage working.
2. Show the thumbnail on workstation cards (`components/instances/workstation-list.tsx`) and service rows/cards where services
   are shown to users (find the user-facing list, e.g. home/workspaces). Icon fallback on 404 like today. Refresh every 60 s.
3. `api/client.ts`: `workstationThumbUrl(id)`, `serviceThumbUrl(id)`. Gate: `npm run build` + `npx vitest run` pass.
