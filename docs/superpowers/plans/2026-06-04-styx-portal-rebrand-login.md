# Styx Portal Rebrand + Login Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the product from "Selkies Hub" to "Styx Portal" across every surface (user-facing + infra) and replace the login page with an animated two-panel, theme-aware design.

**Architecture:** Pure string/identifier rename for the rebrand (fresh DB + network authorized, so no migration code). Login becomes a two-panel split: a hard-coded always-dark animated "river" brand panel (`LoginBrandPanel`) plus a theme-aware form panel using existing Tailwind semantic tokens. All current auth/SSO logic is preserved verbatim.

**Tech Stack:** FastAPI + SQLModel (backend), React 19 + react-router + Tailwind v4 (frontend), pytest, Vite.

**Keep as-is (upstream Selkies streaming tech, NOT our brand):** `frontend/src/lib/selkies-defaults.ts`, `launch-config-fields.tsx`, `launch-selkies-settings.tsx`, the `TITLE=Selkies` env default, `use-launch-config.ts` comment, and `linuxserver/baseimage-selkies` / `selkies-desktop` image names.

---

## Task 1: Backend config rename

**Files:**
- Modify: `backend/app/config.py:6,8`
- Test: `backend/tests/test_config.py:7,9`

- [ ] **Step 1: Update the failing test assertions**

In `backend/tests/test_config.py`, change the two assertions:

```python
    assert settings.DATABASE_URL == "sqlite+aiosqlite:///./data/styx-portal.db"
    # ...
    assert settings.DOCKER_NETWORK == "styx-portal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — asserts still see old `selkies-hub` defaults.

- [ ] **Step 3: Update config defaults**

In `backend/app/config.py`:

```python
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/styx-portal.db"
    # line 8:
    DOCKER_NETWORK: str = "styx-portal"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "refactor(config): rename DB + docker network to styx-portal"
```

---

## Task 2: Backend logger + FastAPI title rename

**Files:**
- Modify: `backend/app/main.py:28,216`
- Modify: `backend/app/routers/oauth.py:17`
- Modify: `backend/app/services/screenshot.py:9`

No test — these are logger names + an HTTP `title` string with no assertions. Verify via app import.

- [ ] **Step 1: Rename logger + FastAPI title in main.py**

`backend/app/main.py` line 28:

```python
logger = logging.getLogger("styx-portal")
```

line 216:

```python
app = FastAPI(title="Styx Portal", version="0.1.0", lifespan=lifespan)
```

- [ ] **Step 2: Rename loggers in oauth.py + screenshot.py**

`backend/app/routers/oauth.py` line 17 and `backend/app/services/screenshot.py` line 9 — both:

```python
logger = logging.getLogger("styx-portal")
```

- [ ] **Step 3: Verify app imports cleanly**

Run: `cd backend && .venv/bin/python -c "from app.main import app; print(app.title)"`
Expected: prints `Styx Portal`

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py backend/app/routers/oauth.py backend/app/services/screenshot.py
git commit -m "refactor(backend): rename logger + app title to Styx Portal"
```

---

## Task 3: DockerManager default network rename

**Files:**
- Modify: `backend/app/services/docker_manager.py:35`
- Test: `backend/tests/test_docker_manager.py:12`

- [ ] **Step 1: Update the fixture + add a default-network test**

The fixture at `backend/tests/test_docker_manager.py:12` passes the network explicitly — update that stale string:

```python
        manager = DockerManager(network_name="styx-portal")
```

Then add a test that pins the DEFAULT (this is what actually drives the impl change). Place it near the top of the test module, after the imports/fixture:

```python
def test_default_network_name():
    from unittest.mock import patch
    with patch("app.services.docker_manager.docker.DockerClient"):
        manager = DockerManager()
        assert manager._network_name == "styx-portal"
```

(If `app.services.docker_manager` already imports `patch` at module level, drop the inner import and reuse it.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_manager.py::test_default_network_name -v`
Expected: FAIL — default still `selkies-hub`.

- [ ] **Step 3: Update the default**

`backend/app/services/docker_manager.py` line 35:

```python
    def __init__(self, network_name: str = "styx-portal"):
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_docker_manager.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/docker_manager.py backend/tests/test_docker_manager.py
git commit -m "refactor(docker): default network styx-portal"
```

---

## Task 4: Traefik label namespace rename

**Files:**
- Modify: `backend/app/services/traefik_labels.py:15-17`
- Test: `backend/tests/test_traefik_labels.py:17-19`

These are metadata label keys (not `traefik.*` routing rules), safe to rename on fresh deploy.

- [ ] **Step 1: Update the test assertions**

`backend/tests/test_traefik_labels.py` lines 17-19:

```python
    assert labels["styx-portal.managed"] == "true"
    assert labels["styx-portal.instance-id"] == "abc123"
    assert labels["styx-portal.template"] == "dev-desktop"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/bin/python -m pytest tests/test_traefik_labels.py -v`
Expected: FAIL — KeyError, labels dict still uses `selkies-hub.*`.

- [ ] **Step 3: Update the label keys**

`backend/app/services/traefik_labels.py` lines 15-17:

```python
        "styx-portal.managed": "true",
        "styx-portal.instance-id": instance_id,
        "styx-portal.template": template_name,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/bin/python -m pytest tests/test_traefik_labels.py -v`
Expected: PASS

- [ ] **Step 5: Run full backend suite + lint**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
Expected: all pass, ruff clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/traefik_labels.py backend/tests/test_traefik_labels.py
git commit -m "refactor(traefik): rename label namespace to styx-portal"
```

---

## Task 5: Frontend brand strings (non-login)

**Files:**
- Modify: `frontend/index.html:9`
- Modify: `frontend/package.json:2`
- Modify: `frontend/src/components/layout/header.tsx:81`
- Modify: `frontend/src/components/system/metrics-overview.tsx:139`
- Modify: `frontend/src/pages/AcceptInvitePage.tsx:41`
- Modify: `frontend/src/pages/SetupWizard.tsx:40`

(LoginPage is rewritten in Task 8 — leave it for now.)

- [ ] **Step 1: Replace each brand string**

`frontend/index.html` line 9:
```html
    <title>Styx Portal</title>
```

`frontend/package.json` line 2:
```json
  "name": "styx-portal-frontend",
```

`frontend/src/components/layout/header.tsx` line 81:
```tsx
      <span className="text-base font-bold">Styx Portal</span>
```

`frontend/src/components/system/metrics-overview.tsx` line 139 (fallback must match new default network):
```tsx
              { label: "Network", value: hostInfo.network ?? "styx-portal" },
```

`frontend/src/pages/AcceptInvitePage.tsx` line 41:
```tsx
          <CardDescription>Create your user account to join Styx Portal</CardDescription>
```

`frontend/src/pages/SetupWizard.tsx` line 40:
```tsx
          <CardDescription>Set up your Styx Portal administrator account</CardDescription>
```

- [ ] **Step 2: Verify no stray brand refs remain (excluding login + upstream tech)**

Run:
```bash
grep -rn "Selkies Hub\|selkies-hub" frontend/src frontend/index.html frontend/package.json | grep -v "LoginPage"
```
Expected: no output.

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/package.json frontend/src/components/layout/header.tsx frontend/src/components/system/metrics-overview.tsx frontend/src/pages/AcceptInvitePage.tsx frontend/src/pages/SetupWizard.tsx
git commit -m "refactor(frontend): rebrand strings to Styx Portal"
```

---

## Task 6: Add brand-panel CSS to globals

**Files:**
- Modify: `frontend/src/styles/globals.css` (append at end, after line 90)

- [ ] **Step 1: Append the `.styx-brand` block**

Add to the end of `frontend/src/styles/globals.css`:

```css
/* Styx Portal login brand panel — always dark, animated "river current" */
.styx-brand {
  position: relative;
  overflow: hidden;
  background: radial-gradient(140% 120% at 15% 100%, #0a1426 0%, #070a12 45%, #05070d 100%);
  color: #fff;
}
.styx-brand::before,
.styx-brand::after {
  content: "";
  position: absolute;
  inset: -40% -40%;
  pointer-events: none;
  -webkit-mask: radial-gradient(150% 130% at 0% 100%, #000 30%, transparent 72%);
          mask: radial-gradient(150% 130% at 0% 100%, #000 30%, transparent 72%);
}
.styx-brand::before {
  background: repeating-linear-gradient(115deg, transparent 0 22px, rgba(70, 140, 255, 0.09) 22px 23px);
  animation: styx-flow 14s linear infinite;
}
.styx-brand::after {
  background: repeating-linear-gradient(115deg, transparent 0 40px, rgba(40, 90, 200, 0.06) 40px 41px);
  animation: styx-flow 26s linear infinite;
}
@keyframes styx-flow {
  from { transform: translate(0, 0); }
  to   { transform: translate(-23px, -49px); }
}
@media (prefers-reduced-motion: reduce) {
  .styx-brand::before,
  .styx-brand::after { animation: none; }
}
.styx-brand > * { position: relative; z-index: 1; }
```

- [ ] **Step 2: Build to verify CSS compiles**

Run: `cd frontend && npm run build`
Expected: build succeeds (no CSS parse errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/styles/globals.css
git commit -m "feat(login): add styx-brand animated panel styles"
```

---

## Task 7: LoginBrandPanel component

**Files:**
- Create: `frontend/src/components/auth/LoginBrandPanel.tsx`

- [ ] **Step 1: Create the component**

`frontend/src/components/auth/LoginBrandPanel.tsx`:

```tsx
import { Waves } from "lucide-react";

/**
 * Always-dark animated brand panel for the login split layout.
 * Visual only — no props, no logic. Theme-independent by design.
 */
export function LoginBrandPanel() {
  return (
    <div className="styx-brand hidden md:flex flex-col justify-between p-10">
      <div className="flex items-center gap-2">
        <Waves className="h-6 w-6 text-sky-400" />
        <span className="text-lg font-extrabold tracking-wider">STYX PORTAL</span>
      </div>
      <div>
        <h2 className="text-3xl font-bold leading-tight">
          Cross over to your
          <br />
          workspaces.
        </h2>
        <p className="mt-3 max-w-xs text-sm text-white/60">
          Secure remote desktops, on demand.
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/auth/LoginBrandPanel.tsx
git commit -m "feat(login): add LoginBrandPanel component"
```

---

## Task 8: Rewrite LoginPage with split layout

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx` (full rewrite)

Preserves all existing logic: `api.login`, `api.oauthProviders`, `api.oauthStartUrl`, the SSO error-code map, `refresh()` + `nav("/")`. Only the markup/layout changes. The backend auth field is `username`; the input is labeled "Email or username" and keeps the `username` state binding.

- [ ] **Step 1: Replace the file contents**

`frontend/src/pages/LoginPage.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoginBrandPanel } from "@/components/auth/LoginBrandPanel";

export function LoginPage() {
  const [username, setU] = useState("");
  const [password, setP] = useState("");
  const [err, setErr] = useState("");
  const [providers, setProviders] = useState<{ name: string; display_label: string }[]>([]);
  const nav = useNavigate();
  const { refresh } = useAuth();

  useEffect(() => {
    api.oauthProviders().then(setProviders).catch(() => {});
  }, []);

  useEffect(() => {
    const ssoError = new URLSearchParams(window.location.search).get("error");
    if (ssoError) {
      const errorMap: Record<string, string> = {
        not_authorized: "This account is not authorized. Ask an admin for an invite.",
        email_unverified: "Your identity provider did not confirm a verified email.",
        account_disabled: "This account is disabled.",
        state_mismatch: "Sign-in session expired. Please try again.",
        bad_state: "Sign-in session expired. Please try again.",
        missing_state: "Sign-in session expired. Please try again.",
        oauth_failed: "Single sign-on failed. Please try again.",
        unknown_provider: "Single sign-on failed. Please try again.",
      };
      setErr(errorMap[ssoError] || "An error occurred during sign-in. Please try again.");
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    try {
      await api.login({ username, password });
      await refresh();
      nav("/");
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  return (
    <div className="grid min-h-screen md:grid-cols-2">
      <LoginBrandPanel />
      <div className="flex items-center justify-center bg-muted px-6 py-12">
        <div className="w-full max-w-sm space-y-6">
          <div className="space-y-1 text-center">
            <h1 className="text-2xl font-bold">Sign in</h1>
            <p className="text-sm text-muted-foreground">Welcome back. Please sign in to continue.</p>
          </div>

          {providers.length > 0 && (
            <div className="space-y-2">
              {providers.map((p) => (
                <a
                  key={p.name}
                  href={api.oauthStartUrl(p.name)}
                  className="flex w-full items-center justify-center rounded-md border border-border bg-background p-2.5 text-sm font-medium hover:bg-accent"
                >
                  Continue with {p.display_label}
                </a>
              ))}
              <div className="flex items-center gap-3 pt-1 text-xs text-muted-foreground">
                <span className="h-px flex-1 bg-border" />
                or
                <span className="h-px flex-1 bg-border" />
              </div>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="username" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Email or username
              </label>
              <Input
                id="username"
                placeholder="you@example.com"
                value={username}
                onChange={(e) => setU(e.target.value)}
                required
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Password
              </label>
              <Input
                id="password"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setP(e.target.value)}
                required
              />
            </div>
            {err && (
              <div className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {err}
              </div>
            )}
            <Button type="submit" className="w-full" size="default">
              Sign in
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify no brand string regressions**

Run: `grep -rn "Selkies Hub\|selkies-hub" frontend/src/pages/LoginPage.tsx`
Expected: no output.

- [ ] **Step 3: Build**

Run: `cd frontend && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Manual verification**

Run dev server (`cd frontend && npm run dev`), open the login page, and confirm:
- Two-panel split on desktop; brand panel hidden, form full-width on mobile (<768px).
- Brand panel is dark with slowly drifting diagonal current lines.
- Toggle OS theme light/dark → form panel flips (bg-muted / fields), brand panel stays dark.
- `prefers-reduced-motion` → lines static.
- SSO buttons appear when providers configured; submit + error path still work.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(login): two-panel animated Styx Portal login"
```

---

## Task 9: README rebrand + ops steps

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rename brand references**

Replace "Selkies Hub" with "Styx Portal" throughout `README.md` (title + prose). Leave any mention of the upstream Selkies streaming engine / `linuxserver/baseimage-selkies` images intact.

- [ ] **Step 2: Add a migration/ops note**

Add a short "Upgrading from Selkies Hub" section to `README.md`:

````markdown
## Upgrading from Selkies Hub (rebrand)

The rebrand renames the Docker network and SQLite DB. On an existing install:

```bash
docker compose down
docker network rm selkies-hub        # old network
rm -f backend/data/selkies-hub.db    # old DB (state is recreated on first run)
docker compose up -d                 # recreates the styx-portal network + fresh DB
```
````

- [ ] **Step 3: Verify**

Run: `grep -n "Selkies Hub\|selkies-hub" README.md`
Expected: matches only inside the "Upgrading" section's old-name commands (intentional), nothing else.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: rebrand README to Styx Portal + upgrade notes"
```

---

## Final verification

- [ ] **Backend:** `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/` → all pass, clean.
- [ ] **Frontend:** `cd frontend && npm run build` → succeeds.
- [ ] **Brand sweep:** `grep -rni "selkies hub\|selkies-hub" backend/app frontend/src frontend/index.html frontend/package.json README.md | grep -vi "Upgrading\|network rm\|\.db"` → no output (only intentional upstream-tech `Selkies*` identifiers remain).
- [ ] **Login manual check** complete (Task 8 Step 4).
```
