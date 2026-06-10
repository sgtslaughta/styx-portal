# UI Polish Phase 2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use the **frontend-design** skill when building the visual components (Groups D/F especially).

**Goal:** Production-grade polish across every authenticated touchpoint per spec `docs/superpowers/specs/2026-06-10-ui-polish-phase2-design.md`.

**Architecture:** Frontend-only (React 19 + TS + framer-motion + Radix + Tailwind v4). Reads existing Phase-1 backend endpoints; no backend changes. New shared primitives (`PasswordInput`, session-expiry dialog, reduced-motion variants) plus targeted edits to auth pages, instance grid, and provider dialog.

**Tech Stack:** React 19, TypeScript (strict), framer-motion, Radix UI, Tailwind v4, lucide-react, sonner (toasts), zxcvbn.

**Verification model (IMPORTANT — read first):** This frontend has **no unit-test runner** (`package.json` scripts: `dev`/`build`/`preview`/`lint`; lint = `tsc --noEmit`). So tasks are **implement → typecheck → build → manual-verify → commit**, NOT failing-test-first. Every task ends with:
- `cd /home/user/code/remote-access/frontend && npx tsc --noEmit` → 0 errors
- `npm run build` → succeeds
- The manual checks listed in the task (run `npm run dev`, open the page, exercise the states)
Do not claim a task done without tsc + build green.

**Conventions:**
- Work dir: `/home/user/code/remote-access/frontend`. Branch: current (`feat/sso-provider-ux-polish`, Phase 1 merged). No worktree unless the executor prefers one.
- Imports use `@/` alias (= `src/`).
- Commit messages: Conventional Commits, body ends with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- There are uncommitted in-progress files: `LoginBrandPanel.tsx`, `RippleCanvas.tsx`, `index.html`, `frontend/public/`. Tasks 1–13 do NOT touch them. Tasks 14–15 (Group F) build on `LoginBrandPanel.tsx`/`RippleCanvas.tsx` — the executor commits them as part of those tasks.

---

## File map

| File | Responsibility | Tasks |
|---|---|---|
| `src/components/ui/password-input.tsx` (new) | Password field with show/hide toggle | 1 |
| `src/lib/auth-errors.ts` (new) | Map backend auth error strings → friendly copy | 2 |
| `src/pages/LoginPage.tsx` | submit loading, PasswordInput, aria-invalid, error map, SSO retry | 2 |
| `src/pages/SetupWizard.tsx`, `src/pages/AcceptInvitePage.tsx` | PasswordInput, submit loading, aria-invalid | 3 |
| `src/api/client.ts`, `src/pages/LoginPage.tsx` | 401 → `?expired=1` toast | 4 |
| `src/auth/AuthContext.tsx`, `src/components/auth/SessionExpiryDialog.tsx` (new) | proactive expiry warning + Stay-signed-in | 5 |
| `src/components/instances/instance-detail-pane.tsx`, `src/hooks/use-instances.ts` | idle countdown + keepalive | 6 |
| `src/components/instances/instance-grid.tsx` | retry button, bulk-action loading | 7 |
| `src/components/instances/instance-card.tsx`, `instance-grid.tsx` | truncation (names/errors/toasts) | 8 |
| `src/components/instances/instance-detail-pane.tsx` | empty-state CTA | 8 |
| `src/lib/motion.ts` + motion call sites | reduced-motion-aware variants | 9 |
| icon-only buttons, modals | aria-labels, focus | 10 |
| `src/components/system/provider-dialog.tsx` | collapsible sections | 11 |
| `src/components/system/provider-dialog.tsx`, `src/api/client.ts` | readable probe, `auto_promote_admins`, role-map copy | 12 |
| `src/components/system/provider-dialog.tsx`, `src/components/system/users-panel.tsx` | icon preview+validation, invite box | 13 |
| `src/components/auth/LoginBrandPanel.tsx`, `RippleCanvas.tsx` | light-mode brand variant | 14 |
| `src/styles/globals.css`, `src/lib/chart.ts` | light-mode card/chart contrast | 15 |

---

### Task 1: `PasswordInput` shared component

**Files:** Create `src/components/ui/password-input.tsx`.

- [ ] **Step 1: Implement**

```tsx
import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/** Password field with a show/hide toggle. Forwards all Input props except type. */
function PasswordInput({ className, ...props }: Omit<React.ComponentProps<"input">, "type">) {
  const [show, setShow] = React.useState(false);
  return (
    <div className="relative">
      <Input
        type={show ? "text" : "password"}
        className={cn("pr-10", className)}
        {...props}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Hide password" : "Show password"}
        aria-pressed={show}
        tabIndex={-1}
        className="absolute inset-y-0 right-0 flex w-10 items-center justify-center text-muted-foreground hover:text-foreground"
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}

export { PasswordInput };
```

- [ ] **Step 2: Verify** — `npx tsc --noEmit` → 0 errors; `npm run build` → succeeds.
- [ ] **Step 3: Commit** — `git add src/components/ui/password-input.tsx && git commit -m "feat(ui): password input with show/hide toggle"`

---

### Task 2: LoginPage — submit loading, PasswordInput, aria-invalid, error map, SSO retry

**Files:** Create `src/lib/auth-errors.ts`; Modify `src/pages/LoginPage.tsx`.

- [ ] **Step 1: Create the error map** — `src/lib/auth-errors.ts`:

```ts
/** Map backend auth error messages (HTTPException detail) to friendly copy. */
const LOGIN_ERRORS: Record<string, string> = {
  "Invalid credentials": "Email or password is incorrect.",
  "User inactive": "This account is disabled. Contact an administrator.",
  "Too many requests": "Too many attempts. Wait a minute and try again.",
};

export function friendlyLoginError(message: string): string {
  return LOGIN_ERRORS[message] ?? message;
}
```

- [ ] **Step 2: Edit LoginPage.tsx.** Add imports:

```tsx
import { PasswordInput } from "@/components/ui/password-input";
import { friendlyLoginError } from "@/lib/auth-errors";
import { Loader2 } from "lucide-react";
```

Add `submitting` state near the other `useState` calls:

```tsx
  const [submitting, setSubmitting] = useState(false);
```

Replace the `submit` function body:

```tsx
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setErr("");
    setSubmitting(true);
    try {
      await api.login({ username, password });
      await refresh();
      nav("/");
    } catch (e) {
      setErr(friendlyLoginError((e as Error).message));
    } finally {
      setSubmitting(false);
    }
  }
```

Replace the password `<Input type="password" .../>` with:

```tsx
              <PasswordInput
                id="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setP(e.target.value)}
                aria-invalid={err ? true : undefined}
                aria-describedby={err ? "login-error" : undefined}
                required
              />
```

Add `aria-invalid`/`aria-describedby` to the username `<Input>` too (`aria-invalid={err ? true : undefined}`). Give the error `<div>` an id and role:

```tsx
            {err && (
              <div id="login-error" role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {err}
              </div>
            )}
```

Replace the submit `<Button>`:

```tsx
            <Button type="submit" className="w-full" size="default" disabled={submitting}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Signing in…</> : "Sign in"}
            </Button>
```

For SSO retry: in the existing `?error=` effect, after `setErr(...)`, the user can dismiss by retrying SSO (the provider buttons remain). Add a "Dismiss" affordance to the error block when it came from SSO — simplest: add a small button that clears the query param and error:

```tsx
            {err && (
              <div id="login-error" role="alert" className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                <div>{err}</div>
                <button type="button" onClick={() => { setErr(""); window.history.replaceState({}, "", "/login"); }}
                        className="mt-1 text-xs underline underline-offset-2 hover:no-underline">
                  Dismiss
                </button>
              </div>
            )}
```

(This single error block serves both login and SSO errors; Dismiss clears both.)

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual (`npm run dev`): wrong password shows "Email or password is incorrect."; the Sign-in button shows a spinner + "Signing in…" and is disabled during the request; the eye toggle reveals/hides the password; load `/login?error=not_authorized` → friendly message + Dismiss clears it and the URL.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(auth): login submit loading, password toggle, inline error a11y, friendly errors"`

---

### Task 3: SetupWizard + AcceptInvitePage — PasswordInput, submit loading, aria-invalid

**Files:** Modify `src/pages/SetupWizard.tsx`, `src/pages/AcceptInvitePage.tsx`.

Both pages share the same structure (zxcvbn strength meter, `score < 3` gate). Apply the same changes to each.

- [ ] **Step 1: SetupWizard.tsx.** Add imports:

```tsx
import { PasswordInput } from "@/components/ui/password-input";
import { Loader2 } from "lucide-react";
```

Add `submitting` state: `const [submitting, setSubmitting] = useState(false);`. Update `submit`:

```tsx
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (score < 3) { setErr("Password too weak"); return; }
    setSubmitting(true);
    try {
      await api.setup({ username, password });
      await refresh();
      nav("/");
    } catch (e) { setErr((e as Error).message); }
    finally { setSubmitting(false); }
  }
```

Replace the password `<Input type="password" .../>` with `<PasswordInput ... />` (same props minus `type`; add `aria-invalid={err ? true : undefined}`). Replace the submit button:

```tsx
            <Button type="submit" className="w-full" disabled={score < 3 || submitting}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Creating…</> : "Create admin"}
            </Button>
```

- [ ] **Step 2: AcceptInvitePage.tsx.** Same edits: import `PasswordInput` + `Loader2`, add `submitting` state, wrap the accept call with `setSubmitting(true)`/`finally setSubmitting(false)`, swap the password field to `PasswordInput` with `aria-invalid`, and the button:

```tsx
            <Button type="submit" className="w-full" disabled={score < 3 || submitting}>
              {submitting ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Joining…</> : "Join"}
            </Button>
```

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: both pages show the eye toggle; submit buttons spin + disable; strength meter still works.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(auth): setup + accept-invite password toggle and submit loading"`

---

### Task 4: 401 mid-action → friendly "session expired" toast

**Files:** Modify `src/api/client.ts`, `src/pages/LoginPage.tsx`.

Currently `client.ts` redirects to `/login` on 401 silently. Add a query flag and surface it.

- [ ] **Step 1: client.ts.** Change the 401 branch:

```tsx
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.location.href = "/login?expired=1";
    throw new Error("Unauthorized");
  }
```

- [ ] **Step 2: LoginPage.tsx.** Add `import { toast } from "sonner";`. Add an effect (next to the `?error=` effect):

```tsx
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("expired")) {
      toast("Your session expired — please sign in again.");
      window.history.replaceState({}, "", "/login");
    }
  }, []);
```

(Confirm sonner's `<Toaster>` is mounted — it is, in `main.tsx`. Reuse it.)

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: while logged in, delete the `access_token` + `refresh_token` cookies in devtools, trigger any action (e.g. refresh instances) → bounced to `/login?expired=1` → toast appears, URL cleaned to `/login`.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(auth): friendly toast on session-expiry redirect"`

---

### Task 5: Proactive session-expiry warning + "Stay signed in"

**Files:** Create `src/components/auth/SessionExpiryDialog.tsx`; Modify `src/auth/AuthContext.tsx`.

Access token TTL = 900s (15 min). Warn at ~13 min idle. "Stay signed in" calls `POST /api/auth/refresh` (mints a fresh token via cookie) and resets the timer. Any successful API call already silently refreshes the cookie, so this dialog is the **idle-tab fallback**; reset the timer on a global activity listener.

- [ ] **Step 1: Add `refreshSession` to the API.** In `src/api/client.ts`, add to the `api` object (near `logout`):

```tsx
  refreshSession: () => request<{ ok: boolean }>("/auth/refresh", { method: "POST" }),
```

- [ ] **Step 2: Create the dialog** — `src/components/auth/SessionExpiryDialog.tsx`:

```tsx
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function SessionExpiryDialog({
  open, onStay, onSignOut,
}: { open: boolean; onStay: () => void; onSignOut: () => void }) {
  return (
    <Dialog open={open}>
      <DialogContent className="max-w-sm" onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>Your session is about to expire</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-muted-foreground">
          You'll be signed out soon for security. Stay signed in to keep working.
        </p>
        <DialogFooter>
          <Button variant="ghost" onClick={onSignOut}>Sign out</Button>
          <Button onClick={onStay}>Stay signed in</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

(Verify the `Dialog` primitive exports `DialogFooter`; check `src/components/ui/dialog.tsx`. If `DialogFooter` is absent, use a `<div className="flex justify-end gap-2">` instead.)

- [ ] **Step 3: AuthContext.tsx** — add the idle timer + dialog. Import:

```tsx
import { useRef, useCallback } from "react";
import { SessionExpiryDialog } from "@/components/auth/SessionExpiryDialog";
```

Inside `AuthProvider`, add state + timer logic (only active when a user is logged in):

```tsx
  const [showExpiry, setShowExpiry] = useState(false);
  const warnTimer = useRef<number | undefined>(undefined);

  const WARN_AFTER_MS = 13 * 60 * 1000; // warn 2 min before the 15-min access TTL

  const armWarnTimer = useCallback(() => {
    window.clearTimeout(warnTimer.current);
    if (!user) return;
    warnTimer.current = window.setTimeout(() => setShowExpiry(true), WARN_AFTER_MS);
  }, [user]);

  // Reset the warning countdown on real user activity (idle-tab is the only case
  // the dialog needs to catch; active use silently refreshes via the cookie).
  useEffect(() => {
    if (!user) { window.clearTimeout(warnTimer.current); return; }
    armWarnTimer();
    const reset = () => { if (!showExpiry) armWarnTimer(); };
    const events = ["mousedown", "keydown", "scroll", "touchstart"] as const;
    events.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));
    return () => events.forEach((ev) => window.removeEventListener(ev, reset));
  }, [user, showExpiry, armWarnTimer]);

  async function staySignedIn() {
    try { await api.refreshSession(); } catch { /* fall through to 401 path on next call */ }
    setShowExpiry(false);
    armWarnTimer();
  }
```

Render the dialog alongside children:

```tsx
  return (
    <AuthContext.Provider value={{ user, loading, setupRequired, refresh, logout }}>
      {children}
      <SessionExpiryDialog open={showExpiry} onStay={staySignedIn} onSignOut={logout} />
    </AuthContext.Provider>
  );
```

- [ ] **Step 4: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: temporarily set `WARN_AFTER_MS = 5000`, log in, wait 5s idle → dialog appears; "Stay signed in" dismisses it and (Network tab) POSTs `/api/auth/refresh`; moving the mouse before 5s keeps resetting it. **Restore `WARN_AFTER_MS = 13*60*1000` before committing.**
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(auth): proactive session-expiry warning with stay-signed-in"`

---

### Task 6: Idle countdown + "Keep awake" on running instances

**Files:** Modify `src/components/instances/instance-detail-pane.tsx`; add a hook in `src/hooks/use-instances.ts`.

`api.getInstanceStatus(id)` returns `idle_seconds` + `session_config`; `api.keepalive(id)` resets activity. Show remaining idle budget for instances with a finite `idle_timeout` (skip `never_timeout`).

- [ ] **Step 1: Add a keepalive mutation hook** in `src/hooks/use-instances.ts` (mirror the existing mutation hooks there):

```tsx
export function useKeepalive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.keepalive(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["instances"] }),
  });
}
```

(Match the file's existing import of `useMutation`/`useQueryClient` and `api`.)

- [ ] **Step 2: Render countdown + button** in `instance-detail-pane.tsx` for a running instance. Read the current file first to find where status/uptime render. Add, using `getInstanceStatus` (poll via the existing status query if one exists; otherwise a `useQuery` keyed `["instance-status", id]` with `refetchInterval: 30000`):

```tsx
// near other hooks
const keepalive = useKeepalive();
// derive idle config; render only when timeout applies
const sc = instance.session_config as { idle_timeout?: string; never_timeout?: boolean } | null;
const hasTimeout = sc && !sc.never_timeout && sc.idle_timeout;
```

JSX (place in the running-instance detail section):

```tsx
{instance.status === "running" && hasTimeout && (
  <div className="flex items-center gap-2 text-xs text-muted-foreground">
    <span>Auto-stops when idle ({sc!.idle_timeout}).</span>
    <Button size="sm" variant="secondary" className="h-6 text-xs"
            disabled={keepalive.isPending}
            onClick={() => keepalive.mutate(instance.id)}>
      {keepalive.isPending ? "Keeping awake…" : "Keep awake"}
    </Button>
  </div>
)}
```

(A live ticking countdown needs `idle_seconds` from a status poll. If the detail pane already polls status, show `remaining = parseTimeout(idle_timeout) - idle_seconds`; if not, ship the static "Auto-stops when idle" + Keep-awake button now and leave the live countdown as a noted follow-up — do not add a new 30s poll just for this if the pane doesn't already have one. State which you did in the report.)

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: open a running instance with a normal template (idle_timeout 30m) → see the notice + "Keep awake"; clicking it POSTs `/api/instances/{id}/keepalive`; a `never_timeout` template shows nothing.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(instances): idle auto-stop notice and keep-awake button"`

---

### Task 7: Instance grid — retry button + bulk-action loading

**Files:** Modify `src/components/instances/instance-grid.tsx`.

- [ ] **Step 1: Retry button.** `useInstances()` exposes `refetch` (React Query). Pull it: `const { data: instances, isLoading, isError, refetch } = useInstances();`. In the `isError` block (~line 160), add a button:

```tsx
  if (isError) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center text-sm text-muted-foreground">
        <span>Backend unavailable — retrying…</span>
        <Button size="sm" variant="secondary" onClick={() => refetch()}>Retry now</Button>
      </div>
    );
  }
```

- [ ] **Step 2: Bulk-action loading.** The bulk mutations (`bulkStart`/`bulkStop`/`bulkPause`/`bulkUnpause`/`bulkDestroy`) fire `mutate` per instance. Add a derived "busy" flag from the mutation hooks and disable the bulk buttons while any is pending. The hooks (`useStartInstance` etc.) expose `isPending`. Combine:

```tsx
  const bulkBusy = startMut.isPending || stopMut.isPending || pauseMut.isPending || unpauseMut.isPending || destroyMut.isPending;
```

(Use the actual mutation variable names in the file.) Then add `disabled={bulkBusy}` to each bulk `<Button>` in the action bar, and show a spinner on the active one is optional — minimum: disable all during any bulk op to prevent double-fire.

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: stop the backend (`docker compose stop backend`) → grid shows "Retry now"; restart backend, click Retry → grid loads. Select several instances, click a bulk action → buttons disable until the mutations settle.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(instances): retry button on backend error, disable bulk actions while pending"`

---

### Task 8: Truncation + empty-state CTA

**Files:** Modify `src/components/instances/instance-card.tsx`, `instance-grid.tsx`, `instance-detail-pane.tsx`.

- [ ] **Step 1: Name truncation.** In `instance-card.tsx`, the instance name heading: add `truncate` + `title={instance.name}` so long names ellipsize. Same for `instance-card-sm.tsx`/`instance-row.tsx` if they render the name without truncation (check each).

- [ ] **Step 2: Error-message clamp.** Where `instance.error_message` renders (instance-card.tsx), wrap with `line-clamp-3` and a `title` for the full text:

```tsx
{instance.error_message && (
  <p className="line-clamp-3 break-all text-xs text-destructive" title={instance.error_message}>
    {instance.error_message}
  </p>
)}
```

- [ ] **Step 3: Toast truncation.** Add a helper in `src/lib/utils.ts`:

```ts
export function shortError(msg: string, max = 140): string {
  return msg.length > max ? msg.slice(0, max - 1) + "…" : msg;
}
```

Then in `instance-grid.tsx` bulk handlers (and anywhere `toast.error(\`${name}: ${e.message}\`)` appears), wrap the message: `toast.error(shortError(\`${i.name}: ${e.message}\`))` and `console.error(i.name, e)` for the full text.

- [ ] **Step 4: Empty-state CTA.** In `instance-detail-pane.tsx`, the "Select an instance" placeholder → make it actionable:

```tsx
<div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
  <p>No instance selected.</p>
  <p>Pick one from the list, or launch a new one from the Template Gallery.</p>
</div>
```

- [ ] **Step 5: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: an instance named `aaaaaaaa…` (60 chars) ellipsizes with a tooltip; a long `error_message` clamps to 3 lines; placeholder shows the CTA copy.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(instances): truncate long names/errors/toasts, actionable empty state"`

---

### Task 9: Reduced-motion-aware animation variants

**Files:** Modify `src/lib/motion.ts`; apply at framer-motion call sites (`instance-card.tsx`, `instance-grid.tsx`, `instance-card-sm.tsx`, `instance-row.tsx`, settings/system motion components).

framer-motion exposes `useReducedMotion()`. Provide a hook that returns no-op variants when the OS flag is set.

- [ ] **Step 1: motion.ts** — add:

```ts
import { useReducedMotion } from "framer-motion";

/** Returns entrance variants that collapse to instant (no transform/opacity
 *  animation) when the user prefers reduced motion. */
export function useFadeSlideIn(): Variants {
  const reduce = useReducedMotion();
  if (reduce) {
    return { initial: { opacity: 1 }, animate: { opacity: 1 }, exit: { opacity: 1 } };
  }
  return fadeSlideIn;
}
```

- [ ] **Step 2: Apply at call sites.** In each component currently using the static `fadeSlideIn` (or inline `initial/animate/exit` props), call `const variants = useFadeSlideIn();` and pass `variants={variants}`. For the instance-grid bulk action bar slide (`motion.div` with `initial={{ y: ... }}`), guard with `useReducedMotion()`:

```tsx
const reduce = useReducedMotion();
// ...
<motion.div
  initial={reduce ? false : { y: 20, opacity: 0 }}
  animate={reduce ? {} : { y: 0, opacity: 1 }}
  exit={reduce ? {} : { y: 20, opacity: 0 }}
  transition={spring}
>
```

Do this for every `motion.*`/`AnimatePresence` in the listed files. Keep it mechanical: import `useReducedMotion`, branch the transform props.

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: enable OS "Reduce motion" (or devtools rendering emulation: `prefers-reduced-motion: reduce`), reload → instance cards/grid/action bar appear without slide/fade; disable → animations return.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(a11y): honor prefers-reduced-motion across animated components"`

---

### Task 10: aria-labels on icon-only buttons + modal focus

**Files:** icon-only buttons across `instance-grid.tsx`, `instance-card.tsx`, header/theme toggle, row actions; LaunchModal + provider-dialog initial focus.

- [ ] **Step 1: aria-labels.** Find icon-only buttons (a `<Button>`/`<button>` whose only child is a lucide icon, often with `title=`). Add `aria-label` matching the action: select-all checkbox → `aria-label="Select all instances"`; per-row refresh → `aria-label="Refresh"`; view/sort/filter cyclers → describe current action; theme toggle → `aria-label="Toggle theme"`. grep for `<Button` with `size="icon"` and icon-only `title=` usages and label each. (Keep existing `title` for hover tooltip; add `aria-label` for screen readers.)

- [ ] **Step 2: Modal initial focus.** Radix `DialogContent` traps focus already. For LaunchModal and provider-dialog, set focus to the first meaningful field on open: add `autoFocus` to the first text input, or use the `onOpenAutoFocus` already provided by Radix (default focuses first focusable — usually fine; only override if the first focusable is the close button). Verify Esc and overlay-click close work (they do by default unless `onInteractOutside` is prevented — the session dialog intentionally prevents it; others should not).

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: tab through the dashboard with a screen reader or the browser a11y inspector — icon buttons announce their action; opening LaunchModal focuses the name field; Esc closes it.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(a11y): aria-labels on icon buttons, modal initial focus"`

---

### Task 11: Provider dialog — collapsible sections

**Files:** Modify `src/components/system/provider-dialog.tsx` (508 lines, flat scroll).

Group the ~15 fields into collapsible sections to reduce scroll. Use native `<details>`/`<summary>` (no new dep) or a Radix Accordion if one is already in `components/ui`. Check `components/ui` for an `accordion`; if absent, use `<details>`.

- [ ] **Step 1: Read the file fully** and identify field clusters: **Basic** (name, display_label, kind, client_id, client_secret, icon), **Endpoints** (issuer_url / authorize_url / token_url / userinfo_url, scopes), **Role mapping** (groupsClaim, adminGroup, + the new auto_promote in Task 12), **Self-service** (trust_email, allow_signup). Keep the Save footer pinned (already is, line ~455).

- [ ] **Step 2: Wrap clusters.** Each non-Basic cluster becomes:

```tsx
<details className="rounded-md border border-border">
  <summary className="cursor-pointer select-none px-3 py-2 text-sm font-medium">Endpoints</summary>
  <div className="space-y-3 px-3 pb-3">
    {/* existing fields for this cluster */}
  </div>
</details>
```

Leave **Basic** always-visible (no `<details>`). Open the **Endpoints** details by default only when editing an `oauth2`-kind provider (explicit endpoints matter there): `<details open={form.kind === "oauth2"}>`.

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: open the provider dialog (Settings → SSO) → Basic fields visible, Endpoints/Role mapping/Self-service collapsed; expanding/collapsing works; Save still pinned and functional; existing create + edit still round-trip.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(sso): collapsible sections in provider dialog"`

---

### Task 12: Provider dialog — readable test-login probe, `auto_promote_admins`, role-map copy

**Files:** Modify `src/components/system/provider-dialog.tsx`, `src/api/client.ts`.

- [ ] **Step 1: Wire `auto_promote_admins` into the type.** In `client.ts`, add to `OAuthProviderRow`: `auto_promote_admins: boolean;` and to `OAuthProviderCreate`: `auto_promote_admins?: boolean;`. (Backend already returns/accepts it — Phase 1.)

- [ ] **Step 2: Form state + control.** In provider-dialog, add `auto_promote_admins` to the form initial state (default `true`), hydrate from `editing.auto_promote_admins` in the edit effect, include it in the create/update payload, and render a checkbox in the **Role mapping** section:

```tsx
<label className="flex items-start gap-2 text-sm">
  <input type="checkbox" className="mt-0.5"
    checked={form.auto_promote_admins ?? true}
    onChange={(e) => setForm((f) => ({ ...f, auto_promote_admins: e.target.checked }))} />
  <span>
    Auto-promote admins from the identity provider
    <span className="block text-xs text-muted-foreground">
      When on, a user whose groups claim contains the admin group below becomes an
      admin automatically. Turn off to require manual promotion.
    </span>
  </span>
</label>
```

- [ ] **Step 3: Plain-English role-map copy.** Near the `adminGroup` input, replace jargon helper text with:

```tsx
<p className="text-xs text-muted-foreground">
  If a user's <code>{groupsClaim || "groups"}</code> claim contains
  “{adminGroup || "<admin group>"}”, they'll be made an admin.
</p>
```

- [ ] **Step 4: Readable test-login probe.** Replace the raw `<pre>{JSON.stringify(probe, null, 2)}</pre>` (line ~445) with a labeled summary. The probe object shape comes from the backend test endpoint; render the meaningful fields:

```tsx
{probe && (
  <div className="mt-2 space-y-1 rounded-md border border-border p-3 text-xs">
    <div className={probe.would_pass ? "font-medium text-success" : "font-medium text-destructive"}>
      {probe.would_pass ? "✓ This identity would be allowed to sign in" : "✗ This identity would be rejected"}
    </div>
    {probe.email && <div className="text-muted-foreground">Email: {probe.email}{probe.email_verified ? " (verified)" : " (unverified)"}</div>}
    {probe.admin_claim !== undefined && <div className="text-muted-foreground">Admin group matched: {String(probe.admin_claim)}</div>}
  </div>
)}
```

Read the actual probe response keys first (check the backend `oauth_admin.py` test endpoint / the `probe` state assignment in the dialog) and map the real field names. Keep a collapsed `<details><summary>Raw response</summary><pre>…</pre></details>` for power users instead of the bare `<pre>`.

- [ ] **Step 5: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: edit a provider → Role mapping shows the auto-promote toggle + plain-English line; saving persists `auto_promote_admins` (reopen to confirm); running Test login shows the green/red summary with raw response tucked behind a disclosure.
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat(sso): auto-promote toggle, plain-English role mapping, readable test result"`

---

### Task 13: Icon upload preview/validation + invite box

**Files:** Modify `src/components/system/provider-dialog.tsx`, `src/components/system/users-panel.tsx`.

- [ ] **Step 1: Icon preview + size guard.** Find the icon upload handler in provider-dialog (reads a file → base64 data URI into `icon_url`). Before setting it, validate size and show a preview. Replace the onChange:

```tsx
const MAX_ICON_BYTES = 200 * 1024;
function onIconFile(e: React.ChangeEvent<HTMLInputElement>) {
  const file = e.target.files?.[0];
  if (!file) return;
  if (file.size > MAX_ICON_BYTES) {
    setIconError("Icon must be under 200 KB.");
    e.target.value = "";
    return;
  }
  setIconError("");
  const reader = new FileReader();
  reader.onload = () => setForm((f) => ({ ...f, icon_url: reader.result as string }));
  reader.readAsDataURL(file);
}
```

Add `const [iconError, setIconError] = useState("");`, show `{iconError && <p className="text-xs text-destructive">{iconError}</p>}`, and ensure the existing preview `<img src={form.icon_url}>` (line ~250) renders immediately after select (it will, since `icon_url` updates). Wire the file input's `onChange={onIconFile}`.

- [ ] **Step 2: Invite box.** In `users-panel.tsx`, the generated invite token currently shows in small gray text. Present it in a highlighted, copyable box with prominent expiry. Find where `createInvite` result renders and replace with:

```tsx
{invite && (
  <div className="rounded-md border border-primary/40 bg-primary/5 p-3">
    <p className="text-xs font-medium">Invite link (single-use)</p>
    <div className="mt-1 flex items-center gap-2">
      <code className="flex-1 truncate text-xs">{inviteUrl}</code>
      <Button size="sm" variant="secondary" onClick={() => { navigator.clipboard.writeText(inviteUrl); toast.success("Copied"); }}>Copy</Button>
    </div>
    <p className="mt-1 text-xs text-warning">Valid for 72 hours. Share securely — anyone with this link can join.</p>
  </div>
)}
```

(Use the panel's actual invite-state variable + however it builds the full URL; if it only has the token, build `inviteUrl = \`${location.origin}/accept-invite/${invite.token}\``.)

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: upload a >200KB image → inline error, field cleared; upload a small one → instant preview; create an invite → highlighted box with Copy + expiry; Copy puts the URL on the clipboard.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "feat(settings): icon size validation + preview, prominent invite link box"`

---

### Task 14: Light-mode brand panel variant (builds on uncommitted ripple work)

**Files:** Modify `src/components/auth/LoginBrandPanel.tsx`, `src/components/auth/RippleCanvas.tsx`, `src/styles/globals.css` (`.styx-brand`). **This task commits the previously-uncommitted ripple files.**

The brand panel is "always dark by design". Give it a light-theme colorway driven by the active theme class, and make the ripple read theme-aware colors instead of hardcoded dark values.

- [ ] **Step 1: Read** `globals.css` `.styx-brand` rules, `LoginBrandPanel.tsx`, and `RippleCanvas.tsx` fully. Identify the hardcoded dark background/gradient and the ripple's color constants.

- [ ] **Step 2: Theme-aware panel.** In `globals.css`, define `.styx-brand` for both themes — keep the rich dark gradient under `.dark .styx-brand`, add a lighter gradient (e.g. sky/indigo tints on near-white) under the default `.styx-brand`. Ensure the panel's text (`text-white/60`, the heading) gets a readable color per theme: in `LoginBrandPanel.tsx` swap hardcoded `text-white/60` for a token (`text-muted-foreground` won't read on the dark gradient) — instead add a panel-scoped CSS var `--brand-fg` set per theme and use `style`/utility classes, or keep white text on dark and dark text on light via `.styx-brand` color rules in CSS. Simplest: set `color` and a `--brand-fg`/`--brand-fg-muted` in the `.styx-brand` / `.dark .styx-brand` CSS, and have the component use `text-[color:var(--brand-fg)]` / `text-[color:var(--brand-fg-muted)]`.

- [ ] **Step 3: Theme-aware ripple.** In `RippleCanvas.tsx`, replace hardcoded stroke/line colors with values read from CSS custom properties at draw time (e.g. `getComputedStyle(canvas).getPropertyValue('--brand-ripple')`), defined per theme in `globals.css`. Keep the existing reduced-motion + WebGL-availability guards. The ripple should be subtle-light on light theme, current look on dark.

- [ ] **Step 4: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: toggle the app to light theme (the theme toggle in the header, or set system light), load `/login` → brand panel is a light colorway with readable text and a subtle ripple, not a dark slab; dark theme unchanged. Reduced-motion still disables the ripple.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(auth): light-mode brand panel variant with theme-aware ripple"` (this includes the formerly-uncommitted `RippleCanvas.tsx`, `LoginBrandPanel.tsx`, and any `index.html`/`public/` assets they depend on — review `git status` and stage the brand-related files; leave unrelated stray files unstaged and mention them).

---

### Task 15: Light-mode card + chart contrast

**Files:** Modify `src/styles/globals.css`, `src/lib/chart.ts`.

- [ ] **Step 1: Card contrast.** In `globals.css`, find the light-mode `--card-border-color` / card shadow tokens. Increase border saturation and/or shadow so cards separate from the page background in light mode. Example: bump the light `--card-border-color` toward `#c8d5e8` and add a slightly stronger card shadow token. Do NOT change dark-mode values.

- [ ] **Step 2: Chart colors.** In `lib/chart.ts`, check the series colors against a light background. If any are dark-optimized (low contrast on white), provide light-mode-appropriate values (or theme-aware via CSS vars). Keep dark unchanged.

- [ ] **Step 3: Verify** — `npx tsc --noEmit`; `npm run build`. Manual: in light theme, dashboard cards have visible edges/separation; sparklines/charts are legible on the light background; dark theme unchanged.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "fix(ui): stronger card and chart contrast in light mode"`

---

## Spec coverage map

| Spec group | Tasks |
|---|---|
| A — Auth form polish | 1, 2, 3 |
| B — Session resilience | 4, 5, 6 |
| C — Dashboard & error states | 7, 8 |
| D — Settings & provider dialog | 11, 12, 13 |
| E — Accessibility | 9, 10 |
| F — Light mode | 14, 15 |
| G — Copy pass | folded into 2 (errors), 8 (empty state), 12 (jargon/role-map) |

## Notes for the executor

- After each task: `npx tsc --noEmit` AND `npm run build` must both pass before commit. No unit runner exists — the manual checks are the behavioral verification; actually run `npm run dev` and look.
- Use the **frontend-design** skill for Tasks 11–15 (visual judgment on layout, light-mode colorway, ripple). Tasks 1–10 are mechanical enough to do directly.
- Several tasks say "read the file fully first" — honor that; the edits reference regions by content, not just line numbers (line numbers drift as earlier tasks land).
- If a referenced primitive is missing (`DialogFooter`, an Accordion), fall back to the plain-markup alternative noted in the task rather than adding a dependency.
