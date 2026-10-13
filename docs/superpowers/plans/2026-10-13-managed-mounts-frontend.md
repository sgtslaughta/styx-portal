# Managed Mounts (SP1.5) — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** New Styx identity app-wide, admin UI for managed base paths (consent, stepper, rollback), focus-aware home tiles, and the Styx shell with the ferry dock.

**Architecture:** Main SPA (`index.html`) gains tokens/font, stepper, form/consent/job panel and tiles. A second Vite build (`shell.html`, base `/_styx/app/`, output `dist/_styx/app/`) renders the shell: same-origin iframe + dock, sharing `src/` code.

**Tech Stack:** React 19, Tailwind v4 + shadcn (new-york), `radix-ui`, `framer-motion@^12.40` (installed), `@tanstack/react-query@^5.75` (installed), `lucide-react`, vitest + Testing Library. New package: `@fontsource-variable/commissioner` only.

**Spec:** `docs/superpowers/specs/2026-10-13-managed-mounts-design.md` · Backend plan: `2026-10-13-managed-mounts-backend.md` (endpoints used here are defined there).

Worktree `/home/user/code/remote-access-mounts`, run from `frontend/`:
- tests `npm test` · gate `npm run build` (tsc -b; stricter than `tsc --noEmit`) · both must pass before every commit.

## Global Constraints

- Files < 500 lines. Semantic commits + trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Tokens (hex): Water `#0F1C22`, Mist `#EDF1EF`, Current `#2A767C`, Obol `#B88A3E` (fills/rings only), Obol text light `#86601F` / dark `#D2A657`, Ember `#B8432A`, Reed `#4F9A6C` (dots/fills), Reed text light `#3A7A53` / dark `#7CC49A`.
- Every text/background pair ≥ 4.5:1 (enforced by the token test).
- One typeface: Commissioner (bundled). Body 15px/1.55, scale ×1.25, headings 600. Sentence case, no all-caps labels, no `→` in buttons, no middle-dot meta strings.
- Obol means "you're in / active / verified" and nothing else.
- One orchestrated motion moment: the dock opening. `MotionConfig reducedMotion="user"`; `LazyMotion features={domAnimation}`.
- Hotkey Alt+Shift+S; Esc closes; edge tab hit area ≥ 44×44.
- Copy: active voice, the button names the outcome ("Restart Sonarr and apply"), errors say what happened and what to do.
- Mobile: shell/dock/tiles fully usable 360–430 px; admin form single column.

## Review Focus

1. Frame navigates outside its app (path app links to `/other/`) → shell leaves the frame and navigates the top window there; never shows Styx-in-Styx. (Task 8)
2. `localStorage` throws (private mode) → edge tab still renders at right-middle, dock works. (Task 9)
3. Job poll returns 404 (no job yet) → panel shows the plan, not an error. (Task 5)
4. Tile list empty in the shell → dock shows "No apps yet" with Home, not a blank panel. (Task 9)
5. Inner path in the shell URL is `//evil.example` or `/%2e%2e/` → frame loads the app root instead. (Task 8)

---

### Task 1: Styx identity — tokens and font

**Files:**
- Modify: `src/styles/globals.css` (`:root`, `.dark`, `@theme inline` additions)
- Modify: `src/main.tsx` (font import), `package.json` (dep)
- Create: `src/styles/tokens.ts`, `src/lib/__tests__/tokens.test.ts`

**Interfaces:**
- Produces: CSS vars `--obol`, `--obol-foreground` (text), `--success-foreground`; Tailwind colors `obol`, `obol-foreground`, `success-foreground` via `@theme inline`; `TOKENS` table + `contrast(a,b)` in `src/styles/tokens.ts`.

- [ ] **Step 1:** `npm i @fontsource-variable/commissioner@5.3.0` then `ls node_modules/@fontsource-variable/commissioner/*.css` — note whether a file exposing the `FLAR` axis exists (e.g. `full.css`). Use it if present, else `index.css`.
- [ ] **Step 2: Failing test** `src/lib/__tests__/tokens.test.ts`

```ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { TOKENS, TEXT_PAIRS, contrast } from "@/styles/tokens";

describe("Styx tokens", () => {
  it.each(TEXT_PAIRS)("%s on %s ≥ 4.5:1 (%s)", (fg, bg) => {
    expect(contrast(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });
  it("globals.css uses the token hexes", () => {
    const css = readFileSync("src/styles/globals.css", "utf8").toLowerCase();
    for (const hex of Object.values(TOKENS.light).concat(Object.values(TOKENS.dark))) {
      expect(css).toContain(hex.toLowerCase());
    }
  });
});
```
- [ ] **Step 3:** `npm test -- tokens` → FAIL.
- [ ] **Step 4: Implement** `src/styles/tokens.ts`

```ts
/** Styx identity (spec §7). globals.css must use exactly these values. */
export const TOKENS = {
  light: { background: "#EDF1EF", foreground: "#0F1C22", card: "#F7F9F8", muted: "#DFE6E3",
    mutedForeground: "#4A5A60", border: "#C9D3D0", primary: "#2A767C", primaryForeground: "#F7F9F8",
    destructive: "#B8432A", success: "#4F9A6C", successForeground: "#3A7A53",
    obol: "#B88A3E", obolForeground: "#86601F", ring: "#2A767C" },
  dark: { background: "#0F1C22", foreground: "#EDF1EF", card: "#15262D", muted: "#1D3139",
    mutedForeground: "#9FB0B4", border: "#2A4049", primary: "#2A767C", primaryForeground: "#EDF1EF",
    destructive: "#E07A5F", success: "#4F9A6C", successForeground: "#7CC49A",
    obol: "#B88A3E", obolForeground: "#D2A657", ring: "#6FB7BC" },
} as const;

/** [fg, bg, label] pairs that carry text. */
export const TEXT_PAIRS: [string, string, string][] = [
  [TOKENS.light.foreground, TOKENS.light.background, "light body"],
  [TOKENS.light.mutedForeground, TOKENS.light.background, "light muted"],
  [TOKENS.light.mutedForeground, TOKENS.light.card, "light muted on card"],
  [TOKENS.light.primaryForeground, TOKENS.light.primary, "light button"],
  [TOKENS.light.primary, TOKENS.light.background, "light link"],
  [TOKENS.light.destructive, TOKENS.light.background, "light danger"],
  [TOKENS.light.obolForeground, TOKENS.light.background, "light obol text"],
  [TOKENS.light.successForeground, TOKENS.light.background, "light ok text"],
  [TOKENS.dark.foreground, TOKENS.dark.background, "dark body"],
  [TOKENS.dark.mutedForeground, TOKENS.dark.card, "dark muted on card"],
  [TOKENS.dark.primaryForeground, TOKENS.dark.primary, "dark button"],
  [TOKENS.dark.ring, TOKENS.dark.background, "dark link"],
  [TOKENS.dark.destructive, TOKENS.dark.background, "dark danger"],
  [TOKENS.dark.obolForeground, TOKENS.dark.background, "dark obol text"],
  [TOKENS.dark.successForeground, TOKENS.dark.background, "dark ok text"],
];

const lum = (hex: string) => {
  const c = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
    .map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
export const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
```
In `globals.css` replace the `:root` and `.dark` values with the hexes above (map: `--background`, `--foreground`, `--card`/`--popover` = card, `--card-foreground`/`--popover-foreground` = foreground, `--primary`, `--primary-foreground`, `--secondary`/`--muted`/`--accent` = muted, `--secondary-foreground`/`--accent-foreground` = foreground, `--muted-foreground`, `--destructive`, `--border`/`--input` = border, `--ring`, `--success`), add `--obol`, `--obol-foreground`, `--success-foreground`, and in `@theme inline` add `--color-obol: var(--obol); --color-obol-foreground: var(--obol-foreground); --color-success-foreground: var(--success-foreground); --font-sans: "Commissioner Variable", ui-sans-serif, system-ui, sans-serif;`. Leave chart colours. Add base type:
```css
@layer base {
  html { font-size: 15px; }
  body { line-height: 1.55; }
  h1, h2, h3 { font-weight: 600; letter-spacing: -0.01em; line-height: 1.2; font-variation-settings: "FLAR" 40; }
}
```
(Drop the `font-variation-settings` line if Step 1 found no FLAR axis.) `main.tsx`: `import "@fontsource-variable/commissioner";` (or the FLAR css file) above the globals import.
- [ ] **Step 5:** `npm test` + `npm run build` PASS. Open `npm run dev`, check login, home, admin in light and dark; fix any hard-coded blue (`grep -rn "blue-\|oklch(0.55 0.17 255)" src`).
- [ ] **Step 6: Commit** `feat(ui): Styx identity tokens (Water/Mist/Current/Obol) and Commissioner type`

---

### Task 2: API client additions + shared tile helpers

**Files:**
- Modify: `src/api/client.ts`
- Create: `src/lib/service-tiles.ts` (move `toTile`, `HEALTH` out of `service-list.tsx`)
- Modify: `src/components/instances/service-list.tsx` (import them)
- Test: `src/api/services-client.test.ts` (append), `src/lib/__tests__/service-tiles.test.ts`

**Interfaces:**
- Produces (types): `ProxiedService` + `mount_managed: boolean; pass_identity: boolean; frame_ok: boolean`; `ServiceTile` + `frame_ok: boolean`; `ServicePreset` + `subpath: { methods: unknown[]; verify_path?: string } | null`; `BypassRule` + `header_prefix?: string | null; required_query?: string | null`;
  `MountChange = { target: string; key: string; old: string | null; new: string }`;
  `MountPlan = { method: "config_file" | null; changes: MountChange[]; needs_consent: boolean; reason: string | null }`;
  `JobStep = { id: string; label: string; state: "pending" | "active" | "done" | "failed" | "skipped"; detail: string | null }`;
  `MountJob = { id: string; state: "pending" | "running" | "done" | "rolled_back" | "failed"; steps: JobStep[]; changes: MountChange[]; backup_dir: string | null; log_excerpt: string | null; created_at: string; finished_at: string | null }`.
- Produces (api): `mountPlan(id) → MountPlan`, `mountApply(id, consent: boolean) → {job_id}`, `mountLatest(id) → MountJob` (404 → throws `ApiError` with `status` 404, as other calls do), `serviceFocus() → {slug: string | null}`.
- Produces (lib): `toTile(s)`, `HEALTH(up)`, `shellHref(t: ServiceTile) → string` (`/_styx/app/<slug>/`, or bare app when `!frame_ok`: `/<slug>/` for path, `/_styx/open/<slug>` for focus).

- [ ] **Step 1: Failing tests**

```ts
// src/lib/__tests__/service-tiles.test.ts
import { describe, expect, it } from "vitest";
import { shellHref, toTile } from "@/lib/service-tiles";
const t = (o = {}) => ({ id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path" as const,
  enabled: true, up: true, frame_ok: true, ...o });
describe("shellHref", () => {
  it("opens in the shell by default", () => expect(shellHref(t())).toBe("/_styx/app/sonarr/"));
  it("bare path app without overlay", () => expect(shellHref(t({ frame_ok: false }))).toBe("/sonarr/"));
  it("bare focus app without overlay", () =>
    expect(shellHref(t({ mount_mode: "cookie-root", frame_ok: false }))).toBe("/_styx/open/sonarr"));
  it("focus app in shell goes through open", () =>
    expect(shellHref(t({ mount_mode: "cookie-root" }))).toBe("/_styx/open/sonarr"));
});
describe("toTile", () => {
  it("maps admin rows", () => expect(toTile({ ...t(), health_status: "unhealthy" } as never).up).toBe(false));
});
```
Note the last `shellHref` case: focus apps always start at `/_styx/open/<slug>` (sets the cookie, then the backend redirects to the shell), so `frame_ok` only decides the redirect target server-side — keep it simple: focus → `/_styx/open/<slug>` in both cases.

```ts
// append to src/api/services-client.test.ts, following the file's fetch-mock helpers
it("mount endpoints", async () => {
  await api.mountPlan("s1"); expect(lastCall()[0]).toBe("/api/services/s1/mount/plan");
  await api.mountApply("s1", true);
  expect(lastCall()[0]).toBe("/api/services/s1/mount/apply");
  expect(JSON.parse(lastCall()[1].body)).toEqual({ consent: true });
  await api.mountLatest("s1"); expect(lastCall()[0]).toBe("/api/services/s1/mount/jobs/latest");
  await api.serviceFocus(); expect(lastCall()[0]).toBe("/api/services/focus");
});
```
- [ ] **Step 2:** FAIL. **Step 3:** implement (methods next to `enterService`):
```ts
  mountPlan: (id: string) => request<MountPlan>(`/services/${id}/mount/plan`, { method: "POST" }),
  mountApply: (id: string, consent: boolean) =>
    request<{ job_id: string }>(`/services/${id}/mount/apply`, { method: "POST", body: JSON.stringify({ consent }) }),
  mountLatest: (id: string) => request<MountJob>(`/services/${id}/mount/jobs/latest`),
  serviceFocus: () => request<{ slug: string | null }>("/services/focus"),
```
`src/lib/service-tiles.ts`: move `toTile` + `HEALTH` verbatim (add `frame_ok: s.frame_ok` to `toTile`), add
```ts
export function shellHref(t: ServiceTile): string {
  if (t.mount_mode === "cookie-root") return `/_styx/open/${t.slug}`;
  return t.frame_ok ? `/_styx/app/${t.slug}/` : `/${t.slug}/`;
}
```
(Backend Task 6 `_focus_response` redirects to `/_styx/app/<slug>/` when `frame_ok`, else `/`.)
- [ ] **Step 4:** PASS + build. **Step 5: Commit** `feat(ui): mount/focus API client and shared tile helpers`

---

### Task 3: Stepper component (+ image pulls)

**Files:**
- Create: `src/components/ui/stepper.tsx`, `src/components/ui/__tests__/stepper.test.tsx`
- Modify: `src/components/instances/icon-viewport.tsx` (pulling state)

**Interfaces:**
- Produces: `Stepper({ steps, className }: { steps: StepItem[]; className?: string })`, `type StepItem = { id: string; label: string; state: "pending" | "active" | "done" | "failed" | "skipped"; detail?: string | null; percent?: number | null }` (`JobStep` is assignable).

- [ ] **Step 1: Failing test**

```tsx
import { render, screen } from "@testing-library/react";
import { Stepper } from "@/components/ui/stepper";
const steps = [
  { id: "a", label: "Back up settings", state: "done" as const },
  { id: "b", label: "Apply base path", state: "active" as const, percent: 40, detail: "Writing config.xml" },
  { id: "c", label: "Restart app", state: "failed" as const, detail: "Timed out" },
  { id: "d", label: "Check it answers", state: "skipped" as const },
];
it("renders an ordered list with states", () => {
  render(<Stepper steps={steps} />);
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(4);
  expect(items[1]).toHaveAttribute("aria-current", "step");
  expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
  expect(screen.getByText("Timed out")).toBeInTheDocument();
  expect(items[0]).toHaveTextContent(/done/i);      // sr-only state text
});
```
- [ ] **Step 2:** FAIL. **Step 3: Implement**

```tsx
import { Check, Circle, Loader2, Minus, X } from "lucide-react";
import { cn } from "@/lib/utils";

export type StepItem = { id: string; label: string;
  state: "pending" | "active" | "done" | "failed" | "skipped"; detail?: string | null; percent?: number | null };

const ICON = {
  pending: <Circle className="h-4 w-4 text-muted-foreground" />,
  active: <Loader2 className="h-4 w-4 animate-spin text-primary motion-reduce:animate-none" />,
  done: <Check className="h-4 w-4 text-success-foreground" />,
  failed: <X className="h-4 w-4 text-destructive" />,
  skipped: <Minus className="h-4 w-4 text-muted-foreground" />,
};
const SR = { pending: "Not started", active: "In progress", done: "Done", failed: "Failed", skipped: "Skipped" };

/** Numbered sequence (the content is a real sequence: backup → apply → restart → verify, or pull → start). */
export function Stepper({ steps, className }: { steps: StepItem[]; className?: string }) {
  return (
    <ol className={cn("space-y-3", className)}>
      {steps.map((s, i) => (
        <li key={s.id} aria-current={s.state === "active" ? "step" : undefined} className="flex gap-3">
          <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full border",
            s.state === "done" ? "border-success/50" : s.state === "failed" ? "border-destructive/60"
              : s.state === "active" ? "border-primary" : "border-border")}>
            {s.state === "pending" ? <span className="text-xs text-muted-foreground">{i + 1}</span> : ICON[s.state]}
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <p className={cn("text-sm", s.state === "pending" || s.state === "skipped" ? "text-muted-foreground" : "font-medium")}>
              {s.label}<span className="sr-only"> ({SR[s.state]})</span>
            </p>
            {s.percent != null && s.state === "active" && (
              <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(s.percent)}
                aria-label={s.label} className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-muted">
                <div className="h-full bg-primary transition-[width] motion-reduce:transition-none" style={{ width: `${s.percent}%` }} />
              </div>
            )}
            {s.detail && <p className={cn("mt-1 break-words text-xs", s.state === "failed" ? "text-destructive" : "text-muted-foreground")}>{s.detail}</p>}
          </div>
        </li>
      ))}
    </ol>
  );
}
```
In `icon-viewport.tsx`, replace the `⏳` branch with a centred card:
```tsx
  const iconContent = instance.status === "pulling" ? (
    <div className="w-[min(18rem,80%)] rounded-lg bg-card/90 p-4">
      <Stepper steps={[
        { id: "pull", label: "Download image", state: "active", percent: instance.pull_percent, detail: instance.pull_detail },
        { id: "start", label: "Start", state: "pending" },
      ]} />
    </div>
  ) : ...
```
(Add an icon-viewport test asserting a `progressbar` renders when `status: "pulling", pull_percent: 30` — follow the existing tests in `src/components/instances/__tests__` for the instance fixture.)
- [ ] **Step 4:** PASS + build. **Step 5: Commit** `feat(ui): shared Stepper; show image pull progress with it`

---

### Task 4: Service form — mount line, access toggles, overlay option

**Files:**
- Create: `src/components/system/service-form-access.tsx` (Access section moved out of `service-form.tsx`)
- Modify: `src/components/system/service-form.tsx`, `src/components/common/risk-callout.tsx` (`RISK.nativeApps`, `RISK.passIdentity`)
- Test: `src/components/system/__tests__/service-form-access.test.tsx`

**Interfaces:**
- Produces: `AccessSection({ f, set, preset, groups, errors })` where `f: ProxiedServiceInput`, `set: <K extends keyof ProxiedServiceInput>(k: K, v: ProxiedServiceInput[K]) => void`, `preset?: ServicePreset`.
- Behaviour:
  - Mount line (read-only): `cookie-root` → "Focus: opens on its own"; `path` with preset `subpath` → "Path /<slug>, configured by Styx"; `path` otherwise → "Path /<slug>, set the app's base path yourself" + `preset.base_url_hint`.
  - `<details>` "Advanced" holds: the existing mount-mode select (labels "Path (/slug)" / "Focus (opens on its own)"), the existing auth-mode select, the bypass editor, and a switch **Open without overlay** (`frame_ok` inverted).
  - Switch **Allow native apps** (only when the preset has `bypass_rules`): on → `auth_mode="sso-with-bypass"` and `bypass_rules` = preset's; off → `auth_mode="sso"`. Red `RiskCallout` when on.
  - Switch **Pass identity** → `pass_identity`; neutral callout when on.

- [ ] **Step 1: Failing test**

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { AccessSection } from "../service-form-access";
const preset = { id: "jellyfin", name: "Jellyfin", icon: null, default_port: 8096, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [{ path_prefix: "/jellyfin/", required_header: "X-Emby-Token" }], health_path: null, verify_tls: true,
  base_url_hint: null, warnings: [], subpath: { methods: [{}] } } as never;
function Harness(p: { f?: object }) {
  const [f, setF] = useState({ slug: "jellyfin", mount_mode: "path", auth_mode: "sso", bypass_rules: [],
    allowed_groups: [], pass_identity: false, frame_ok: true, ...p.f } as never);
  return <><AccessSection f={f} set={(k, v) => setF((o: object) => ({ ...o, [k]: v }) as never)} preset={preset} groups={[]} errors={{}} />
    <output data-testid="state">{JSON.stringify(f)}</output></>;
}
const state = () => JSON.parse(screen.getByTestId("state").textContent!);
it("shows the managed mount line", () => {
  render(<Harness />);
  expect(screen.getByText("Path /jellyfin, configured by Styx")).toBeInTheDocument();
});
it("native apps toggles bypass mode and shows the risk", () => {
  render(<Harness />);
  fireEvent.click(screen.getByRole("switch", { name: /allow native apps/i }));
  expect(state().auth_mode).toBe("sso-with-bypass");
  expect(state().bypass_rules).toHaveLength(1);
  expect(screen.getByRole("alert")).toHaveTextContent(/exposed to the internet/i);
  fireEvent.click(screen.getByRole("switch", { name: /allow native apps/i }));
  expect(state().auth_mode).toBe("sso");
});
it("open without overlay flips frame_ok", () => {
  render(<Harness />);
  fireEvent.click(screen.getByText("Advanced"));
  fireEvent.click(screen.getByRole("switch", { name: /open without overlay/i }));
  expect(state().frame_ok).toBe(false);
});
it("focus mode line", () => {
  render(<Harness f={{ mount_mode: "cookie-root" }} />);
  expect(screen.getByText("Focus: opens on its own")).toBeInTheDocument();
});
```
- [ ] **Step 2:** FAIL. **Step 3: Implement** — move the Access JSX (lines ~196–241 of `service-form.tsx`) into `AccessSection`, reorganised as above, reusing `Field`, `Section`, `SwitchRow`, `BypassRulesEditor`, `selectCls`, the group chips (`chipCls`/`checkCls` move with it). `RISK` additions:
```ts
  nativeApps: "Jellyfin's own login is exposed to the internet. Requests from its apps skip Styx login; rate limits and bans still apply.",
  passIdentity: "The app receives the signed-in user's name, email and groups. Only turn this on for apps that use them to sign people in.",
```
(Use `preset.name` in place of "Jellyfin" in the rendered text: `RISK.nativeApps.replace("Jellyfin", preset.name)`.) Update `EMPTY` in `service-form.tsx` with `mount_managed: false, pass_identity: false, frame_ok: true`; strip `mount_managed` in `initialState` destructure (server-owned). `withPreset` keeps `auth_mode: "sso"` (native apps are opt-in).
- [ ] **Step 4:** PASS (+ existing form tests) + build; `wc -l` both files < 500.
- [ ] **Step 5: Commit** `feat(ui): service form shows the mount, native-app and identity options`

---

### Task 5: Base-path panel — plan, consent, job stepper, row chip

**Files:**
- Create: `src/components/system/service-mount.tsx`, `src/components/system/mount-consent-dialog.tsx`
- Modify: `src/components/system/services-panel.tsx` (render `ServiceMount` in the edit drawer above the form), `src/components/system/service-row.tsx` (chip)
- Test: `src/components/system/__tests__/service-mount.test.tsx`

**Interfaces:**
- Consumes: `api.mountPlan/mountApply/mountLatest`, `Stepper`, `ConfirmDialog`-style `Dialog` from `@/components/ui/dialog`.
- Produces: `ServiceMount({ service }: { service: ProxiedService })`; `MountConsentDialog({ open, appName, changes, backupHint, onConfirm, onCancel })`; query keys `["mount-plan", id]`, `["mount-job", id]`.

Behaviour:
- Only for `kind === "docker-local"` and `mount_mode === "path"`.
- `useQuery(["mount-plan", id], () => api.mountPlan(id))`. `useQuery(["mount-job", id], () => api.mountLatest(id).catch(e => e.status === 404 ? null : Promise.reject(e)), { refetchInterval: (q) => ["pending","running"].includes(q.state.data?.state ?? "") ? 1000 : false })`.
- States:
  - plan.method null → muted text `plan.reason` + the preset hint; no button.
  - plan.changes empty → Obol-ringed line "Base path is set to /<slug>" (verified state).
  - plan.changes non-empty, no running job → button **Set base path to /<slug>**; if `needs_consent` opens the consent dialog, else applies directly.
  - job running → `<Stepper steps={job.steps} />`.
  - job `done` → Stepper + Obol "Base path set. <name> answers at /<slug>." 
  - job `rolled_back` → Stepper, Ember text "Couldn't switch <name> to /<slug>, so Styx put its settings back." + `<details>` "App log" with `log_excerpt` in `<pre>`; buttons **Try again** and **Use focus mode instead** (calls `api.updateService(id, {...service, mount_mode: "cookie-root"})`, then invalidates services).
  - job `failed` → Ember "The change failed and Styx couldn't put the old settings back. Your backup is in <backup_dir>." + **Try again**.
- Consent dialog: title "Change <name>'s settings?"; body "Styx didn't create this container, so it asks first."; table (File, Setting, Now, After) from `changes`, `old ?? "(not set)"`; line "Styx backs up the file first and restores it if <name> doesn't come back."; line "<name> restarts (about 30 seconds)."; buttons **Restart <name> and apply** (primary) / **Cancel**.
- Row chip (`service-row.tsx`): reads the same `["mount-job", id]` query only when the drawer isn't open — simplest: `ServiceRow` gets an optional `lastMount?: MountJob["state"]` prop that `services-panel` fills from `queryClient.getQueryData(["mount-job", id])`; chip text: done → "Base path set" (Obol), rolled_back → "Rolled back" (Ember), failed → "Needs attention" (Ember).

- [ ] **Step 1: Failing tests** (mock `@/api/client` with `vi.mock`, wrap in a fresh `QueryClientProvider`)

```tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";
import { api } from "@/api/client";
import { ServiceMount } from "../service-mount";
vi.mock("@/api/client", async (o) => ({ ...(await o<object>()), api: {
  mountPlan: vi.fn(), mountApply: vi.fn(), mountLatest: vi.fn(), updateService: vi.fn() } }));
const svc = { id: "s1", slug: "sonarr", name: "Sonarr", kind: "docker-local", mount_mode: "path" } as never;
const wrap = (ui: React.ReactNode) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{ui}</QueryClientProvider>);
const CH = [{ target: "/config/config.xml", key: "/Config/UrlBase", old: "", new: "/sonarr" }];
const notFound = Object.assign(new Error("nf"), { status: 404 });

it("adopted container asks for consent with the change table", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: true, reason: null });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  vi.mocked(api.mountApply).mockResolvedValue({ job_id: "j" });
  wrap(<ServiceMount service={svc} />);
  fireEvent.click(await screen.findByRole("button", { name: "Set base path to /sonarr" }));
  expect(await screen.findByRole("dialog", { name: "Change Sonarr's settings?" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "/sonarr" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Restart Sonarr and apply" }));
  await waitFor(() => expect(api.mountApply).toHaveBeenCalledWith("s1", true));
});

it("rollback shows reason, log and both recoveries", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: "config_file", changes: CH, needs_consent: false, reason: null });
  vi.mocked(api.mountLatest).mockResolvedValue({ id: "j", state: "rolled_back", changes: CH, backup_dir: "/b",
    log_excerpt: "boom", created_at: "", finished_at: "", steps: [{ id: "verify", label: "Check it answers", state: "failed", detail: "No answer" }] });
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByText(/Styx put its settings back/)).toBeInTheDocument();
  expect(screen.getByText("boom")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Use focus mode instead" })).toBeInTheDocument();
});

it("no job yet (404) shows the plan, not an error", async () => {
  vi.mocked(api.mountPlan).mockResolvedValue({ method: null, changes: [], needs_consent: true, reason: "Styx can't find Sonarr's settings file in the container." });
  vi.mocked(api.mountLatest).mockRejectedValue(notFound);
  wrap(<ServiceMount service={svc} />);
  expect(await screen.findByText(/can't find Sonarr's settings file/)).toBeInTheDocument();
  expect(screen.queryByRole("alert")).toBeNull();
});
```
- [ ] **Step 2:** FAIL. **Step 3:** implement per Behaviour (each file < 200 lines; Dialog from `@/components/ui/dialog`, table as plain `<table>` with `<th scope="col">`). Apply mutation: `useMutation({ mutationFn: (consent) => api.mountApply(id, consent), onSuccess: () => qc.invalidateQueries({ queryKey: ["mount-job", id] }) })`; on 409 show `toast.error(err.message)` (sonner, as elsewhere).
- [ ] **Step 4:** PASS + build. Manually check the drawer at 390 px (table scrolls inside `overflow-x-auto`).
- [ ] **Step 5: Commit** `feat(ui): base-path panel with consent, live steps and rollback recovery`

---

### Task 6: Home tiles — shell links and focus state

**Files:**
- Modify: `src/components/instances/service-list.tsx`
- Test: `src/components/instances/__tests__/service-list.test.tsx` (create or extend)

Behaviour:
- Tiles are `<a href={shellHref(t)}>` for both modes (focus no longer calls `enterService`; the backend sets the cookie at `/_styx/open`).
- Focus tiles show a second line "Opens on its own" (muted, `text-xs`).
- `useQuery(["service-focus"], api.serviceFocus, { refetchOnWindowFocus: true })`; the tile whose slug matches gets `ring-2 ring-obol` and an **Exit** link (`/_styx/exit?next=/`) beside it (separate focusable element, not nested in the anchor).
- Keep the admin tip and the 30 s poll.

- [ ] **Step 1: Failing test**

```tsx
// mock api.listServiceTiles → [{slug:"sonarr",mount_mode:"path",frame_ok:true,...},{slug:"immich",mount_mode:"cookie-root",frame_ok:true,...}]
// mock api.serviceFocus → {slug:"immich"}
it("links into the shell and marks the focused app", async () => {
  renderList();
  expect(await screen.findByRole("link", { name: /sonarr/i })).toHaveAttribute("href", "/_styx/app/sonarr/");
  expect(screen.getByRole("link", { name: /immich/i })).toHaveAttribute("href", "/_styx/open/immich");
  expect(screen.getByText("Opens on its own")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Exit Immich" })).toHaveAttribute("href", "/_styx/exit?next=/");
});
```
(Write `renderList()` with `vi.mock("@/api/client")`, a `QueryClientProvider`, and the `useAuth` mock pattern used by other instance tests.)
- [ ] **Step 2–4:** FAIL → implement → PASS + build.
- [ ] **Step 5: Commit** `feat(ui): home tiles open the Styx shell and show the focused app`

---

### Task 7: Shell build and serving

**Files:**
- Create: `shell.html`, `vite.shell.config.ts`, `src/shell/main.tsx`, `src/shell/shell-app.tsx` (placeholder render of the slug)
- Modify: `package.json` (`build`), `nginx.conf`, `tsconfig.app.json` (include `src/shell` if includes are explicit)

- [ ] **Step 1:** `vite.shell.config.ts`
```ts
import { defineConfig, mergeConfig } from "vite";
import base from "./vite.config";

// Shell lives under /_styx/app/ because /assets/* belongs to a focused app (spec §6.1).
export default mergeConfig(base, defineConfig({
  base: "/_styx/app/",
  build: { outDir: "dist/_styx/app", emptyOutDir: true, rollupOptions: { input: "shell.html" } },
}));
```
`shell.html`: copy `index.html`, set `<title>Styx</title>`, script `src="/src/shell/main.tsx"`.
`src/shell/main.tsx`: imports font + `@/styles/globals.css`, renders `<QueryClientProvider><ShellApp/></QueryClientProvider>`, applies dark class the same way `src/main.tsx` does (reuse its theme helper; if inline, extract to `src/lib/theme.ts` and import from both).
`package.json`: `"build": "tsc -b && vite build && vite build -c vite.shell.config.ts"`. Ensure the main build doesn't wipe `dist/_styx` (main runs first with `emptyOutDir` default true, shell second — order matters; keep it).
- [ ] **Step 2:** `nginx.conf` — add before `location /`:
```nginx
    location /_styx/app/assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        add_header X-Content-Type-Options "nosniff" always;
        try_files $uri =404;
    }
    location /_styx/app/ {
        add_header Cache-Control "no-cache";
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-Frame-Options "DENY" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        add_header Content-Security-Policy "default-src 'self'; img-src 'self' data: blob: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'" always;
        try_files /_styx/app/shell.html =404;
    }
```
- [ ] **Step 3:** `npm run build && ls dist/_styx/app/shell.html dist/_styx/app/assets` exist; `docker build -t styx-frontend-test frontend` succeeds; `docker run --rm -d -p 13000:3000 --name sfx styx-frontend-test && curl -s localhost:13000/_styx/app/sonarr/ | grep -q '/_styx/app/assets/' && docker rm -f sfx`.
- [ ] **Step 4: Commit** `build(ui): second Vite entry for the Styx shell served at /_styx/app/`

---

### Task 8: Shell frame — URL mapping, sync, blocked fallback, SW cleanup

**Files:**
- Create: `src/shell/url.ts`, `src/shell/use-frame-sync.ts`, `src/shell/frame.tsx`, `src/shell/__tests__/url.test.ts`, `src/shell/__tests__/frame.test.tsx`
- Modify: `src/shell/shell-app.tsx`

**Interfaces:**
- Produces:
  - `parseShellPath(pathname: string, search: string, hash: string) → { slug: string; inner: string } | null` (inner always starts with `/`; invalid inner → `/`).
  - `frameSrc(mode: "path" | "cookie-root", slug: string, inner: string) → string`.
  - `shellPathFor(mode, slug, loc: { pathname: string; search: string; hash: string }) → string | null` (null = frame left the app).
  - `isFrameBlocked(frame: { contentWindow: { location: { href: string } } | null }) → boolean`.
  - `Frame({ tile, inner, onTitle })`.

- [ ] **Step 1: Failing tests** `url.test.ts`

```ts
import { describe, expect, it } from "vitest";
import { frameSrc, isFrameBlocked, parseShellPath, shellPathFor } from "../url";
describe("parseShellPath", () => {
  it("splits slug and inner", () =>
    expect(parseShellPath("/_styx/app/sonarr/series/1", "?q=1", "#x")).toEqual({ slug: "sonarr", inner: "/series/1?q=1#x" }));
  it("root", () => expect(parseShellPath("/_styx/app/sonarr/", "", "")).toEqual({ slug: "sonarr", inner: "/" }));
  it.each(["/_styx/app/sonarr//evil.example", "/_styx/app/sonarr/%2e%2e/api", "/_styx/app/sonarr/a/../../x"])(
    "unsafe inner %s falls back to /", (p) => expect(parseShellPath(p, "", "")?.inner).toBe("/"));
  it("rejects a bad slug", () => expect(parseShellPath("/_styx/app/..%2f/", "", "")).toBeNull());
});
it("frameSrc", () => {
  expect(frameSrc("path", "sonarr", "/series")).toBe("/sonarr/series");
  expect(frameSrc("cookie-root", "immich", "/photos")).toBe("/photos");
});
describe("shellPathFor", () => {
  it("path app inside its prefix", () =>
    expect(shellPathFor("path", "sonarr", { pathname: "/sonarr/series", search: "", hash: "" })).toBe("/_styx/app/sonarr/series"));
  it("path app leaving its prefix", () =>
    expect(shellPathFor("path", "sonarr", { pathname: "/radarr/", search: "", hash: "" })).toBeNull());
  it("focus app anywhere except Styx paths", () => {
    expect(shellPathFor("cookie-root", "immich", { pathname: "/photos", search: "?a=1", hash: "" })).toBe("/_styx/app/immich/photos?a=1");
    expect(shellPathFor("cookie-root", "immich", { pathname: "/_styx/exit", search: "", hash: "" })).toBeNull();
  });
});
it("isFrameBlocked", () => {
  expect(isFrameBlocked({ contentWindow: { location: { href: "about:blank" } } })).toBe(true);
  expect(isFrameBlocked({ contentWindow: { get location(): never { throw new DOMException("x", "SecurityError"); } } } as never)).toBe(true);
  expect(isFrameBlocked({ contentWindow: { location: { href: "https://h/sonarr/" } } })).toBe(false);
});
```
- [ ] **Step 2:** FAIL. **Step 3: Implement** `src/shell/url.ts`

```ts
const SLUG = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const PREFIX = "/_styx/app/";

function safeInner(p: string): string {
  let decoded: string;
  try { decoded = decodeURIComponent(p); } catch { return "/"; }
  if (!p.startsWith("/") || p.startsWith("//") || /%(2e|2f|5c)/i.test(p) || decoded.includes("\\")
      || decoded.split("/").includes("..")) return "/";
  return p;
}

export function parseShellPath(pathname: string, search: string, hash: string) {
  if (!pathname.startsWith(PREFIX)) return null;
  const rest = pathname.slice(PREFIX.length);
  const slug = rest.split("/", 1)[0];
  if (!SLUG.test(slug)) return null;
  const raw = rest.slice(slug.length) || "/";
  const path = safeInner(raw);
  return { slug, inner: path === raw ? path + search + hash : "/" };   // unsafe path → app root, drop query
}
```

```ts
export const frameSrc = (mode: "path" | "cookie-root", slug: string, inner: string) =>
  mode === "path" ? `/${slug}${inner}` : inner;

export function shellPathFor(mode: "path" | "cookie-root", slug: string,
                             loc: { pathname: string; search: string; hash: string }): string | null {
  let p = loc.pathname;
  if (mode === "path") {
    if (p !== `/${slug}` && !p.startsWith(`/${slug}/`)) return null;
    p = p.slice(slug.length + 1) || "/";
  } else if (p.startsWith("/_styx/") || p.startsWith("/api/") || p === "/login") {
    return null;
  }
  return `${PREFIX}${slug}${p}${loc.search}${loc.hash}`;
}

export function isFrameBlocked(frame: { contentWindow: { location: { href: string } } | null }): boolean {
  try { return !frame.contentWindow || frame.contentWindow.location.href === "about:blank"; }
  catch { return true; }
}
```
`use-frame-sync.ts` (hook, `ref: RefObject<HTMLIFrameElement>`, `tile`, `onLeave(href)`, `onTitle(t)`): on frame `load` → if blocked set `blocked=true`; else attach to `contentWindow`: wrap `history.pushState`/`replaceState` (call original, then `sync()`), add `popstate` + `hashchange` listeners; `sync()` = `const p = shellPathFor(mode, slug, cw.location); p ? window.history.replaceState(null, "", p) : onLeave(cw.location.href)`; `onTitle(cw.document.title)`. Detach on next load/unmount.
`frame.tsx`: before first render for `cookie-root` tiles, `await navigator.serviceWorker?.getRegistrations()` and `unregister()` those whose `scope === location.origin + "/"` (try/catch; then render). `<iframe title={tile.name} src={frameSrc(...)} className="h-full w-full border-0" allow="fullscreen; clipboard-read; clipboard-write; autoplay; picture-in-picture; encrypted-media" />`. Blocked → centred card (styx tokens): h1 "<name> can't run inside Styx", p "This app blocks being shown inside another page.", primary link **Open <name> on its own** (`frameSrc` URL, `target="_top"`).
`onLeave(href)` → `window.location.assign(href)` (top-level).
`shell-app.tsx`: parse `location`; unknown slug (not in tiles) → card "This app isn't available" + Home link; renders `<Frame>` full-viewport (`h-dvh w-screen`), sets `document.title`.
- `frame.test.tsx`: render `Frame` with a tile and fire `load` on the iframe after stubbing `contentWindow` getter to throw → expect the "can't run inside Styx" heading and a link with `href="/sonarr/"`.
- [ ] **Step 4:** PASS + build. **Step 5: Commit** `feat(shell): same-origin frame with URL sync, safe inner paths and blocked-frame fallback`

---

### Task 9: The ferry — edge tab, dock, hotkey

**Files:**
- Create: `src/shell/edge-tab.tsx`, `src/shell/dock.tsx`, `src/shell/use-hotkey.ts`, `src/shell/ferry-pos.ts`, `src/shell/__tests__/ferry.test.tsx`
- Modify: `src/shell/shell-app.tsx`

**Interfaces:**
- Produces: `readPos() → { side: "left" | "right"; y: number }` (y = fraction 0–1, default `{right, .5}`, never throws), `writePos(p)`, `snapSide(x: number, width: number) → "left" | "right"`; `useHotkey(targets: () => (Window | null)[], onToggle)`; `EdgeTab({ onOpen })`; `Dock({ open, onOpenChange, tiles, current, focusSlug })`.

Design (spec §6.3, frontend-design):
- Edge tab: `m.button` 44×44 hit area, visible pill 10×56 px in Current with a 1px Mist/20 % inner line, `aria-label="Open the Styx menu (Alt+Shift+S)"`. `drag` with `dragConstraints` = viewport ref, `dragElastic: 0.1`, `dragMomentum: false`; `onDragEnd` → `snapSide(point.x, innerWidth)`, `y = point.y / innerHeight` clamped .1–.9, `writePos`, animate to the edge. Idle 3 s → `opacity .35`; pointer enter/focus/touch → 1.
- Dock: Radix `Dialog` (from `radix-ui`, same import as `components/ui/dialog.tsx`) for focus trap + Esc + `aria-modal`; `DialogTitle` "Styx" (visually hidden ok), `DialogDescription` "Switch apps or go back to Styx". Content is a side panel (anchored to the tab's side), width `min(22rem, 100vw - 32px)`, full height on phones (`<640px` → bottom sheet, `max-h-[80dvh]`, rounded top). Glass: dark `bg-[#0F1C22]/72 backdrop-blur-xl border-white/10`; light `bg-[#EDF1EF]/80 backdrop-blur-xl border-[#0F1C22]/12` (use token CSS vars via `color-mix` if cleaner).
- Contents: app list (icon, name, health dot via `HEALTH`), each a link `shellHref(tile)` (`target="_top"`); current app has `aria-current="page"` and `ring-2 ring-obol`; empty → "No apps yet" text. Footer actions: **Home** (`/_styx/exit?next=/`, top), **Pop out** (current bare URL `frameSrc`, `target="_blank" rel="noopener"`), **Exit focus** (only when `focusSlug === current`, `/_styx/exit?next=/`).
- Motion (the one moment): panel slides from its edge (`x: ±24 → 0`, opacity 0→1, spring from `@/lib/motion`), icons settle in sequence along a shallow arc: each item `initial={{ x: side * 12, opacity: 0 }}` animating to `x: side * (k * (i - mid)²)` with `k = 0.6`px, `staggerChildren .025`. Wrap shell root in `<LazyMotion features={domAnimation}><MotionConfig reducedMotion="user">` and use `m.*` components.
- Hotkey: `useHotkey(() => [window, frameRef.current?.contentWindow ?? null], toggle)` — attaches `keydown` to each target (re-run on frame load), matches `e.altKey && e.shiftKey && e.code === "KeyS"`, `preventDefault()`.

- [ ] **Step 1: Failing tests** `ferry.test.tsx`

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { readPos, snapSide, writePos } from "../ferry-pos";
import { Dock } from "../dock";
import { useHotkey } from "../use-hotkey";

it("snapSide", () => { expect(snapSide(100, 1000)).toBe("left"); expect(snapSide(700, 1000)).toBe("right"); });
it("readPos survives a throwing storage", () => {
  const spy = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
  expect(readPos()).toEqual({ side: "right", y: 0.5 });
  spy.mockRestore();
});
it("writePos/readPos roundtrip", () => { writePos({ side: "left", y: 0.3 }); expect(readPos()).toEqual({ side: "left", y: 0.3 }); });

const tiles = [
  { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path" as const, enabled: true, up: true, frame_ok: true },
  { id: "2", slug: "immich", name: "Immich", icon: null, mount_mode: "cookie-root" as const, enabled: true, up: null, frame_ok: true },
];
it("lists apps, marks the current one, focus exit only for focus app", () => {
  render(<Dock open onOpenChange={() => {}} tiles={tiles} current="immich" focusSlug="immich" side="right" />);
  expect(screen.getByRole("link", { name: /immich/i })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: /sonarr/i })).toHaveAttribute("href", "/_styx/app/sonarr/");
  expect(screen.getByRole("link", { name: "Exit focus" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/_styx/exit?next=/");
});
it("empty dock says so", () => {
  render(<Dock open onOpenChange={() => {}} tiles={[]} current="x" focusSlug={null} side="right" />);
  expect(screen.getByText("No apps yet")).toBeInTheDocument();
});
it("Esc closes", () => {
  const close = vi.fn();
  render(<Dock open onOpenChange={close} tiles={tiles} current="sonarr" focusSlug={null} side="right" />);
  fireEvent.keyDown(screen.getByRole("dialog"), { key: "Escape" });
  expect(close).toHaveBeenCalledWith(false);
});
it("Alt+Shift+S toggles", () => {
  const toggle = vi.fn();
  function H() { useHotkey(() => [window], toggle); return null; }
  render(<H />);
  fireEvent.keyDown(window, { code: "KeyS", altKey: true, shiftKey: true });
  fireEvent.keyDown(window, { code: "KeyS", altKey: true });
  expect(toggle).toHaveBeenCalledTimes(1);
});
```
(`Dock` takes `side` too — add it to the Interfaces line when implementing.)
- [ ] **Step 2:** FAIL. **Step 3:** implement per Design. `ferry-pos.ts`:
```ts
const KEY = "styx.ferry";
export type FerryPos = { side: "left" | "right"; y: number };
const DEFAULT: FerryPos = { side: "right", y: 0.5 };
export const snapSide = (x: number, width: number): FerryPos["side"] => (x < width / 2 ? "left" : "right");
export function readPos(): FerryPos {
  try {
    const p = JSON.parse(localStorage.getItem(KEY) ?? "null");
    if (p && (p.side === "left" || p.side === "right") && typeof p.y === "number") return { side: p.side, y: Math.min(0.9, Math.max(0.1, p.y)) };
  } catch { /* private mode / bad JSON */ }
  return DEFAULT;
}
export function writePos(p: FerryPos) { try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* ignore */ } }
```
`shell-app.tsx` wires: tiles from `useQuery(["service-tiles"], api.listServiceTiles)` mapped with `toTile`, focus from `useQuery(["service-focus"], api.serviceFocus)`, `<Frame>`, `<EdgeTab>`, `<Dock>`.
- [ ] **Step 4:** PASS + build. **Step 5: Commit** `feat(shell): the ferry dock with draggable edge tab and Alt+Shift+S`

---

### Task 10: Polish pass (frontend-design self-critique)

- [ ] `docker compose -p styx-e2e` stack from the e2e plan (or `npm run dev` + backend) → screenshot with Playwright at 1440×900 and 390×844, light and dark: login, home (tiles incl. focused), services admin (drawer with consent, stepper running, rolled back), shell with Sonarr + dock open, blocked-frame card.
- [ ] Critique against Global Constraints: only one animated moment; Obol only on active/verified; no all-caps, no `→`, no middle-dot meta; type scale consistent; focus rings visible on every control; 44 px targets in the shell; nothing overflows at 360 px. Remove one decorative element if anything competes with the dock.
- [ ] `npm test`, `npm run build`, `wc -l` (< 500 each).
- [ ] Commit `style(ui): polish identity, drawer and shell after review`
