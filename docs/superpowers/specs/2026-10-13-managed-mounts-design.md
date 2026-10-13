# Managed Mounts, Focus Mode and the Styx Shell (SP1.5) — Design

Status: draft for review · Branch: `feat/managed-mounts` (off `feat/service-proxy-core`)
Builds on: `2026-10-12-service-proxy-core-design.md` (SP1). Section numbers below
prefixed "SP1 §" refer to that spec.

## 1. Goal

One host domain, every service working without manual app configuration and
behind Styx login:

- Apps that support a base path are configured **by Styx** (managed path).
- Root-only apps (Home Assistant, Immich) run in **focus mode** (SP1
  `cookie-root`, renamed in the UI), one at a time per browser.
- Every service opens inside the **Styx shell**: a same-origin frame with an
  overlay dock ("the ferry") to swap apps, go home, pop out, or exit.
- Styx gets a visual identity (palette + typeface) applied app-wide, light and
  dark.

Success: a household member taps a tile, lands in Jellyfin/Immich/Sonarr
without ever seeing a base-path error, and can swap apps from the dock on
desktop and phone. An admin adds Sonarr from a preset and Styx sets its URL
base, restarts it, verifies, and rolls back on failure.

### 1.1 Decisions (user, 2026-10-13)

| # | Decision |
|---|----------|
| D1 | Auto-configure apps Styx controls; ask consent for anything else (adopted containers). |
| D2 | Jellyfin → managed path; native apps via token-header bypass (opt-in). |
| D3 | HA + Immich → focus mode; switching one at a time is fine for now. |
| D4 | Mobile native apps remotely, multi-focus, Authentik SSO: later SPs (§13). |
| D5 | Overlay menu to return/swap apps → shell + same-origin frame, no HTML rewriting. |
| D6 | Overlay on **all** proxied services, with Pop out. |
| D7 | Edge tab (draggable, snaps, fades) + Alt+Shift+S hotkey. |
| D8 | New Styx identity app-wide (Water/Mist/Current/Obol/Ember/Reed, Commissioner). |
| D9 | Shared stepper also shows image-pull progress. |
| D10 | Prefer well-regarded libraries; DRY. Use installed `framer-motion`, `@tanstack/react-query`. |
| D11 | E2E includes a real Jellyfin image; live check on the user's prod Jellyfin incl. a native app. |

## 2. Verified facts

- SP1 already provides: `path` mode (priority 60, no strip), `cookie-root` mode
  (priority 40, `HeaderRegexp(Cookie, styx_svc=<slug>)`), `/api` gated by
  `X-Styx-Client: 1` when a cookie-root service exists, `/_styx/exit`
  (backend, priority 90), `sso-with-bypass` + `bypass_rules` per preset,
  identity headers `X-Styx-User`/`X-Styx-Groups`, spoof-strip middleware.
- Frontend: Tailwind v4 + shadcn (zinc), tokens in `src/styles/globals.css`,
  no font set, no stepper primitive. `framer-motion@^12.40`,
  `@tanstack/react-query@^5.75`, `vitest` installed.
- `@fontsource-variable/commissioner` exists on npm (5.3.0).
- Frontend router is `Host(domain)` priority 1, so cookie-root/focus routers
  (40) shadow `/` **and** `/assets/*` while focus is active.
- Image pull progress (`pull_percent`, `pull_detail`) exists in the API but is
  not rendered (`icon-viewport.tsx` shows an emoji).

## 3. Mount modes

| UI name | DB `mount_mode` | Who |
|---------|-----------------|-----|
| Path (managed) | `path` + `mount_managed=true` | Presets with a `subpath` block |
| Path (manual) | `path` + `mount_managed=false` | url-kind or apps Styx can't configure; shows the preset `base_url_hint` |
| Focus | `cookie-root` (unchanged value, no migration) | Root-only apps |

The preset picks the mode. The form shows it read-only ("Path /jellyfin ·
configured by Styx") with **Change** under Advanced (admin override).

### 3.1 Preset `subpath` block

```json
"subpath": {
  "methods": [
    {"type": "config_file",
     "paths": ["/config/config.xml"],
     "format": "xml", "xpath": "/Config/UrlBase"}
  ],
  "restart": true,
  "verify_path": "/{slug}/ping"
}
```

- `config_file`: read/write via Docker archive API (`get_archive` /
  `put_archive`), first existing path wins. Formats: `xml` (xpath to a text
  node, created if missing), `json` (dotted key), `ini` (section.key).
- `env` and `api` method types are reserved and not implemented (YAGNI). Presets
  with only an env method (e.g. audiobookshelf, `ROUTER_BASE_PATH`) stay manual.
- Initial managed presets with `subpath`: sonarr, radarr, lidarr, prowlarr
  (`/config/config.xml` UrlBase), jellyfin
  (`/config/config/network.xml` and `/config/network.xml`, `BaseUrl`). Others
  stay manual.
- New presets: `homeassistant`, `immich` with `"mount_mode": "cookie-root"`.

### 3.2 Apply job

Steps, in order (this is a real sequence; the stepper numbers them):

1. **Plan** — resolve method, read current value, build the change list
   `[{target, key, old, new}]`. No writes.
2. **Back up** — copy each target file to
   `/data/mount-backups/<service_id>/<utc-ts>/` (backend volume). Keep last 5.
3. **Apply** — write new values.
4. **Restart** — `container.restart(timeout=30)`.
5. **Verify** — GET `http://<container>:<port><verify_path>` until 2xx, 90 s
   budget, 2 s interval.
6. On any failure in 3–5: **Roll back** — restore backup, restart, verify the
   *old* path; job ends `rolled_back` with reason + last 20 log lines of the
   container. If rollback also fails: `failed`, backup path shown.

- Table `mount_jobs`: `id, service_id, state(pending|running|done|rolled_back|failed),
  steps JSON [{id,label,state,detail}], changes JSON, log_excerpt, created_at,
  finished_at`. One running job per service (409 otherwise).
- Runs as an asyncio task. On backend startup, jobs left `running` become
  `failed` with "Interrupted — backup kept at <path>".
- Consent: `needs_consent = not container.labels.get("styx.managed") == "true"`.
  Apply for an adopted container returns 409 unless the request carries
  `consent: true`. Consent is logged (audit log, admin id, change list).
- `ponytail:` no manual "revert" endpoint; switching the service to Focus or
  Manual leaves the app's base path as is. Add when someone asks.

## 4. Focus mode

Focus = SP1 cookie-root (SP1 §4.2) plus:

- `GET /_styx/open/<slug>` (backend, priority 90): ACL check, sets
  `styx_svc=<slug>`, then 302 to the shell `/_styx/app/<slug>/`.
  - Requires `Sec-Fetch-Site` in {`same-origin`, `none`}; otherwise (cross-site
    or missing header) renders an unauthenticated confirm page with a same-origin
    link to `/_styx/open/<slug>`, so a cross-site link can't silently swap the
    user's focused app. No POST and no CSRF form: `styx_proxy` is
    `SameSite=Strict`, so the link click is same-origin and carries the cookie.
  - Response carries `Clear-Site-Data: "cache"` (not `"storage"`: app logins
    in localStorage survive).
- The shell unregisters service workers registered at scope `/` before loading
  a focus app (same-origin `navigator.serviceWorker.getRegistrations()`),
  because the previous focus app's SW would otherwise answer for `/`.
- `/_styx/exit?to=<safe path>` (exists) clears the cookie; `to` goes through
  `safe_next`.
- Stale Styx tabs: while focus is active, a plain reload of `/` in another Styx
  tab shows the focus app. Documented; the dock's Home always exits first.

## 5. Auth integration

- Managed path routes reuse SP1 forwardAuth (`svc-auth-<slug>`) and cookie
  stripping. Prefix not stripped.
- Focus routers re-check group access per request (SP1 behavior); a stale or
  forged `styx_svc` only reaches apps the user may use, else the no-access page.
- Navigation requests get 302 to login/switcher; requests with
  `Accept: application/json` or `X-Requested-With` get 401 (no HTML into SPAs).
- **Allow native apps** (per service, default off) = `auth_mode
  sso-with-bypass` with the preset's `bypass_rules`. Rule schema grows one
  optional field: `required_query` (query param name). Jellyfin preset rules:
  headers `Authorization` (value prefix `MediaBrowser`), `X-Emby-Authorization`,
  `X-Emby-Token`, `X-MediaBrowser-Token`; query `api_key` (cast/stream URLs).
  Red risk callout: "Jellyfin's own login is exposed to the internet". Rate
  limit + IP ban still apply.
- **Pass identity** (per service, default off) controls whether
  `X-Styx-User`/`X-Styx-Email`/`X-Styx-Groups` reach the upstream. Client
  copies are always stripped (SP1). Enables Grafana `auth.proxy`, Paperless
  `REMOTE_USER` today; SP2 Authentik plugs in behind the same gate.
- Session expiry: refresh family unchanged; expired `styx_proxy` → login with
  safe `next` → back into the shell at the same inner path.

## 6. The Styx shell

### 6.1 Serving

- Second Vite build: `frontend/vite.shell.config.ts`, entry `shell.html`,
  `base: "/_styx/app/"`, out `dist/shell/`. Shares `src/` (tokens, ui, api
  client). Separate base because `/assets/*` is shadowed during focus.
- Frontend nginx serves `/_styx/app/assets/*` from `dist/shell/assets` and
  every other `/_styx/app/*` with `dist/shell/shell.html`.
- Traefik: `Host(domain) && PathPrefix(/_styx/app)` → frontend, priority 95
  (above backend `/_styx` 90 and all service routers).
- The no-access (403) and unavailable (503) pages move to the shell styling
  (same tokens, inline CSS generated at build time is fine; they stay
  backend-served).

### 6.2 Frame

- URL: `/_styx/app/<slug>/<inner>`. Inner path validated with
  `lib/safe-next.ts` rules (must start with `/`, no `//`, no encoded traversal).
  Frame `src` = path mode `/<slug>/<inner>`, focus mode `/<inner>`.
- `<iframe allow="fullscreen; clipboard-read; clipboard-write; autoplay;
  picture-in-picture; encrypted-media">`, no `sandbox` (same origin; sandbox
  with `allow-same-origin allow-scripts` adds nothing).
- URL sync: on frame `load` and on its `popstate`/`hashchange`, plus wrapping
  the frame's `history.pushState/replaceState` (same-origin), the shell
  `replaceState`s its own URL and copies `document.title`. Reload and deep
  links work.
- Frame headers: service routers get a headers middleware forcing
  `X-Frame-Options: SAMEORIGIN`. App CSP is not rewritten.
- Blocked-frame fallback: after `load`, if `contentDocument` is null or
  `about:blank` at the app URL, the shell shows "This app can't run inside
  Styx" with **Open on its own**. Admin can set "Open without overlay" per
  service (tiles then link to the bare app).
- Security note: the framed app is same-origin with Styx — identical exposure
  to SP1's same-origin acknowledgement (SP1 §10.1); the shell stores nothing
  beyond what the portal origin already holds.

### 6.3 The ferry (overlay dock)

- **Edge tab**: 44×44 hit area (WCAG), framer-motion `drag` with
  `dragConstraints` = viewport and snap to nearest left/right edge on release;
  fades to 35 % after 3 s idle, full on hover/focus/touch. Position saved in
  `localStorage` per device (try/catch, default right-middle).
- **Open**: click/tap the tab or **Alt+Shift+S** (listener on the shell window
  and the frame's `contentWindow`); Esc closes; focus trapped while open.
- **Contents**: app icons + names with health dots (from the existing
  member-tile endpoint, TanStack Query, 30 s), current app ringed in Obol;
  actions **Home** (`/_styx/exit?to=/`), **Pop out** (bare app, new tab),
  **Exit focus** (focus apps only).
- **Motion**: the dock slide + icons settling along a shallow curve is the
  single orchestrated moment. `MotionConfig reducedMotion="user"`;
  `LazyMotion` + `domAnimation`.
- Swapping to a focus app navigates the top window to `/_styx/open/<slug>`;
  swapping to a path app only changes the frame `src` (no reload of the shell).

## 7. Identity

| Token | Hex | Use |
|-------|-----|-----|
| Water | `#0F1C22` | dark background; light-mode foreground |
| Mist | `#EDF1EF` | light background; dark-mode foreground |
| Current | `#2A767C` | primary (replaces shadcn blue); 4.63:1 on Mist |
| Obol | `#B88A3E` | active/focused/verified only (rings, fills); text variant `#86601F` in light mode |
| Ember | `#B8432A` | destructive, rollback; 4.76:1 on Mist |
| Reed | `#4F9A6C` | healthy, done |

- Surfaces/borders/muted derive from Water/Mist mixes; all pairs used for text
  ≥ 4.5:1 (checked in a unit test over the token table).
- Type: `@fontsource-variable/commissioner` (bundled, no external calls),
  one family. Body 15 px / 1.55; scale ×1.25; headings weight 600, tight
  tracking, flair axis on headings if the package ships it (else none).
  Sentence case, no all-caps labels.
- Dock glass: dark = Water at 72 % + backdrop blur; light = Mist at 80 % with
  a Water 12 % border, so it reads on bright apps.
- Rejected: cream+terracotta, black+neon.

## 8. Admin and home UI

- **Service form** (`components/system/service-form.tsx`, split into parts to
  stay < 500 lines): Mount line (read-only + Change in Advanced); Access gains
  **Allow native apps** (red callout) and **Pass identity**; Advanced gains
  **Open without overlay**.
- **Consent modal** (adopted containers): title "Change Sonarr's settings?",
  change table (file, key, old → new), backup location, "Sonarr restarts
  (about 30 s)". Buttons: **Restart Sonarr and apply** / Cancel.
- **Stepper** `components/ui/stepper.tsx`: `steps: {id, label, state:
  pending|active|done|failed|skipped, detail?, percent?}[]`. Used by the mount
  job (in the drawer, polling 1 s while running) and by image pulls
  (`icon-viewport` / instance card render `pull_percent` + `pull_detail`).
  Rollback view: reason, log excerpt (collapsible), **Try again**, **Use focus
  mode instead**. Row chip shows the last job result after the drawer closes.
- **Home tiles**: open `/_styx/app/<slug>/` (or the bare app if "Open without
  overlay"). Focus tiles say "Opens on its own"; the active focus tile gets an
  Obol ring and **Exit**.
- Mobile: shell, dock and tiles fully responsive at 360–430 px; admin form
  usable (single column).

## 9. API surface (new)

| Method | Path | Notes |
|--------|------|-------|
| POST | `/api/services/{id}/mount/plan` | admin; change list + method + `needs_consent` |
| POST | `/api/services/{id}/mount/apply` | admin; body `{consent: bool}`; 202 `{job_id}`; 409 running/no consent |
| GET | `/api/services/{id}/mount/jobs/latest` | admin; job with steps |
| GET | `/api/services/focus` | user; `{slug}` of the active focus app (cookie is HttpOnly) |
| GET | `/_styx/open/{slug}` | user; §4 |

Schema additions on `proxied_services`: `mount_managed bool`, `pass_identity
bool`, `frame_ok bool default true` (Open without overlay = false).

## 10. Security summary

- Writes into containers only via archive API on the configured container, only
  to preset-declared paths; adopted containers need explicit, audited consent.
- Backups before every write; auto-rollback.
- `/_styx/open` cross-site or header-less requests get an unauthenticated
  confirm page with a same-origin link (no state change until that click).
- Native-app bypass off by default, preset-declared headers only, red callout.
- Identity headers stripped from clients always; forwarded only when opted in.
- Frame: `X-Frame-Options: SAMEORIGIN` forced on service routes (prevents
  cross-origin clickjacking); no app CSP rewriting.
- Shell inner path validated by `safe-next` rules (no open redirect).

## 11. Testing

**Backend unit** (pytest, mocked Docker): plan/backup/apply/restart/verify/
rollback state machine incl. rollback failure and startup-interrupt; xml/json/
ini editors; consent 409; focus
router generation; `/_styx/open` Sec-Fetch-Site matrix + confirm link page (cross-site and missing header); bypass
rules incl. `required_query` and spoof cases; identity header forwarding on/off;
frame-header middleware labels.

**Frontend unit** (vitest): stepper states + percent; consent change table;
mount line + override; dock open/close, hotkey, Esc, focus trap, reduced
motion; shell URL sync + inner-path validation; blocked-frame fallback; token
contrast table.

**E2E** (`e2e/`, Playwright, compose project `styx-e2e`):
- Real `linuxserver/sonarr` (adopted → consent → managed path, verify).
- Real `jellyfin/jellyfin` (config_file BaseUrl; startup wizard via API;
  native client: `Authorization: MediaBrowser … Token=` reaches Jellyfin
  without Styx cookies when Allow native apps is on, 302/401 when off).
- Root-only nginx test app (focus mode, swap, exit, SW cleanup).
- `traefik/whoami` (identity headers on/off, spoof stripped).
- Test app sending `frame-ancestors 'none'` (blocked-frame fallback).
- Broken preset (verify fails → rollback shown).
- Dock drag/snap/hotkey; screenshots light + dark, 1440 px and 390 px.

**Live (only with user go)**: prod Jellyfin via consent dialog (backup kept),
web playback in the shell, and the user's Jellyfin phone app against
`https://<domain>/jellyfin`.

## 12. Rollout

Branch `feat/managed-mounts` stays isolated until e2e is green and the user
approves; merge order SP1 → SP1.5 (user decides). Minor version bump
(feat). Docs: `docs/SERVICES.md` (modes, consent, shell, dock, native apps),
README screenshots, CLAUDE.md structure.

## 13. Out of scope

SP2 Authentik SSO; native-client endpoint/subdomains for remote mobile apps
beyond token bypass; several focus apps at once (streamed browser kiosk);
HTML rewriting/script injection; `api` subpath method; manual revert of an
app's base path.
