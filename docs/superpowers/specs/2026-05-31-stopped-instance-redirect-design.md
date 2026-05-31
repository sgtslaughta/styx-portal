# Stopped-Instance Dynamic Redirect — Design Spec

**Date:** 2026-05-31
**Status:** Approved, pending plan

## Problem

Hitting a not-running instance URL (`https://{domain}/i/{subdomain}/`) shows a
Cloudflare/Traefik error instead of something useful. Root cause: idle
auto-stop (`session_monitor`) marks an instance `stopped` but never refreshes
Traefik routes, so the instance's route still points at a now-dead container →
502 → error. Manual stop *does* refresh routes; auto-stop does not.

We want: hitting any not-running instance URL redirects to the main "My
Instances" page with a toast naming the instance. Cover three cases:
cleanly-stopped (no route), dead-origin (route present, container down → 5xx),
and unknown/non-existent subdomains.

## Routing background (current)

- Instances are reached path-based: `Host(\`{domain}\`) && PathPrefix(\`/i/{subdomain}\`)`,
  priority 50, with a `strip-{subdomain}` middleware, written by
  `backend/app/services/route_writer.py:write_routes()`.
- `frontend` router: `Host(\`{domain}\`)`, priority 1 (catches everything else
  on the domain) → nginx SPA (My Instances).
- `api` router: `Host(\`{domain}\`) && PathPrefix(\`/api\`)`, priority 100 → backend.
- Routes for stopped instances are filtered out (only `running`/`idle` are
  written). Traffic enters via `cloudflared` → Traefik `:80`.
- The frontend opens instances via `window.open("/i/{subdomain}/")`
  (`action-bar.tsx`), full page, not an iframe.

## Decision

One redirect HTML page, delivered by two Traefik paths, plus a root-cause route
reconciler.

### 1. Backend redirect page

`GET /api/instance-unavailable` returns a small self-contained HTML page
(`Content-Type: text/html`). Its inline script derives the subdomain from the
browser's current path and redirects to the My Instances page:

```html
<!doctype html>
<meta charset="utf-8">
<title>Instance unavailable</title>
<meta http-equiv="refresh" content="3;url=/">
<script>
  (function () {
    var m = location.pathname.match(/^\/i\/([^\/]+)/);
    var q = m ? "?stopped=" + encodeURIComponent(m[1]) : "";
    location.replace("/" + q);
  })();
</script>
<p>Instance unavailable. Redirecting… <a href="/">My Instances</a></p>
```

The browser keeps the original `/i/{subdomain}/` address (both delivery paths
preserve it), so the page derives the subdomain uniformly. The `<meta refresh>`
and the link are no-JS fallbacks.

### 2. route_writer (Traefik) additions

In `write_routes()` add, always (independent of instance count):

- Catch-all router `instances_fallback`:
  `Host(\`{domain}\`) && PathPrefix(\`/i/\`)`, priority 10, entryPoints `[web]`,
  middlewares `[unavailable-rewrite]`, service `api`. Below running instances
  (50), above frontend (1) — so it only matches `/i/` paths with no live
  instance router.
- Middleware `unavailable-rewrite`:
  `replacePath: { path: "/api/instance-unavailable" }`.
- Middleware `instance-unavailable-errors`:
  `errors: { status: ["500-599"], service: "api", query: "/api/instance-unavailable" }`.
  Add `instance-unavailable-errors` as the FIRST middleware on every per-instance
  router (before `strip-{subdomain}`) so it wraps and catches 5xx from a dead
  container.

These middlewares/routers are emitted on every `write_routes()` call so they
exist whether or not any instance is running.

### 3. Root-cause fix + reconciler

- Extract a shared helper `refresh_routes_from_db(session)` (new function in
  `route_writer.py`) that queries `Instance` rows with status in
  `{running, idle}`, resolves each template's `internal_port`/`internal_protocol`,
  and calls `write_routes(...)`. Replace the duplicated route-building in
  `instances.py:_refresh_routes` and the startup block in `main.py` lifespan
  with calls to it.
- `session_monitor` auto-stop path: the `_session_monitor_loop` in `main.py`
  must call `refresh_routes_from_db(session)` after a pass in which any instance
  transitioned to `stopped`. `SessionMonitor.check_instance` already returns
  `["auto_stopped"]` when it stops one — the loop detects that and refreshes.
- Per-tick crashed-container reconcile: in the loop that already iterates
  running/idle instances, if an instance's `container_id` reports
  `not_found`/`exited` (via `DockerManager.get_container_status`), mark it
  `stopped` and trigger a route refresh. This mirrors the existing startup
  stale-sync and shrinks the dead-origin window.

### 4. Frontend toast

On app load (top-level component, e.g. `App.tsx` or `InstanceWorkspace`), read
`new URLSearchParams(location.search).get("stopped")`. If present:
- Show a toast via `sonner`: `Instance "{sub}" is stopped`.
- `history.replaceState({}, "", location.pathname)` to drop the query param so a
  refresh doesn't re-toast.

## Data flow

```
Stopped / unknown /i/{sub}/:
  → instances_fallback (prio 10) → unavailable-rewrite → backend /api/instance-unavailable
  → HTML/JS reads {sub} → location.replace("/?stopped={sub}") → SPA toast

Dead origin (route present, container down):
  → instance router (prio 50) → 5xx → instance-unavailable-errors
  → backend /api/instance-unavailable → same JS → redirect
```

## Error handling

- No-JS clients: `<meta refresh>` + link send them to `/` (no toast).
- Cloudflare passes origin 5xx response bodies through, so the errors-middleware
  page renders. The reconciler is the primary mechanism that prevents the 5xx in
  the first place; the errors middleware only covers the brief crash-to-reconcile
  window.
- `write_routes()` already no-ops on `PermissionError` for the output dir
  (test/dev) — unchanged.

## Testing

- `route_writer`: generated config always contains `instances_fallback`
  (priority 10, `PathPrefix(/i/)`, middleware `unavailable-rewrite`, service
  `api`), the `unavailable-rewrite` and `instance-unavailable-errors`
  middlewares; each per-instance router lists `instance-unavailable-errors`
  before `strip-{subdomain}`.
- `refresh_routes_from_db(session)`: builds the running/idle list and calls
  `write_routes`; instances.py and main.py use it (no behavior change for
  manual stop).
- Backend endpoint: `GET /api/instance-unavailable` → 200, `text/html`, body
  contains the redirect script and a `/` fallback link.
- Auto-stop refresh: after `SessionMonitor` auto-stops an instance, routes are
  refreshed (test the helper + the loop's stop-detection branch).
- Frontend: build passes; manual smoke for the toast.

## Out of scope

- Subdomain-Host access (`{subdomain}.{domain}`) — the app uses `/i/` paths.
- Auto-starting a stopped instance from the redirect (just redirect + toast).
- Custom branded error pages beyond the minimal redirect page.
