# Workspaces & Apps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the home page into Workspaces | Apps tabs, add an Apps | Workspaces switch to the app-shell dock, and open things per a per-user "new tab / this tab" preference that is asked once.

**Architecture:** Backend adds two nullable `users` columns plus `PUT /api/auth/me/preferences`. Frontend gets one `OpenPrefProvider` (prompt dialog plus a `useOpenChoice()` hook) mounted in both the SPA and the shell. Every "open" click calls `choose(group, name, run)`. `run(mode)` uses small helpers in `lib/connect-wipe.ts` that call `window.open` synchronously inside the click.

**Tech Stack:** FastAPI + SQLModel (SQLite), React 19 + TanStack Query + Radix (`radix-ui`) + sonner, vitest + Testing Library, Playwright e2e.

**Spec:** `docs/superpowers/specs/2026-10-14-workspaces-apps-design.md`

**Worktree:** `/home/user/code/remote-access-wa` (branch `feat/workspaces-apps`, local only — do not push).

## Global Constraints

- UI names: **Workspaces** (workstations + instances) and **Apps** (proxied services). Settings → Services keeps its name. Code identifiers keep `service`/`instance`/`workstation`.
- Preference values: `NULL` (ask) | `'new_tab'` | `'same_tab'`. Columns `open_workspaces`, `open_apps`.
- Home tab key `styx.home.tab` in localStorage, values `workspaces` | `apps`, default `workspaces`. Every storage access is wrapped in try/catch.
- Prompt copy: title `Open <name>`. Buttons `Open in new tab` (primary, focused) and `Open here`. Checkbox `Remember for all apps` / `Remember for all workspaces`, ticked by default.
- Toasts: `Couldn't save your choice` and `Your browser blocked the new tab, so Styx opened it here.`
- `window.open` must run synchronously inside the click handler and never after an `await`.
- The dock Apps list never prompts; it swaps in place, as it does today.
- Files stay under 500 lines.
- Commits use conventional format with a lowercase subject, body lines ≤100 chars, and the trailer `Co-Authored-By: <model> <noreply@anthropic.com>`.
- Gates before every commit:
  - `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/`
  - `cd frontend && npm test && npm run build` (the build runs `tsc -b`, which is stricter than lint).
- Never touch the live docker stack. e2e uses only the `styx-e2e` compose project.

## Rulings (where the plan deviates from or clarifies the spec)

1. **Connect failure in new-tab mode.** The pre-opened tab is **closed**, and the error or takeover dialog shows in the original tab. The spec instead had the error page shown inside the new tab. This keeps the one existing error and takeover UI.
2. **Takeover pre-check.** It uses the list data: a workstation `in_use && !in_use_self` opens the takeover dialog *before* any tab opens. A server 423 race closes the tab and then opens the dialog.
3. **"Same tab" for workspaces.** It navigates the current tab to `/connecting#…`, which plays the wave and then hands off. Today's behaviour is always a new tab, so the spec's "current behaviour" wording is not literal.
4. **User menu.** There is no avatar menu today. The header username becomes a dropdown trigger (`Account menu`) that holds the **Opening** selectors. The existing **Log out** button stays where it is, because e2e relies on it.
5. **Dock and in-use workstations.** The dock lists a workstation that is in use by someone else as disabled (`in use by X`). Takeover happens only from home.
6. **Shell toasts.** The shell gets a sonner `<Toaster />` so dock toasts (blocked popup, connect error, save failure) are visible.
7. **Preferences not yet loaded.** If `/me` has not loaded at click time, the click prompts as if unset. This is harmless: the prompt only asks.
8. **No new-tab handle for instances.** Instance URLs are known synchronously, but they use the same `openPending` path as workstations, so there is one code path.

## Review Focus

1. **Popup blocker.** Any `await` before `window.open` silently breaks new-tab mode. Tests assert that `window.open` is called before the connect promise resolves (Task 2).
2. **Same-tab plus Remember.** The PUT must be sent before navigation, or a page unload aborts it. Test: `setOpenPrefs` is called before `run` for `same_tab` (Task 3).
3. **Modifier clicks on app tiles** (Ctrl, ⌘, Shift, middle click) keep native browser behaviour and never prompt. A `needs_setup` tile never prompts (Task 4).
4. **Storage blocked or garbage value.** If `styx.home.tab` throws or holds `"foo"`, the page shows Workspaces and does not crash (Task 4).
5. **ConnectingPage pending mode.** A label-only hash waits. A later hash carrying `url` navigates. A cross-origin `url` is still rejected (Task 2).

---

### Task 1: Backend open preferences

**Files:**
- Modify: `backend/app/models.py` (class `User`, after `locked_until`)
- Modify: `backend/app/database.py` (migrations list in `_run_migrations`, after `("proxied_services", "icon_custom", …)`)
- Modify: `backend/app/schemas.py` (`UserOut`; add `OpenPreferences`)
- Modify: `backend/app/routers/auth.py` (`/me`, new `PUT /me/preferences`)
- Create: `backend/tests/test_me_preferences.py`
- Modify: `backend/tests/test_database_migrations.py` (append one test)

**Interfaces:**
- Produces:
  - `GET /api/auth/me` returns `{id, username, email, role, is_active, …, open_workspaces: str|null, open_apps: str|null}`.
  - `PUT /api/auth/me/preferences` takes body `{open_workspaces?, open_apps?}` and returns the same shape. Only provided keys change. Any other value or key returns 422.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_me_preferences.py`:
```python
import pytest
from sqlmodel import select

from app.models import User

URL = "/api/auth/me/preferences"


@pytest.mark.asyncio
async def test_me_exposes_unset_preferences(member_client):
    j = (await member_client.get("/api/auth/me")).json()
    assert j["open_workspaces"] is None and j["open_apps"] is None


@pytest.mark.asyncio
async def test_put_changes_only_given_keys_and_null_resets(member_client):
    r = await member_client.put(URL, json={"open_apps": "new_tab"})
    assert r.status_code == 200, r.text
    assert r.json()["open_apps"] == "new_tab" and r.json()["open_workspaces"] is None
    r = await member_client.put(URL, json={"open_workspaces": "same_tab"})
    assert r.json()["open_apps"] == "new_tab" and r.json()["open_workspaces"] == "same_tab"
    me = (await member_client.get("/api/auth/me")).json()
    assert (me["open_apps"], me["open_workspaces"]) == ("new_tab", "same_tab")
    r = await member_client.put(URL, json={"open_apps": None})
    assert r.json()["open_apps"] is None and r.json()["open_workspaces"] == "same_tab"


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"open_apps": "popup"}, {"open_apps": 1}, {"theme": "dark"}])
async def test_put_rejects_bad_values(member_client, body):
    assert (await member_client.put(URL, json=body)).status_code == 422


@pytest.mark.asyncio
async def test_put_requires_csrf(member_client):
    member_client.headers.pop("X-CSRF-Token")
    assert (await member_client.put(URL, json={"open_apps": "new_tab"})).status_code == 403


@pytest.mark.asyncio
async def test_put_requires_auth(client):
    assert (await client.put(URL, json={"open_apps": "new_tab"})).status_code in (401, 403)


@pytest.mark.asyncio
async def test_other_users_untouched(member_client, session):
    from app.security.passwords import hash_password
    other = User(username="other", password_hash=hash_password("x" * 20))
    session.add(other)
    await session.commit()
    await member_client.put(URL, json={"open_apps": "new_tab", "open_workspaces": "new_tab"})
    o = (await session.exec(select(User).where(User.username == "other"))).first()
    await session.refresh(o)
    assert o.open_apps is None and o.open_workspaces is None
```

Append to `backend/tests/test_database_migrations.py`:
```python
@pytest.mark.asyncio
async def test_migrations_add_open_preference_columns_to_users():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(sqlalchemy.text("CREATE TABLE users (id TEXT PRIMARY KEY)"))
        await _run_migrations(conn)
        rows = (await conn.execute(sqlalchemy.text("PRAGMA table_info(users)"))).fetchall()
        assert {"open_workspaces", "open_apps"} <= {r[1] for r in rows}
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd backend && .venv/bin/python -m pytest tests/test_me_preferences.py tests/test_database_migrations.py -q`
Expected: KeyError `open_workspaces`, 404/405 on PUT, and the missing column.

- [ ] **Step 3: Implement**

`models.py`, in `User` after `locked_until`:
```python
    open_workspaces: str | None = None  # None = ask | new_tab | same_tab
    open_apps: str | None = None
```
`database.py`, append to the migrations list:
```python
        ("users", "open_workspaces", "TEXT"),
        ("users", "open_apps", "TEXT"),
```
`schemas.py`: change `from pydantic import BaseModel, Field, field_validator` to also import `ConfigDict`. Add to `UserOut`:
```python
    open_workspaces: str | None = None
    open_apps: str | None = None
```
Add below `UserOut`:
```python
OpenMode = Literal["new_tab", "same_tab"]


class OpenPreferences(BaseModel):
    """Where Workspaces / Apps open. None = ask. Only keys sent are changed."""
    model_config = ConfigDict(extra="forbid")
    open_workspaces: OpenMode | None = None
    open_apps: OpenMode | None = None
```
`auth.py`: import `OpenPreferences` in the schemas import line. Replace the `/me` handler with:
```python
def _me_out(user: User) -> UserOut:
    return UserOut(id=user.id, username=user.username, email=user.email, role=user.role,
                   is_active=user.is_active, open_workspaces=user.open_workspaces,
                   open_apps=user.open_apps)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return _me_out(user)


@router.put("/me/preferences", response_model=UserOut)
async def set_preferences(body: OpenPreferences, session: AsyncSession = Depends(get_session),
                          user: User = Depends(get_current_user)):
    """Personal UI preference: no admin override, no audit entry."""
    row = await session.get(User, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _me_out(row)
```

- [ ] **Step 4: Run the gates, expect PASS**

Run: `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app/ tests/ && wc -l app/routers/auth.py`
Expected: all pass, ruff clean, `auth.py` < 500 lines.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests/test_me_preferences.py backend/tests/test_database_migrations.py
git commit -m "feat(auth): per-user open preference for workspaces and apps"
```

---

### Task 2: Frontend open primitives and pending connect page

**Files:**
- Modify: `frontend/src/api/client.ts` (types `OpenMode`, `Me`; `me`; add `setOpenPrefs`)
- Modify: `frontend/src/lib/connect-wipe.ts` (rewrite)
- Modify: `frontend/src/pages/ConnectingPage.tsx` (pending mode)
- Create: `frontend/src/lib/__tests__/connect-wipe.test.ts`
- Create: `frontend/src/pages/__tests__/connecting-page.test.tsx`

**Interfaces:**
- Produces (from `@/api/client`):
  - `type OpenMode = "new_tab" | "same_tab"`
  - `type Me = { id: string; username: string; email: string | null; role: string; open_workspaces: OpenMode | null; open_apps: OpenMode | null }`
  - `api.me(): Promise<Me>`
  - `api.setOpenPrefs(p: Partial<Pick<Me, "open_workspaces" | "open_apps">>): Promise<Me>`
- Produces (from `@/lib/connect-wipe`):
  - `BLOCKED: string`
  - `openTab(href: string): Window | null`
  - `openConnectWipe(url: string, label: string): boolean`, which existing callers keep using
  - `openHref(mode: OpenMode, href: string): void`
  - `openPending(mode: OpenMode, label: string, getUrl: () => Promise<string>): Promise<void>`, which rejects with getUrl's error

- [ ] **Step 1: Write the failing tests**

`frontend/src/lib/__tests__/connect-wipe.test.ts`:
```ts
import { afterEach, beforeEach, expect, test, vi } from "vitest";
const toast = vi.fn();
vi.mock("sonner", () => ({ toast: (m: string) => toast(m) }));
import { BLOCKED, openHref, openPending } from "../connect-wipe";

const assign = vi.fn();
let opened: { location: { replace: ReturnType<typeof vi.fn> }; close: ReturnType<typeof vi.fn>; opener: unknown } | null;
beforeEach(() => {
  opened = { location: { replace: vi.fn() }, close: vi.fn(), opener: window };
  vi.spyOn(window, "open").mockImplementation(() => opened as unknown as Window);
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign, origin: "http://localhost" } });
});
afterEach(() => { vi.restoreAllMocks(); assign.mockReset(); toast.mockReset(); });

const hash = (u: string) => JSON.parse(decodeURIComponent(u.split("#")[1]!));

test("new tab opens synchronously, before the url resolves, then hands the url to the tab", async () => {
  let resolve!: (u: string) => void;
  const p = openPending("new_tab", "Connecting to Box…", () => new Promise((r) => { resolve = r; }));
  expect(window.open).toHaveBeenCalledTimes(1);
  expect(hash(vi.mocked(window.open).mock.calls[0]![0] as string)).toEqual({ label: "Connecting to Box…" });
  expect(opened!.opener).toBeNull();
  resolve("/w/box/");
  await p;
  expect(hash(opened!.location.replace.mock.calls[0]![0])).toEqual({ url: "/w/box/", label: "Connecting to Box…" });
  expect(assign).not.toHaveBeenCalled();
});

test("blocked popup falls back to this tab with a toast", async () => {
  opened = null;
  await openPending("new_tab", "L", async () => "/i/x/");
  expect(toast).toHaveBeenCalledWith(BLOCKED);
  expect(hash(assign.mock.calls[0]![0])).toEqual({ url: "/i/x/", label: "L" });
});

test("same tab never opens a window", async () => {
  await openPending("same_tab", "L", async () => "/i/x/");
  expect(window.open).not.toHaveBeenCalled();
  expect(assign.mock.calls[0]![0]).toMatch(/^\/connecting#/);
});

test("failure closes the pre-opened tab and rejects", async () => {
  await expect(openPending("new_tab", "L", async () => { throw new Error("nope"); })).rejects.toThrow("nope");
  expect(opened!.close).toHaveBeenCalled();
});

test("openHref: new tab, blocked fallback, same tab", () => {
  openHref("new_tab", "/_styx/app/s/");
  expect(window.open).toHaveBeenCalledWith("/_styx/app/s/", "_blank");
  expect(assign).not.toHaveBeenCalled();
  opened = null;
  openHref("new_tab", "/_styx/app/s/");
  expect(toast).toHaveBeenCalledWith(BLOCKED);
  expect(assign).toHaveBeenCalledWith("/_styx/app/s/");
  openHref("same_tab", "/x/");
  expect(assign).toHaveBeenLastCalledWith("/x/");
});
```

`frontend/src/pages/__tests__/connecting-page.test.tsx`:
```tsx
import { act, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
vi.mock("@/components/effects/wave-transition", () => ({
  WaveTransition: ({ label }: { label: string }) => <p>{label}</p>,
}));
import { ConnectingPage } from "../ConnectingPage";

const replace = vi.fn();
function at(hash: string) {
  Object.defineProperty(window, "location", { configurable: true,
    value: { origin: "http://localhost", hash, replace } });
}
const enc = (o: object) => "#" + encodeURIComponent(JSON.stringify(o));
afterEach(() => { replace.mockReset(); vi.useRealTimers(); });

test("label-only hash waits, then navigates when the url arrives", () => {
  vi.useFakeTimers();
  at(enc({ label: "Connecting to Box…" }));
  render(<ConnectingPage />);
  expect(screen.getByText("Connecting to Box…")).toBeInTheDocument();
  act(() => { vi.advanceTimersByTime(5000); });
  expect(replace).not.toHaveBeenCalled();
  at(enc({ url: "/w/box/", label: "Connecting to Box…" }));
  act(() => { window.dispatchEvent(new HashChangeEvent("hashchange")); vi.advanceTimersByTime(2000); });
  expect(replace).toHaveBeenCalledWith("/w/box/");
});

test("cross-origin url is rejected", () => {
  at(enc({ url: "https://evil.test/x", label: "x" }));
  render(<ConnectingPage />);
  expect(screen.getByText("Invalid connection link.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd frontend && npx vitest run src/lib/__tests__/connect-wipe.test.ts src/pages/__tests__/connecting-page.test.tsx`
Expected: FAIL. `openPending`/`openHref` don't exist, and a label-only hash shows "Invalid connection link."

- [ ] **Step 3: Implement**

`api/client.ts`: add near the other exported types:
```ts
export type OpenMode = "new_tab" | "same_tab";
export type Me = { id: string; username: string; email: string | null; role: string;
  open_workspaces: OpenMode | null; open_apps: OpenMode | null };
```
Replace the `me:` line and add `setOpenPrefs` right below it:
```ts
  me: () => request<Me>("/auth/me"),
  setOpenPrefs: (p: Partial<Pick<Me, "open_workspaces" | "open_apps">>) =>
    request<Me>("/auth/me/preferences", { method: "PUT", body: JSON.stringify(p) }),
```

`lib/connect-wipe.ts` (whole file):
```ts
import { toast } from "sonner";
import type { OpenMode } from "@/api/client";

export const BLOCKED = "Your browser blocked the new tab, so Styx opened it here.";

/** `/connecting` interstitial; the payload rides in the hash (stateless, no storage races). */
const wipe = (p: { url?: string; label: string }) => `/connecting#${encodeURIComponent(JSON.stringify(p))}`;

/** window.open WITHOUT "noopener" (with it the return is always null, so a blocked popup is
 *  undetectable), then cut the opener link by hand. Call synchronously inside a click. */
export function openTab(href: string): Window | null {
  const w = window.open(href, "_blank");
  if (w) w.opener = null;
  return w;
}

/** New tab that plays the wave, then loads `url`. False if the browser blocked it. */
export function openConnectWipe(url: string, label: string): boolean {
  return openTab(wipe({ url, label })) !== null;
}

/** Open a plain link (an app) per the preference; blocked popup -> this tab + toast. */
export function openHref(mode: OpenMode, href: string): void {
  if (mode === "new_tab") {
    if (openTab(href)) return;
    toast(BLOCKED);
  }
  window.location.assign(href);
}

/** Open a session whose URL arrives asynchronously. The tab opens NOW (inside the click, before any
 *  await, so it is not blocked) on a waiting wave; the URL is handed to it once `getUrl` resolves.
 *  On failure the waiting tab is closed and the error is rethrown for the caller's UI. */
export async function openPending(mode: OpenMode, label: string, getUrl: () => Promise<string>): Promise<void> {
  let w: Window | null = null;
  if (mode === "new_tab") {
    w = openTab(wipe({ label }));
    if (!w) toast(BLOCKED);
  }
  let url: string;
  try {
    url = await getUrl();
  } catch (e) {
    w?.close();
    throw e;
  }
  if (w) w.location.replace(wipe({ url, label })); // same path, new hash: no reload, fires hashchange
  else window.location.assign(wipe({ url, label }));
}
```

`pages/ConnectingPage.tsx`: in `parseHash`, the return type becomes `{ url: string | null; label: string } | null`. Replace the url check `if (typeof data.url !== "string") return null;` and what follows with:
```ts
    const label = typeof data.label === "string" ? data.label : "";
    if (data.url === undefined) return { url: null, label }; // pending: the opener sends the url later
    if (typeof data.url !== "string") return null;
    const resolved = new URL(data.url, window.location.origin);
    if (resolved.origin !== window.location.origin) return null;
    return { url: resolved.pathname + resolved.search + resolved.hash, label };
```
Replace the component body with:
```tsx
export function ConnectingPage() {
  const [target, setTarget] = useState(parseHash);
  const waveDone = useRef(false);
  const url = useRef<string | null>(null);
  url.current = target?.url ?? null;

  // A pending tab (opened before the connect call returned) gets its url via a hash change.
  useEffect(() => {
    const on = () => setTarget(parseHash());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);

  useEffect(() => {
    const u = target?.url;
    if (!u) return;
    if (waveDone.current) { window.location.replace(u); return; }
    // Hard fallback in case the animation's onDone never fires.
    const t = window.setTimeout(() => window.location.replace(u), 2000);
    return () => window.clearTimeout(t);
  }, [target]);

  function done() {
    waveDone.current = true;
    if (url.current) window.location.replace(url.current);
  }

  return (
    <div className="fixed inset-0" style={{ background: "#0c1730" }}>
      <WaveTransition show label={target?.label || "Connecting…"} onDone={done} />
      {!target && (
        <div className="flex h-full items-center justify-center text-sm text-white/70">
          Invalid connection link.
        </div>
      )}
    </div>
  );
}
```
Import `useRef` from react. Update the doc comment: the page is reached via `openConnectWipe` or `openPending`.

- [ ] **Step 4: Run the gates, expect PASS**

Run: `cd frontend && npm test && npm run build`
Expected: green. `openConnectWipe` callers still compile because a boolean return value can be ignored.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/lib frontend/src/pages
git commit -m "feat(frontend): open helpers with detectable popup blocking and a pending connect page"
```

---

### Task 3: Open preference provider and prompt

**Files:**
- Create: `frontend/src/components/open-prompt.tsx`
- Create: `frontend/src/components/__tests__/open-prompt.test.tsx`
- Modify: `frontend/src/main.tsx` (wrap `<Routes>` in `<OpenPrefProvider>`, inside `WaveTransitionProvider`)

**Interfaces:**
- Consumes: `api.me`, `api.setOpenPrefs`, `OpenMode`, `Me` (Task 2).
- Produces (from `@/components/open-prompt`):
  - `type OpenGroup = "workspaces" | "apps"`
  - `useOpenPrefs()`: `useQuery<Me>` with key `["me"]`
  - `useSavePrefs()`: `useMutation` that writes the result into `["me"]`
  - `useOpenChoice(): (group: OpenGroup, name: string, run: (mode: OpenMode) => void) => void`. Without a provider it runs `"new_tab"` directly.
  - `OpenPrefProvider({ children })`

- [ ] **Step 1: Write the failing test**

`frontend/src/components/__tests__/open-prompt.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const me = vi.fn();
const setOpenPrefs = vi.fn();
vi.mock("@/api/client", () => ({ api: { me: () => me(), setOpenPrefs: (p: unknown) => setOpenPrefs(p) } }));
const toastError = vi.fn();
vi.mock("sonner", () => ({ toast: { error: (m: string) => toastError(m) } }));
import { OpenPrefProvider, useOpenChoice } from "../open-prompt";

const base = { id: "u", username: "a", email: null, role: "user", open_workspaces: null, open_apps: null };
const run = vi.fn();
function Btn() {
  const choose = useOpenChoice();
  return <button onClick={() => choose("apps", "Sonarr", run)}>go</button>;
}
function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={qc}><OpenPrefProvider><Btn /></OpenPrefProvider></QueryClientProvider>);
  return qc;
}
beforeEach(() => { run.mockReset(); setOpenPrefs.mockReset(); toastError.mockReset(); me.mockResolvedValue(base); });

test("set preference runs directly, no dialog", async () => {
  me.mockResolvedValue({ ...base, open_apps: "same_tab" });
  setup();
  await waitFor(() => expect(me).toHaveBeenCalled());
  await new Promise((r) => setTimeout(r));
  fireEvent.click(screen.getByText("go"));
  expect(run).toHaveBeenCalledWith("same_tab");
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("unset prompts; new tab runs first, then saves", async () => {
  setOpenPrefs.mockResolvedValue({ ...base, open_apps: "new_tab" });
  setup();
  fireEvent.click(screen.getByText("go"));
  expect(await screen.findByRole("dialog", { name: "Open Sonarr" })).toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "Remember for all apps" })).toBeChecked();
  await waitFor(() => expect(screen.getByRole("button", { name: "Open in new tab" })).toHaveFocus());
  fireEvent.click(screen.getByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalledWith("new_tab");
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_apps: "new_tab" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
});

test("same tab saves BEFORE running (navigation would abort the PUT)", async () => {
  const order: string[] = [];
  setOpenPrefs.mockImplementation(async () => { order.push("save"); return base; });
  run.mockImplementation(() => order.push("run"));
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("button", { name: "Open here" }));
  await waitFor(() => expect(order).toEqual(["save", "run"]));
});

test("remember off: opens, saves nothing", async () => {
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("checkbox", { name: "Remember for all apps" }));
  fireEvent.click(screen.getByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalledWith("new_tab");
  expect(setOpenPrefs).not.toHaveBeenCalled();
});

test("escape cancels: nothing opens or saves", async () => {
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.keyDown(await screen.findByRole("dialog"), { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(run).not.toHaveBeenCalled();
  expect(setOpenPrefs).not.toHaveBeenCalled();
});

test("save failure toasts; the open still happened", async () => {
  setOpenPrefs.mockRejectedValue(new Error("x"));
  setup();
  fireEvent.click(screen.getByText("go"));
  fireEvent.click(await screen.findByRole("button", { name: "Open in new tab" }));
  expect(run).toHaveBeenCalled();
  await waitFor(() => expect(toastError).toHaveBeenCalledWith("Couldn't save your choice"));
});

test("without a provider: runs new_tab", () => {
  render(<Btn />);
  fireEvent.click(screen.getByText("go"));
  expect(run).toHaveBeenCalledWith("new_tab");
});
```

- [ ] **Step 2: Run it, expect FAIL** (module missing)

Run: `cd frontend && npx vitest run src/components/__tests__/open-prompt.test.tsx`

- [ ] **Step 3: Implement** `frontend/src/components/open-prompt.tsx`:

```tsx
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type Me, type OpenMode } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

export type OpenGroup = "workspaces" | "apps";
type Run = (mode: OpenMode) => void;
type Choose = (group: OpenGroup, name: string, run: Run) => void;
const KEY = { workspaces: "open_workspaces", apps: "open_apps" } as const;
const SAVE_FAILED = "Couldn't save your choice";

export const useOpenPrefs = () => useQuery<Me>({ queryKey: ["me"], queryFn: api.me, staleTime: Infinity });

export function useSavePrefs() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: api.setOpenPrefs, onSuccess: (me) => qc.setQueryData(["me"], me) });
}

const Ctx = createContext<Choose | null>(null);
const direct: Choose = (_g, _n, run) => run("new_tab");

/** `choose(group, name, run)`: runs per the saved preference, or asks once. `run` must open
 *  synchronously (window.open inside the click). Outside a provider it just opens a new tab. */
export const useOpenChoice = (): Choose => useContext(Ctx) ?? direct;

export function OpenPrefProvider({ children }: { children: ReactNode }) {
  const { data: me } = useOpenPrefs();
  const save = useSavePrefs();
  const [ask, setAsk] = useState<{ group: OpenGroup; name: string; run: Run } | null>(null);
  const [remember, setRemember] = useState(true);
  const primary = useRef<HTMLButtonElement>(null);

  const choose = useCallback<Choose>((group, name, run) => {
    const pref = me?.[KEY[group]]; // ponytail: not loaded yet = ask (harmless)
    if (pref) run(pref);
    else { setRemember(true); setAsk({ group, name, run }); }
  }, [me]);

  function pick(mode: OpenMode) {
    if (!ask) return;
    const { group, run } = ask;
    setAsk(null);
    if (!remember) return run(mode);
    const p = save.mutateAsync({ [KEY[group]]: mode });
    if (mode === "new_tab") { run(mode); p.catch(() => toast.error(SAVE_FAILED)); } // open inside the click
    else p.catch(() => toast.error(SAVE_FAILED)).finally(() => run(mode)); // navigating away would abort the PUT
  }

  return (
    <Ctx.Provider value={choose}>
      {children}
      <Dialog open={ask !== null} onOpenChange={(o) => { if (!o) setAsk(null); }}>
        <DialogContent className="sm:max-w-sm"
          onOpenAutoFocus={(e) => { e.preventDefault(); primary.current?.focus(); }}>
          <DialogHeader>
            <DialogTitle>Open {ask?.name}</DialogTitle>
            <DialogDescription>Choose where it opens.</DialogDescription>
          </DialogHeader>
          <label className="flex min-h-11 items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={remember}
              onChange={(e) => setRemember(e.target.checked)} />
            Remember for all {ask?.group === "workspaces" ? "workspaces" : "apps"}
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => pick("same_tab")}>Open here</Button>
            <Button ref={primary} onClick={() => pick("new_tab")}>Open in new tab</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Ctx.Provider>
  );
}
```
In `main.tsx`, import `OpenPrefProvider` and wrap `<Routes>…</Routes>` with `<OpenPrefProvider>…</OpenPrefProvider>`.

- [ ] **Step 4: Run the gates, expect PASS:** `cd frontend && npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/open-prompt.tsx frontend/src/components/__tests__/open-prompt.test.tsx frontend/src/main.tsx
git commit -m "feat(frontend): ask-once open preference prompt"
```

---

### Task 4: Home tabs and the Apps grid

**Files:**
- Create: `frontend/src/components/home/home-tabs.tsx`
- Create: `frontend/src/components/home/__tests__/home-tabs.test.tsx`
- Move: `frontend/src/components/instances/service-list.tsx` → `frontend/src/components/home/apps-grid.tsx` (`git mv`); rename the export `ServiceList` → `AppsGrid`
- Move: `frontend/src/components/instances/__tests__/service-list.test.tsx` → `frontend/src/components/home/__tests__/apps-grid.test.tsx` (`git mv`); update the import and the name
- Modify: `frontend/src/components/instances/instance-workspace.tsx`

**Interfaces:**
- Consumes: `useOpenChoice` (Task 3) and `openHref` (Task 2).
- Produces:
  - `HomeTabs({ workspaces, apps }: { workspaces: ReactNode; apps: ReactNode })`
  - `AppsGrid({ onOpenSettings }: { onOpenSettings?: () => void })`, rendered as `<section aria-label="Apps">`

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/home/__tests__/home-tabs.test.tsx`:
```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { HomeTabs } from "../home-tabs";

const ui = () => render(<HomeTabs workspaces={<p>W-body</p>} apps={<p>A-body</p>} />);
beforeEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

test("defaults to Workspaces; tablist semantics", () => {
  ui();
  expect(screen.getByRole("tablist", { name: "Home" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("W-body")).toBeInTheDocument();
});

test("remembers the last tab", () => {
  const { unmount } = ui();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Apps" }), { button: 0 });
  expect(screen.getByText("A-body")).toBeInTheDocument();
  expect(localStorage.getItem("styx.home.tab")).toBe("apps");
  unmount();
  ui();
  expect(screen.getByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
});

test("arrow keys move between tabs", () => {
  ui();
  const ws = screen.getByRole("tab", { name: "Workspaces" });
  ws.focus();
  fireEvent.keyDown(ws, { key: "ArrowRight" });
  expect(screen.getByRole("tab", { name: "Apps" })).toHaveFocus();
});

test("garbage or throwing storage falls back to Workspaces", () => {
  localStorage.setItem("styx.home.tab", "foo");
  const { unmount } = ui();
  expect(screen.getByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  unmount();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  ui();
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Apps" }), { button: 0 });
  expect(screen.getByText("A-body")).toBeInTheDocument();
});
```

In `apps-grid.test.tsx`:
- Rename `ServiceList` → `AppsGrid`, the import → `../apps-grid`, and the describe → `"AppsGrid"`.
- Add `useOpenChoice` and `openHref` mocks at the top, below the existing mocks:
```tsx
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openHref = vi.fn();
vi.mock("@/lib/connect-wipe", () => ({ openHref: (...a: unknown[]) => openHref(...a) }));
```
In `beforeEach`, add `choose.mockReset(); openHref.mockReset();`. In any existing test that asserts the old admin empty copy (`No services yet`), replace it with the new copy. Then append:
```tsx
  test("plain click asks via the Apps preference and opens the shell href", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    renderList();
    fireEvent.click(await screen.findByRole("link", { name: "Open Sonarr" }));
    expect(choose).toHaveBeenCalledWith("apps", "Sonarr", expect.any(Function));
    choose.mock.calls[0]![2]("new_tab");
    expect(openHref).toHaveBeenCalledWith("new_tab", "/_styx/app/sonarr/");
  });

  test("modifier or middle clicks and needs-setup tiles keep native behaviour", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([tile({}), tile({ id: "2", slug: "j", name: "Jelly", needs_setup: true })]);
    renderList();
    const link = await screen.findByRole("link", { name: "Open Sonarr" });
    for (const init of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }])
      fireEvent.click(link, init);
    fireEvent.click(screen.getByRole("link", { name: "Set up Jelly" }));
    expect(choose).not.toHaveBeenCalled();
  });

  test("region is Apps; admin sees an Add app tile", async () => {
    role.current = "admin";
    const onOpenSettings = vi.fn();
    listServiceTiles.mockResolvedValue([tile({})]);
    renderList({ onOpenSettings });
    expect(await screen.findByRole("region", { name: "Apps" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add app" }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  test("empty states", async () => {
    listServiceTiles.mockResolvedValue([]);
    const { unmount } = renderList();
    expect(await screen.findByText("No apps shared with you yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add app" })).toBeNull();
    unmount();
    role.current = "admin";
    renderList();
    expect(await screen.findByText("No apps yet. Add your first app.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add app" })).toBeInTheDocument();
  });
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd frontend && npx vitest run src/components/home`

- [ ] **Step 3: Implement**

`components/home/home-tabs.tsx`:
```tsx
import { useState, type ReactNode } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const KEY = "styx.home.tab";
type Tab = "workspaces" | "apps";

function readTab(): Tab {
  try { return localStorage.getItem(KEY) === "apps" ? "apps" : "workspaces"; } catch { return "workspaces"; }
}

/** Workspaces | Apps switch at the top of home; the last tab is remembered per browser. */
export function HomeTabs({ workspaces, apps }: { workspaces: ReactNode; apps: ReactNode }) {
  const [tab, setTab] = useState(readTab);
  function change(v: string) {
    const t: Tab = v === "apps" ? "apps" : "workspaces";
    setTab(t);
    try { localStorage.setItem(KEY, t); } catch { /* storage blocked: session-only */ }
  }
  return (
    <Tabs value={tab} onValueChange={change} className="h-full min-h-0">
      <TabsList aria-label="Home" className="max-sm:h-11">
        <TabsTrigger value="workspaces" className="px-4">Workspaces</TabsTrigger>
        <TabsTrigger value="apps" className="px-4">Apps</TabsTrigger>
      </TabsList>
      <TabsContent value="workspaces" className="min-h-0 flex-1">{workspaces}</TabsContent>
      <TabsContent value="apps" className="min-h-0 flex-1 overflow-y-auto">{apps}</TabsContent>
    </Tabs>
  );
}
```

`components/home/apps-grid.tsx`: start from the moved `service-list.tsx` and change these parts.
- Rename the export to `AppsGrid`. Keep `TIP_KEY`, `TIP`, `readDismissed` and the tip banner as they are; the tip now lives on the Apps tab.
- Add imports: `Plus` from lucide-react, `useOpenChoice` from `@/components/open-prompt`, `openHref` from `@/lib/connect-wipe`.
- `tileCls`: change `min-h-12 py-2` to `min-h-16 py-3`.
- `Tile`: add a `choose` prop of type `ReturnType<typeof useOpenChoice>` and this handler on the `<a>`:
```tsx
        onClick={(e) => {
          // Native new-tab gestures and the admin setup link keep plain link behaviour.
          if (s.needs_setup || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
          e.preventDefault();
          choose("apps", s.name, (mode) => openHref(mode, href));
        }}
```
- In `AppsGrid`, call `const choose = useOpenChoice();` and pass `choose` to each `<Tile>`.
- Add the admin tile component:
```tsx
function AddAppTile({ onClick }: { onClick?: () => void }) {
  return (
    <button type="button" onClick={onClick}
      className={cn(tileCls, "justify-center border-dashed text-muted-foreground hover:text-foreground")}>
      <Plus className="size-4" aria-hidden />Add app
    </button>
  );
}
```
- Replace the `tiles.length === 0` branch:
```tsx
  if (tiles.length === 0) {
    return (
      <section aria-label="Apps" className="space-y-3">
        <p className="text-sm text-muted-foreground">
          {isAdmin ? "No apps yet. Add your first app." : "No apps shared with you yet."}
        </p>
        {isAdmin && <div className="max-w-xs"><AddAppTile onClick={onOpenSettings} /></div>}
      </section>
    );
  }
```
- In the main return:
  - change `aria-label="Services"` to `"Apps"` and delete the `<h3>Services</h3>`;
  - make the list `grid grid-cols-[repeat(auto-fill,minmax(15rem,1fr))] gap-3`;
  - after the tiles, add `{isAdmin && <li className="flex"><AddAppTile onClick={onOpenSettings} /></li>}`.

`instance-workspace.tsx`: remove the `ServiceList` import. Import `HomeTabs` and `AppsGrid`. Wrap the existing layout:
```tsx
  return (
    <HomeTabs
      apps={<AppsGrid onOpenSettings={onOpenSettings} />}
      workspaces={
        <div className="relative flex h-full gap-3">
          {/* …existing list pane, minus <ServiceList/>, with this heading between WorkstationList and InstanceGrid: */}
          {/* <h3 className="mb-2 text-sm font-medium text-muted-foreground">Instances</h3> */}
          {/* …existing detail pane unchanged… */}
        </div>
      }
    />
  );
```
Write the JSX in full; the comments above only mark where the existing blocks go.

Run `grep -rn "service-list\|ServiceList" frontend/src` afterwards. It must return nothing.

- [ ] **Step 4: Run the gates, expect PASS:** `cd frontend && npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/components
git commit -m "feat(home): workspaces and apps tabs with an apps grid"
```

---

### Task 5: Workspaces open per preference (home)

**Files:**
- Modify: `frontend/src/components/instances/workstation-list.tsx` (`connect`)
- Modify: `frontend/src/components/common/action-bar.tsx` (`connect`)
- Modify: `frontend/src/components/instances/__tests__/workstation-list.test.tsx`
- Create: `frontend/src/components/common/__tests__/action-bar-connect.test.tsx`

**Interfaces:**
- Consumes: `useOpenChoice` (Task 3) and `openPending` (Task 2).

- [ ] **Step 1: Write the failing tests**

Append to `workstation-list.test.tsx`:
- Extend the existing `@/api/client` mock with `workstationConnectUrl: (...a: unknown[]) => connectUrl(...a)`.
- Add `const connectUrl = vi.fn();` above the mocks.
- Add these mocks:
```tsx
const choose = vi.fn((_g: string, _n: string, run: (m: string) => void) => run("new_tab"));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn((_m: string, _l: string, get: () => Promise<string>) => get());
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: Parameters<typeof openPending>) => openPending(...a) }));
```
Then add the tests:
```tsx
test("Connect asks via the Workspaces preference and connects", async () => {
  connectUrl.mockResolvedValue({ url: "/w/studio/" });
  render(<WorkstationList />);
  fireEvent.click(await screen.findByRole("button", { name: "Connect" }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
  expect(openPending.mock.calls[0]![1]).toBe("Connecting to Studio…");
  await waitFor(() => expect(connectUrl).toHaveBeenCalledWith("w9", false));
});
```
`fireEvent`, `waitFor` and `screen` must be imported from `@testing-library/react`. Then add a second test with `row` overridden to `in_use: true, in_use_self: false, in_use_by: "bob"`. Use a `rows` variable that the api mock returns, so the test can swap it. Assert that clicking Connect shows `Take over "Studio"?` and that `openPending` was not called.

`frontend/src/components/common/__tests__/action-bar-connect.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const choose = vi.fn((_g: string, _n: string, run: (m: string) => void) => run("same_tab"));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn(async (_m: string, _l: string, get: () => Promise<string>) => { await get(); });
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: Parameters<typeof openPending>) => openPending(...a) }));
import { ActionBar } from "../action-bar";
import type { Instance } from "@/lib/types";

test("instance Connect uses the Workspaces preference", async () => {
  const inst = { id: "i1", name: "Desk", subdomain: "desk", status: "running" } as Instance;
  render(<QueryClientProvider client={new QueryClient()}><ActionBar instance={inst} /></QueryClientProvider>);
  fireEvent.click(screen.getByRole("button", { name: /connect/i }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Desk", expect.any(Function));
  expect(openPending.mock.calls[0]!.slice(0, 2)).toEqual(["same_tab", "Launching Desk…"]);
  await expect(openPending.mock.calls[0]![2]()).resolves.toBe("/i/desk/");
});
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd frontend && npx vitest run src/components/instances/__tests__/workstation-list.test.tsx src/components/common/__tests__/action-bar-connect.test.tsx`

- [ ] **Step 3: Implement**

`workstation-list.tsx`:
- Replace the `openConnectWipe` import with `import { openPending } from "@/lib/connect-wipe";`.
- Add `import { useOpenChoice } from "@/components/open-prompt";`.
- Inside the component, before the early `return null`, add `const choose = useOpenChoice();` (hooks must not follow a conditional return).
- Replace `connect`:
```tsx
  const connect = (ws: Workstation, force = false) => {
    setErr(null);
    // Takeover is confirmed here, in this tab, before any new tab opens.
    if (!force && ws.in_use && !ws.in_use_self) { setTakeover(ws); return; }
    choose("workspaces", ws.name, (mode) => {
      openPending(mode, `Connecting to ${ws.name}…`, async () => (await api.workstationConnectUrl(ws.id, force)).url)
        .catch((e) => {
          if (e instanceof ApiError && e.status === 423) setTakeover(ws); // raced: someone joined meanwhile
          else setErr((e as Error).message);
        });
    });
  };
```
`action-bar.tsx`:
- Import `openPending` instead of `openConnectWipe`, and import `useOpenChoice`.
- Call `const choose = useOpenChoice();` with the other hooks.
- Replace `connect`:
```tsx
  function connect() {
    choose("workspaces", instance.name, (mode) => {
      openPending(mode, `Launching ${instance.name}…`, async () => `/i/${instance.subdomain}/`)
        .catch((e: Error) => toast.error(`Connect failed: ${e.message}`));
    });
  }
```

- [ ] **Step 4: Run the gates, expect PASS:** `cd frontend && npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components
git commit -m "feat(workspaces): connect opens per the workspaces preference"
```

---

### Task 6: Opening selectors in the user menu

**Files:**
- Create: `frontend/src/components/layout/opening-menu.tsx`
- Create: `frontend/src/components/layout/__tests__/opening-menu.test.tsx`
- Modify: `frontend/src/components/layout/header.tsx` (replace the username `<span>` with `<OpeningMenu username={user.username} />`; keep the wrapper class `flex items-center gap-2 max-sm:ml-auto` because `header.test.tsx` greps for it)

**Interfaces:**
- Consumes: `useOpenPrefs` and `useSavePrefs` (Task 3).

- [ ] **Step 1: Write the failing test**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const setOpenPrefs = vi.fn();
vi.mock("@/api/client", () => ({ api: {
  me: () => Promise.resolve({ id: "u", username: "alice", email: null, role: "user", open_workspaces: "new_tab", open_apps: null }),
  setOpenPrefs: (p: unknown) => setOpenPrefs(p),
} }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
import { OpeningMenu } from "../opening-menu";

test("shows current values incl. Ask, and saves a change", async () => {
  setOpenPrefs.mockResolvedValue({ id: "u", username: "alice", email: null, role: "user", open_workspaces: "new_tab", open_apps: "same_tab" });
  render(<QueryClientProvider client={new QueryClient()}><OpeningMenu username="alice" /></QueryClientProvider>);
  const trigger = screen.getByRole("button", { name: "Account menu" });
  await waitFor(() => expect(trigger).toBeEnabled());
  fireEvent.keyDown(trigger, { key: "Enter" });
  const ws = await screen.findByRole("group", { name: "Workspaces" });
  const apps = screen.getByRole("group", { name: "Apps" });
  expect(within(ws).getByRole("menuitemradio", { name: "New tab" })).toHaveAttribute("aria-checked", "true");
  expect(within(apps).getByRole("menuitemradio", { name: "Ask" })).toHaveAttribute("aria-checked", "true");
  fireEvent.click(within(apps).getByRole("menuitemradio", { name: "This tab" }));
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_apps: "same_tab" }));
});

test("Ask saves null", async () => {
  setOpenPrefs.mockResolvedValue({});
  render(<QueryClientProvider client={new QueryClient()}><OpeningMenu username="alice" /></QueryClientProvider>);
  fireEvent.keyDown(screen.getByRole("button", { name: "Account menu" }), { key: "Enter" });
  const ws = await screen.findByRole("group", { name: "Workspaces" });
  fireEvent.click(within(ws).getByRole("menuitemradio", { name: "Ask" }));
  await waitFor(() => expect(setOpenPrefs).toHaveBeenCalledWith({ open_workspaces: null }));
});
```

- [ ] **Step 2: Run it, expect FAIL:** `cd frontend && npx vitest run src/components/layout`

- [ ] **Step 3: Implement** `components/layout/opening-menu.tsx`:

```tsx
import { ChevronDown, UserRound } from "lucide-react";
import { toast } from "sonner";
import { useOpenPrefs, useSavePrefs } from "@/components/open-prompt";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const ROWS = [["open_workspaces", "Workspaces"], ["open_apps", "Apps"]] as const;

/** Username dropdown: where Workspaces and Apps open (New tab / This tab / Ask). Saves on change. */
export function OpeningMenu({ username }: { username: string }) {
  const { data: me } = useOpenPrefs();
  const save = useSavePrefs();
  const set = (key: (typeof ROWS)[number][0], v: string) =>
    save.mutate({ [key]: v === "ask" ? null : v } as Parameters<typeof save.mutate>[0], {
      onSuccess: () => toast.success("Opening preference saved"),
      onError: () => toast.error("Couldn't save your choice"),
    });
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button aria-label="Account menu" disabled={!me}
          className="inline-flex min-h-9 max-sm:min-h-11 items-center gap-1 rounded-md px-2 text-sm text-muted-foreground hover:text-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <UserRound className="size-4" aria-hidden />
          <span className="max-sm:hidden">{username}</span>
          <ChevronDown className="size-3.5" aria-hidden />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel>Opening</DropdownMenuLabel>
        {ROWS.map(([key, label], i) => (
          <div key={key}>
            {i > 0 && <DropdownMenuSeparator />}
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{label}</DropdownMenuLabel>
            <DropdownMenuRadioGroup aria-label={label} value={me?.[key] ?? "ask"} onValueChange={(v) => set(key, v)}>
              <DropdownMenuRadioItem value="new_tab">New tab</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="same_tab">This tab</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="ask">Ask</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
```
In `header.tsx`, replace `<span className="text-sm text-muted-foreground max-sm:hidden">{user.username}</span>` with `<OpeningMenu username={user.username} />` and add the import.

- [ ] **Step 4: Run the gates, expect PASS:** `cd frontend && npm test && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/layout
git commit -m "feat(header): opening preference selectors in the account menu"
```

---

### Task 7: Dock Apps | Workspaces switch

**Files:**
- Create: `frontend/src/shell/dock-workspaces.tsx`
- Create: `frontend/src/shell/__tests__/dock-workspaces.test.tsx`
- Modify: `frontend/src/shell/dock.tsx` (tabs wrapping the existing list)
- Modify: `frontend/src/shell/shell-app.tsx` (wrap in `OpenPrefProvider`, add `<Toaster />`)
- Modify: `frontend/src/shell/__tests__/shell-app.test.tsx` (mock `me`, `myWorkstations`, `listInstances`; add the switch test)

**Interfaces:**
- Consumes: `useOpenChoice` (Task 3), `openPending` (Task 2), `api.myWorkstations`, `api.listInstances`, `WorkstationIcon`.
- Produces: `DockWorkspaces({ onPicked }: { onPicked: () => void })`. `onPicked` closes the dock before choosing, so the prompt is never stacked on the modal dock.

- [ ] **Step 1: Write the failing tests**

`shell/__tests__/dock-workspaces.test.tsx`:
```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const ws = (o: object) => ({ id: "w1", name: "Studio", status: "online", in_use: false, in_use_self: false,
  in_use_by: null, icon_kind: "auto", icon_etag: "e", os_info: {}, ...o });
const inst = (o: object) => ({ id: "i1", name: "Desk", subdomain: "desk", status: "running", ...o });
const data = { ws: [] as object[], inst: [] as object[] };
vi.mock("@/api/client", () => ({ api: {
  myWorkstations: () => Promise.resolve(data.ws), listInstances: () => Promise.resolve(data.inst),
  workstationConnectUrl: () => Promise.resolve({ url: "/w/studio/" }),
} }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
vi.mock("@/lib/connect-wipe", () => ({ openPending: vi.fn(() => Promise.resolve()) }));
import { DockWorkspaces } from "../dock-workspaces";

const ui = (onPicked = vi.fn()) =>
  render(<QueryClientProvider client={new QueryClient()}><DockWorkspaces onPicked={onPicked} /></QueryClientProvider>);

test("lists workspaces with status; unavailable ones are disabled", async () => {
  data.ws = [ws({}), ws({ id: "w2", name: "Lab", status: "offline" }),
    ws({ id: "w3", name: "Shared", in_use: true, in_use_by: "bob" })];
  data.inst = [inst({}), inst({ id: "i2", name: "Old", status: "stopped" })];
  ui();
  expect(await screen.findByRole("button", { name: /Studio.*online/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Lab.*offline/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Shared.*in use by bob/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Desk.*running/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Old.*stopped/ })).toBeDisabled();
});

test("click closes the dock then asks via the Workspaces preference", async () => {
  data.ws = [ws({})]; data.inst = [];
  const onPicked = vi.fn();
  ui(onPicked);
  fireEvent.click(await screen.findByRole("button", { name: /Studio/ }));
  expect(onPicked).toHaveBeenCalled();
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
});

test("empty state", async () => {
  data.ws = []; data.inst = [];
  ui();
  expect(await screen.findByText("No workspaces yet")).toBeInTheDocument();
});
```
In `shell-app.test.tsx`:
- Extend the `vi.mock("@/api/client"…)` api object with `me: () => Promise.resolve({ id: "u", username: "a", email: null, role: "user", open_workspaces: null, open_apps: null }), myWorkstations: () => Promise.resolve([]), listInstances: () => Promise.resolve([])`.
- Add `vi.mock("sonner", () => ({ Toaster: () => null, toast: Object.assign(vi.fn(), { error: vi.fn() }) }));`.
- Append:
```tsx
it("dock opens on Apps; Workspaces tab shows the workspaces list; app links never prompt", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve(mk()));
  const { container, getByRole, findByRole, queryByRole } = setup();
  await waitFor(() => expect(container.querySelector("iframe")).toBeTruthy());
  fireEvent.click(getByRole("button", { name: /open the styx menu/i }));
  expect(await findByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
  const app = getByRole("link", { name: /Sonarr/ });
  expect(app.getAttribute("href")).toBe("/_styx/app/sonarr/");
  fireEvent.mouseDown(getByRole("tab", { name: "Workspaces" }), { button: 0 });
  expect(await findByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  expect(queryByRole("dialog", { name: /^Open / })).toBeNull();
});
```
The edge-tab accessible name is `Open the Styx menu (Alt+Shift+S)` (see e2e `TAB`). If the edge tab needs a pointer gesture in jsdom, use whatever `ferry.test.tsx` already does to open it.

- [ ] **Step 2: Run them, expect FAIL:** `cd frontend && npx vitest run src/shell`

- [ ] **Step 3: Implement**

`shell/dock-workspaces.tsx`:
```tsx
import { useQuery } from "@tanstack/react-query";
import { Box } from "lucide-react";
import { toast } from "sonner";
import { api, type Workstation } from "@/api/client";
import { useOpenChoice } from "@/components/open-prompt";
import { WorkstationIcon } from "@/components/system/workstation-icon";
import { openPending } from "@/lib/connect-wipe";
import type { Instance } from "@/lib/types";

type Item = { key: string; name: string; icon: React.ReactNode; status: string; ok: boolean; url: () => Promise<string>; verb: string };

function wsItem(w: Workstation): Item {
  const other = w.in_use && !w.in_use_self;
  const status = w.status !== "online" ? "offline" : w.in_use_self ? "connected (you)"
    : other ? `in use by ${w.in_use_by ?? "someone"}` : "online";
  // ponytail: takeover only from home; the dock just lists someone else's session as unavailable
  return { key: `w${w.id}`, name: w.name, icon: <WorkstationIcon ws={w} />, status, ok: w.status === "online" && !other,
    verb: "Connecting to", url: async () => (await api.workstationConnectUrl(w.id)).url };
}

function instItem(i: Instance): Item {
  return { key: `i${i.id}`, name: i.name, icon: <Box className="size-7 shrink-0 p-1 text-muted-foreground" aria-hidden />,
    status: i.status, ok: i.status === "running" || i.status === "idle",
    verb: "Launching", url: async () => `/i/${i.subdomain}/` };
}

const DOT = (ok: boolean) => (ok ? "bg-success" : "bg-transparent ring-1 ring-inset ring-muted-foreground");

/** Dock Workspaces list: open per the Workspaces preference; starting/waking stays on home. */
export function DockWorkspaces({ onPicked }: { onPicked: () => void }) {
  const choose = useOpenChoice();
  const ws = useQuery({ queryKey: ["my-workstations"], queryFn: api.myWorkstations, refetchInterval: 30_000 });
  const inst = useQuery({ queryKey: ["instances"], queryFn: api.listInstances, refetchInterval: 30_000 });
  if (ws.isPending || inst.isPending) return null;
  const items = [...(ws.data ?? []).map(wsItem), ...(inst.data ?? []).map(instItem)];
  if (items.length === 0) return <p className="py-6 text-foreground">No workspaces yet</p>;
  return (
    <ul className="flex flex-1 flex-col gap-1 overflow-y-auto px-2 py-1">
      {items.map((it) => (
        <li key={it.key}>
          <button type="button" disabled={!it.ok}
            onClick={() => {
              onPicked();
              choose("workspaces", it.name, (mode) => {
                openPending(mode, `${it.verb} ${it.name}…`, it.url).catch((e: Error) => toast.error(e.message));
              });
            }}
            className="flex min-h-12 w-full items-center gap-3 rounded-md border border-transparent px-3 text-left hover:bg-foreground/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 disabled:hover:bg-transparent">
            {it.icon}
            <span className="flex-1 truncate">{it.name}</span>
            <span className="text-xs text-muted-foreground">{it.status}</span>
            <span className={`size-2.5 rounded-full ${DOT(it.ok)}`} aria-hidden />
          </button>
        </li>
      ))}
    </ul>
  );
}
```
The button's accessible name is its text content (name plus status), which the tests rely on.

`shell/dock.tsx`:
- Import `useState` and `Tabs, TabsContent, TabsList, TabsTrigger` from `@/components/ui/tabs`, plus `DockWorkspaces`.
- Add `const [view, setView] = useState("apps");` and, in the existing `useEffect`, call `setView("apps")` inside `if (open) {`. The dock opens on Apps every time.
- Wrap the existing `{tiles.length === 0 ? … : (<m.ul …/>)}` block:
```tsx
                <Tabs value={view} onValueChange={setView} className="min-h-0 flex-1">
                  <TabsList aria-label="Switch list" className="w-full">
                    <TabsTrigger value="apps" className="flex-1">Apps</TabsTrigger>
                    <TabsTrigger value="workspaces" className="flex-1">Workspaces</TabsTrigger>
                  </TabsList>
                  <TabsContent value="apps" className="flex min-h-0 flex-col">{/* existing apps block, unchanged */}</TabsContent>
                  <TabsContent value="workspaces" className="flex min-h-0 flex-col">
                    <DockWorkspaces onPicked={() => onOpenChange(false)} />
                  </TabsContent>
                </Tabs>
```
- Update the sr-only description to `Switch apps or workspaces, or go back to Styx`.
- The focus code selects `a[aria-current="page"]` first and then the first `a`. That still lands on the current app because the Apps tab is active on open.

`shell/shell-app.tsx`:
- Import `OpenPrefProvider` and `Toaster` from `sonner`.
- Wrap the final `<div className="h-dvh w-screen">…</div>` in `<OpenPrefProvider>…</OpenPrefProvider>`.
- Add `<Toaster position="bottom-center" />` inside the div.

Run `wc -l frontend/src/shell/dock.tsx`; it must stay under 500 lines.

- [ ] **Step 4: Run the gates, expect PASS:** `cd frontend && npm test && npm run build`. Both bundles build: the SPA and `vite.shell.config.ts`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shell
git commit -m "feat(shell): dock apps and workspaces switch"
```

---

### Task 8: e2e

**Files:**
- Modify: `e2e/playwright.config.ts` (seed `styx.home.tab=apps` for all contexts; add the `workspaces` project)
- Modify: `e2e/tests/screens.ts:74,77`, `e2e/tests/shots-home.spec.ts:20`, `e2e/tests/shell.spec.ts:72` (region `"Services"` → `"Apps"`)
- Modify: `e2e/tests/shell.spec.ts:44` (answer the prompt)
- Create: `e2e/tests/workspaces.spec.ts`

- [ ] **Step 1: Update the existing specs**

`playwright.config.ts`:
- Add above `export default`: `const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080";`
- Set `baseURL: BASE`.
- Add under `use`:
```ts
    // Existing specs assert app tiles on home: start every context on the Apps tab.
    storageState: { cookies: [], origins: [{ origin: BASE, localStorage: [{ name: "styx.home.tab", value: "apps" }] }] },
```
- Append the project `{ name: "workspaces", testMatch: "workspaces.spec.ts", dependencies: ["shots-home"] }`.

Replace `name: "Services"` with `name: "Apps"` on the four region lines listed above.

`shell.spec.ts:44`: after `await p.getByRole("link", { name: "Open Sonarr" }).click();`, add:
```ts
  // First open asks where to open; this tab keeps the rest of the suite in one page.
  await p.getByRole("dialog", { name: "Open Sonarr" }).getByRole("button", { name: "Open here" }).click();
```

- [ ] **Step 2: Write the new spec** `e2e/tests/workspaces.spec.ts`:

```ts
import { expect, test } from "@playwright/test";
import { ADMIN, apiCall, uiLogin } from "./helpers";

test.describe.configure({ mode: "serial" });

test("first app open asks, remember new tab, second open goes straight to a new tab", async ({ browser }) => {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, ADMIN);
  await expect(p.getByRole("button", { name: "Log out" })).toBeVisible();
  await apiCall(ctx, "PUT", "/api/auth/me/preferences", { open_apps: null, open_workspaces: null });
  await p.goto("/");
  const tile = p.getByRole("region", { name: "Apps" }).getByRole("link", { name: "Open Sonarr" });
  await tile.click();
  const dlg = p.getByRole("dialog", { name: "Open Sonarr" });
  await expect(dlg.getByRole("checkbox", { name: "Remember for all apps" })).toBeChecked();
  await expect(dlg.getByRole("button", { name: "Open in new tab" })).toBeFocused();
  const [first] = await Promise.all([ctx.waitForEvent("page"), dlg.getByRole("button", { name: "Open in new tab" }).click()]);
  await expect(first).toHaveURL(/\/_styx\/app\/sonarr\/$/);
  await expect(p).toHaveURL(/\/$/);
  await expect.poll(async () => (await apiCall(ctx, "GET", "/api/auth/me")).open_apps).toBe("new_tab");
  const [second] = await Promise.all([ctx.waitForEvent("page"), tile.click()]);
  await expect(second).toHaveURL(/\/_styx\/app\/sonarr\/$/);
  await expect(p.getByRole("dialog")).toHaveCount(0);
  await apiCall(ctx, "PUT", "/api/auth/me/preferences", { open_apps: null });
  await ctx.close();
});

test("home tab persists across reload", async ({ browser }) => {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, ADMIN);
  await p.getByRole("tab", { name: "Workspaces" }).click();
  await p.reload();
  await expect(p.getByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  await p.getByRole("tab", { name: "Apps" }).click();
  await p.reload();
  await expect(p.getByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
  await ctx.close();
});

test("dock switches between Apps and Workspaces", async ({ browser }) => {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, ADMIN);
  await p.goto("/_styx/app/sonarr/");
  await p.locator('[aria-label="Open the Styx menu (Alt+Shift+S)"]').click();
  const dock = p.getByRole("dialog");
  await expect(dock.getByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
  await dock.getByRole("tab", { name: "Workspaces" }).click();
  await expect(dock.getByText("No workspaces yet")).toBeVisible(); // the e2e stack has no workstations or instances
  await dock.getByRole("tab", { name: "Apps" }).click();
  await expect(dock.getByRole("link", { name: /Sonarr/ })).toBeVisible();
  await ctx.close();
});
```

- [ ] **Step 3: Run the full e2e**

Run: `cd /home/user/code/remote-access-wa && e2e/run.sh`
Expected: all specs pass, the existing 47 plus 3 new.

`run.sh` tears the `styx-e2e` stack down and rebuilds it. Afterwards, restart the smoke stack from `/home/user/code/remote-access-smoke/e2e` with the override command recorded in the session notes, and tell the user it was restarted. Never touch the live stack.

- [ ] **Step 4: Commit**

```bash
git add e2e
git commit -m "test(e2e): workspaces and apps tabs, open prompt, dock switch"
```

---

## Done criteria

- Every task is committed. pytest, ruff, vitest and `npm run build` are green, and e2e is green.
- `wc -l` shows every touched file under 500 lines.
- Branch `feat/workspaces-apps` stays local. Before any push, the user decides the merge order: it rebases onto main after SP1.5, icons and favicons land.
