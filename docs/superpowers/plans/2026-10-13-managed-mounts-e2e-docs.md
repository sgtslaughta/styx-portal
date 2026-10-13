# Managed Mounts (SP1.5) — E2E, Docs and Live Check Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove SP1.5 end-to-end against real apps (Sonarr, Jellyfin), document it, then verify on the user's production Jellyfin with their go.

**Architecture:** Extend the isolated `styx-e2e` compose project (127.0.0.1:18080 only, docker-shim guard) with real app containers and two tiny nginx test apps; new Playwright spec `mounts.spec.ts`. Runs after the backend and frontend plans are complete.

**Tech Stack:** Docker Compose, Playwright `@playwright/test` 1.63.0, `linuxserver/sonarr`, `jellyfin/jellyfin`, `nginx:alpine`, `traefik/whoami`.

**Spec:** `docs/superpowers/specs/2026-10-13-managed-mounts-design.md` · Plans: `2026-10-13-managed-mounts-backend.md`, `2026-10-13-managed-mounts-frontend.md`.

Run: `e2e/run.sh` (all) or `e2e/run.sh -g mounts`; `KEEP=1` keeps the stack.

## Global Constraints

- Never touch the live stack: the shim only allows writes to containers labelled `com.docker.compose.project=styx-e2e`.
- Pin images by tag: `lscr.io/linuxserver/sonarr:4.0.15`, `jellyfin/jellyfin:10.10.7`, `nginx:1.27-alpine`, `traefik/whoami:v1.10.3` (bump only if the tag is gone; record the change).
- Screenshots: 1440×900 and 390×844, light and dark, into `e2e/screenshots/` (gitignored).
- Live production checks happen **only after the user says go**, one step at a time.

## Review Focus

1. Jellyfin first start is slow (DB init) → test waits on `/health` up to 120 s before planning, so "can't find settings file" never flakes. (Task 2)
2. Sonarr writes its config.xml on first boot only → wait for the file before apply. (Task 2)
3. Existing SP1 tests that assumed identity headers by default → updated to opt in (`pass_identity`). (Task 1)
4. Focus app registers a service worker → after switching focus apps, the old SW no longer answers `/`. (Task 3)
5. Phone viewport: dock opens as bottom sheet and every action is reachable without scrolling the page behind. (Task 3)

---

### Task 1: E2E stack — shim writes, test apps, presets, SP1 test updates

**Files:**
- Modify: `e2e/docker-shim/shim.py`, `e2e/compose.yml`, `e2e/tests/services.spec.ts`
- Create: `e2e/apps/focusapp/{index.html,sw.js,nginx.conf}`, `e2e/apps/frameblock/nginx.conf`, `e2e/apps/brokenapp/config.xml`, `e2e/presets/brokenapp.json`

- [ ] **Step 1: Shim** — in `check()`, before `if method != "POST":` add:
```python
        m = re.fullmatch(r"/containers/([^/]+)/(archive|restart)", path)
        if m and ((method == "PUT" and m.group(2) == "archive") or (method == "POST" and m.group(2) == "restart")):
            info = inspect(urllib.parse.unquote(m.group(1)))
            if not info or info["Config"]["Labels"].get("com.docker.compose.project") != PROJECT:
                return 403, "e2e shim: container outside the e2e project"
            return target, body
```
and update the module docstring's write list ("…plus PUT archive / POST restart on e2e-project containers"). Confirm the proxy loop forwards a PUT body (the `if body or method == "POST"` branch) — if it only reads bodies for POST, change it to `method in ("POST", "PUT")`.
- [ ] **Step 2: Compose services** (all `labels: {styx-e2e.discoverable: "true"}`, `networks: [apps]`):
```yaml
  sonarr:
    image: lscr.io/linuxserver/sonarr:4.0.15
    environment: {PUID: "1000", PGID: "1000", TZ: Etc/UTC}
    tmpfs: ["/config:uid=1000,gid=1000"]
  jellyfin:
    image: jellyfin/jellyfin:10.10.7
    tmpfs: ["/config", "/cache"]
  focusapp:          # root-only app with a service worker
    image: nginx:1.27-alpine
    volumes: ["./apps/focusapp:/usr/share/nginx/html:ro", "./apps/focusapp/nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
  frameblock:        # sends frame-ancestors 'none'
    image: nginx:1.27-alpine
    volumes: ["./apps/frameblock/nginx.conf:/etc/nginx/conf.d/default.conf:ro"]
  brokenapp:         # config.xml exists, but /brokenapp/ping never answers → rollback
    image: nginx:1.27-alpine
    volumes: ["./apps/brokenapp/config.xml:/config/config.xml"]
```
Backend gets `- ./presets/brokenapp.json:/app/templates/services/brokenapp.json:ro` (file-level bind inside the ro dir mount).
`apps/focusapp/index.html`: `<!doctype html><title>Focus app</title><h1>Focus app root</h1><script>navigator.serviceWorker.register("/sw.js")</script>`; `sw.js`: `self.addEventListener("fetch", e => { if (new URL(e.request.url).pathname === "/sw-probe") e.respondWith(new Response("from-focusapp-sw")); });`; `nginx.conf`: `server { listen 80; root /usr/share/nginx/html; location / { try_files $uri /index.html; } }`.
`apps/frameblock/nginx.conf`: `server { listen 80; location / { add_header Content-Security-Policy "frame-ancestors 'none'" always; return 200 "frameblock"; } }`.
`apps/brokenapp/config.xml`: `<Config><UrlBase></UrlBase></Config>`.
`presets/brokenapp.json`: `{"id":"brokenapp","name":"Broken app","icon":"🧪","default_port":80,"mount_mode":"path","auth_mode":"sso","bypass_rules":[],"health_path":"/","verify_tls":true,"base_url_hint":null,"warnings":[],"subpath":{"methods":[{"type":"config_file","paths":["/config/config.xml"],"format":"xml","key":"/Config/UrlBase"}],"restart":true,"verify_path":"/{slug}/ping"}}`.
- [ ] **Step 3: SP1 spec updates** in `services.spec.ts`: test **c** creates/updates the whoami service with `pass_identity: true` before asserting identity headers, and adds an assertion that a second service without it gets no `X-Styx-User`; test **h** opens the cookie-root service via `page.goto("/_styx/open/<slug>")` instead of the `enter` API, and expects to land on `/_styx/app/<slug>/`.
- [ ] **Step 4:** `e2e/run.sh -g "services"` → all SP1 tests green.
- [ ] **Step 5: Commit** `test(e2e): real app containers, shim archive/restart for e2e project, SP1 tests opt into identity`

---

### Task 2: E2E — managed paths (Sonarr, Jellyfin + native client, rollback)

**Files:**
- Create: `e2e/tests/mounts.spec.ts`; Modify: `e2e/tests/helpers.ts` (add `waitHttp`, `jellyfinSetup`)

- [ ] **Step 1: Helpers**
```ts
export async function waitHttp(req: APIRequestContext, url: string, ok = (s: number) => s < 400, timeout = 120_000) {
  await expect.poll(async () => (await req.get(url, { failOnStatusCode: false, maxRedirects: 0 }).catch(() => null))?.status() ?? 0,
    { timeout, intervals: [2000] }).toSatisfy(ok);
}
const JF_AUTH = 'MediaBrowser Client="e2e", Device="e2e", DeviceId="e2e-1", Version="1.0"';
/** Completes Jellyfin's startup wizard through Styx (needs Allow native apps on: every call carries
 *  `Authorization: MediaBrowser …`, so it bypasses Styx login). Returns an access token. */
export async function jellyfinToken(req: APIRequestContext, base: string): Promise<string> {
  await req.post(`${base}/Startup/Configuration`, { headers: { Authorization: JF_AUTH }, data: { UICulture: "en-US", MetadataCountryCode: "US", PreferredMetadataLanguage: "en" } });
  await req.get(`${base}/Startup/User`, { headers: { Authorization: JF_AUTH } });
  await req.post(`${base}/Startup/User`, { headers: { Authorization: JF_AUTH }, data: { Name: "e2e", Password: "e2e-Jelly-Pass-42" } });
  await req.post(`${base}/Startup/Complete`, { headers: { Authorization: JF_AUTH } });
  const r = await req.post(`${base}/Users/AuthenticateByName`, { headers: { Authorization: JF_AUTH }, data: { Username: "e2e", Pw: "e2e-Jelly-Pass-42" } });
  return (await r.json()).AccessToken;
}
```
- [ ] **Step 2: Tests** (`test.describe.serial`, reuse admin login from `services.spec.ts` helpers; `BASE = "http://127.0.0.1:18080"`):
  - **m1 Sonarr (adopted → consent → managed path)**: admin adds Sonarr via "Add from container" with the Sonarr preset; drawer shows "Set base path to /sonarr"; click → consent dialog lists `/config/config.xml`, `/Config/UrlBase`, `(not set)` or empty → `/sonarr`; **Restart Sonarr and apply**; stepper reaches 4× done within 120 s; Obol line "Base path set"; `GET /sonarr/ping` (admin cookies) = 200. Screenshot `mount-consent-*.png`, `mount-done-*.png`.
  - **m2 Jellyfin managed path**: before adding, `waitHttp` can't reach Jellyfin from the host (apps network is internal), so add the service first (Jellyfin preset), then poll the plan endpoint until it returns `method: "config_file"` (network.xml exists after first boot, ≤120 s); apply with consent; verify `GET /jellyfin/health` = 200 with admin cookies.
  - **m3 Jellyfin native client**: with Allow native apps **off**, `request.newContext()` (no cookies) `GET /jellyfin/System/Info` with `Authorization: MediaBrowser Token="x"` → 302/401 (Styx). Turn **on** via the form switch (red callout visible, screenshot); complete the wizard via `jellyfinToken(anonCtx, BASE + "/jellyfin")` (requests carry `Authorization: MediaBrowser …` so they bypass); then `GET /jellyfin/Users/Me` with `Authorization: MediaBrowser Token="<token>"` → 200 JSON with `Name: "e2e"`; `GET /jellyfin/System/Info?api_key=<token>` → 200; `Authorization: Bearer <token>` → Styx 302/401; response bodies never contain `Set-Cookie` for Styx cookies.
  - **m4 Rollback**: add `brokenapp` via "Add from container" (Broken app preset), apply with consent → stepper shows "Check it answers" failed, Ember text "Styx put its settings back", log excerpt present, buttons Try again / Use focus mode instead; read file back via `docker compose -p styx-e2e exec -T brokenapp cat /config/config.xml` (child_process in test) → `<UrlBase></UrlBase>` restored. Screenshot `mount-rollback-*.png`.
  - **m5 Already set**: re-open Sonarr drawer → "Base path is set to /sonarr", no apply button.
- [ ] **Step 3:** `e2e/run.sh -g mounts` green (allow up to 10 min first run for image pulls).
- [ ] **Step 4: Commit** `test(e2e): managed base path for Sonarr and Jellyfin, native client bypass, rollback`

---

### Task 3: E2E — shell, dock, focus, frames, identity, mobile

**Files:** Modify `e2e/tests/mounts.spec.ts`

- [ ] Tests:
  - **s1 Shell + URL sync**: member opens Sonarr tile → URL `/_styx/app/sonarr/`; navigate inside the frame (`frameLocator('iframe').locator('a[href*="/sonarr/calendar"]').click()` or set `frame.goto('/sonarr/calendar')`) → top URL becomes `/_styx/app/sonarr/calendar`; reload keeps the same frame path.
  - **s2 Dock**: edge tab visible; Alt+Shift+S opens dock (role dialog), Sonarr has `aria-current="page"`; Esc closes; drag tab to the left half → after reload it sits on the left. Screenshots dock open light/dark at 1440 and 390 (bottom sheet).
  - **s3 Focus swap + SW cleanup**: add `focusapp` (Focus mode via Advanced) and a second focus service `focusapp2` pointing to the same container; open focusapp from the dock → `/_styx/open/focusapp` → shell; inside frame `fetch('/sw-probe')` eventually returns `from-focusapp-sw`; open `focusapp2` from the dock → after load the SW registered at `/` is gone (`navigator.serviceWorker.getRegistrations()` in the shell → 0 before the new app registers its own). Home tile shows Obol ring + Exit; Exit → Styx home, `styx_svc` cleared.
  - **s4 Cross-site open**: `GET /_styx/open/focusapp` with header `Sec-Fetch-Site: cross-site` → confirm page (form), no `styx_svc` cookie set; submitting the form (with the page's hidden csrf) → shell.
  - **s5 Blocked frame**: add `frameblock` (path mode, url-kind not needed — docker-local, no preset) → open tile → "Frameblock can't run inside Styx" card with "Open Frameblock on its own" link `/frameblock/`.
  - **s6 Identity**: whoami service with Pass identity on → body has `X-Styx-User: alice`, `X-Styx-Email`, `X-Styx-Groups`; spoofed `X-Styx-User: mallory` from the client is replaced; with it off → no `X-Styx-*` lines.
  - **s7 SAMEORIGIN**: any service response carries `X-Frame-Options: SAMEORIGIN`.
- [ ] `e2e/run.sh` (whole suite) green; commit `test(e2e): shell, ferry dock, focus switching, blocked frames and identity headers`

---

### Task 4: Docs

**Files:** `docs/SERVICES.md`, `docs/PRODUCTION.md`, `README.md`, `CLAUDE.md`, `zensical.toml` (only if adding a page)

- [ ] `docs/SERVICES.md` new sections (plain language, sentence-case headings):
  - "How apps are mounted" — table of Path (configured by Styx), Path (set by you), Focus; which presets do what.
  - "Letting Styx configure an app" — what consent shows, backup location `data/mount-backups/<service>/`, rollback, "Try again", "Use focus mode instead", how to restore a backup by hand (`docker cp`).
  - "Focus apps" — one at a time per browser, `/_styx/exit`, cross-site confirm page, service-worker cleanup, stale tabs.
  - "The Styx shell and dock" — Alt+Shift+S, dragging the tab, Pop out, "Open without overlay", blocked-frame message.
  - "Native apps" — Jellyfin header/`api_key` rules, the risk, how to test with the Jellyfin app (`https://<domain>/jellyfin`).
  - "Pass identity" — what headers, examples (Grafana `auth.proxy`, Paperless `REMOTE_USER`).
  - Update `#security-model` with consent/audit, SAMEORIGIN, identity opt-in.
- [ ] `PRODUCTION.md`: backups live in the backend data volume (include in host backups); socket-proxy needs `POST=1` (already set) for archive writes.
- [ ] `README.md`: refresh feature list + two screenshots from `e2e/screenshots/` copied to `docs/assets/` (shell with dock, consent dialog).
- [ ] `docs` build: `zensical build` (or the CI docs command from `.github/workflows/docs.yml`) passes.
- [ ] Commit `docs(services): managed mounts, focus apps, shell and native apps`

---

### Task 5: Branch gate and review

- [ ] Backend `pytest -q` + `ruff check`, frontend `npm test` + `npm run build`, `e2e/run.sh` — all green; record counts.
- [ ] Whole-branch review by a fresh reviewer on the most capable model (security focus: archive writes, consent, `/_styx/open`, bypass, frame headers, shell inner-path validation).
- [ ] Fix findings, re-run gates, push `feat/managed-mounts` to origin and gitlab (no PR merge without the user).
- [ ] Log outcome in open-brain (`log_decision`/`log_issue` as applicable) and update memory `unified-remote-access.md`.

---

### Task 6: Live check on production (user go required for each bullet)

Ask the user before each step; stop on any surprise.
- [ ] Deploy the branch images to the live stack (`docker compose build backend frontend && docker compose up -d backend frontend`) — **ask first**.
- [ ] Add the prod Jellyfin container from discovery with the Jellyfin preset; open the drawer; show the user the consent table; apply only after they confirm in the UI themselves. Note the backup path.
- [ ] Web: open Jellyfin from the home tile → shell, play a video for 1 min, dock swap to another app and back.
- [ ] Turn on Allow native apps (user confirms the red callout); user signs into the Jellyfin phone app with `https://<domain>/jellyfin` over mobile data and plays something.
- [ ] Home Assistant / Immich as focus apps if the user wants them now (same consent rules don't apply — focus needs no config change).
- [ ] Rollback plan if anything misbehaves: restore `network.xml` from the noted backup with `docker cp`, restart Jellyfin, redeploy previous images.
