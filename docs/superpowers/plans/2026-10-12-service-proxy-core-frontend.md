# Service Proxy Core (SP1) — Frontend + Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Admin UI to add/configure proxied services and groups, a Services tile section on the home page, and docs that spell out every security trade-off.

**Architecture:** Plain `useState`/`useEffect` + `api` client calls (same style as `workstations-panel.tsx`), native `<select>` elements, existing `ui/` primitives. Risk messaging lives in one `RiskCallout` component reused everywhere. Backend contract comes from `2026-10-12-service-proxy-core-backend.md`.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind 4, lucide-react, sonner, vitest + testing-library. Zensical docs.

**Spec:** `docs/superpowers/specs/2026-10-12-service-proxy-core-design.md` (§9, §10). Backend plan must be complete first.

## Global Constraints

- Every risky setting shows the exact callout text from spec §9 (reproduced in Task 3). Do not soften the wording.
- Frontend gate is `cd frontend && npm run build` (tsc -b) and `npm test`. Both must pass before every commit.
- Files under 500 lines: the services admin panel is split into `services-panel.tsx` (list) and `service-form.tsx` (drawer).
- The API wrapper sends `X-Styx-Client: 1` on every request (spec §4.2). This is the single line that keeps the portal working while a cookie-root takeover is active.
- Cookie-root entry is a `POST` through the wrapper (header + CSRF) followed by `window.location.assign("/")`; never a bare navigation to `/api/...`.
- Commits: Conventional Commits, end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Review Focus

1. A service with `allowed_groups` the member is not in must not appear in the tile list — the backend filters, the frontend must not cache an admin's list for a member session (lists are fetched per mount, no shared cache). Test in Task 4.
2. Bypass rule editor with an empty `path_prefix` must disable Save, not submit and bounce on a 422. Test in Task 3.
3. Switching `kind` from `url` to `docker-local` must clear `upstream_url` so the backend's cross-check passes. Test in Task 3.
4. Unhealthy tile remains clickable (spec §7). Test in Task 4.
5. Deleting a group that services still reference by name leaves the service's `allowed_groups` dangling, which locks everyone but admins out. The groups panel warns before delete with the list of affected services. Test in Task 2.

---

### Task 1: API client types and methods

**Files:**
- Modify: `frontend/src/api/client.ts` (types at top, header in `request`, methods on `api`)
- Test: `frontend/src/api/services-client.test.ts`

**Interfaces:**
- Produces types `ProxiedService`, `ServicePreset`, `BypassRule`, `DiscoveredContainer`, `Group`, `ProxiedServiceInput`; methods `api.listServices`, `api.listServicePresets`, `api.discoverContainers`, `api.createService`, `api.updateService`, `api.deleteService`, `api.setServiceEnabled`, `api.enterService`, `api.listGroups`, `api.createGroup`, `api.deleteGroup`, `api.getUserGroups`, `api.setUserGroups`.

- [ ] **Step 1: Write failing test**

```ts
// frontend/src/api/services-client.test.ts
import { describe, test, expect, vi, beforeEach } from "vitest";
import { api } from "./client";

describe("services api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  test("every request carries X-Styx-Client", async () => {
    await api.listServices();
    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect((init as RequestInit).headers).toMatchObject({ "X-Styx-Client": "1" });
  });

  test("enterService posts", async () => {
    await api.enterService("unraid");
    const [url, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/api/services/unraid/enter");
    expect((init as RequestInit).method).toBe("POST");
  });
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd frontend && npx vitest run src/api/services-client.test.ts`
Expected: FAIL (`api.listServices is not a function`).

- [ ] **Step 3: Implement**

At the top of `client.ts`, after the `Workstation` type, add:

```ts
export type BypassRule = { path_prefix: string; required_header: string | null };
export type ProxiedService = {
  id: string; slug: string; name: string; icon: string | null;
  kind: "url" | "docker-local";
  upstream_url: string | null; container: string | null; container_port: number | null;
  upstream_fallback: string | null;
  mount_mode: "path" | "cookie-root";
  auth_mode: "sso" | "sso-with-bypass" | "app-native";
  bypass_rules: BypassRule[]; allowed_groups: string[];
  verify_tls: boolean; health_path: string | null;
  health_status: "healthy" | "unhealthy" | "unknown"; health_checked_at: string | null;
  preset_id: string | null; enabled: boolean; created_at: string; updated_at: string;
};
export type ProxiedServiceInput = Omit<ProxiedService,
  "id" | "upstream_fallback" | "health_status" | "health_checked_at" | "created_at" | "updated_at">;
export type ServicePreset = {
  id: string; name: string; icon: string | null; default_port: number | null;
  mount_mode: ProxiedService["mount_mode"]; auth_mode: ProxiedService["auth_mode"];
  bypass_rules: BypassRule[]; health_path: string | null; verify_tls: boolean;
  base_url_hint: string | null; warnings: string[];
};
export type DiscoveredContainer = {
  name: string; image: string; ports: number[]; networks: string[]; suggested_preset: string | null;
};
export type Group = { id: string; name: string; description: string | null; member_count: number };
```

In `request()`, change the headers initialiser to:

```ts
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Styx-Client": "1",
    ...(init?.headers as Record<string, string>),
  };
```

On the `api` object add:

```ts
  listServices: () => request<ProxiedService[]>("/services"),
  listServicePresets: () => request<ServicePreset[]>("/services/presets"),
  discoverContainers: () => request<DiscoveredContainer[]>("/services/discover"),
  createService: (data: ProxiedServiceInput) =>
    request<ProxiedService>("/services", { method: "POST", body: JSON.stringify(data) }),
  updateService: (id: string, data: Omit<ProxiedServiceInput, "slug">) =>
    request<ProxiedService>(`/services/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  deleteService: (id: string) => request<void>(`/services/${id}`, { method: "DELETE" }),
  setServiceEnabled: (id: string, enabled: boolean) =>
    request<ProxiedService>(`/services/${id}/${enabled ? "enable" : "disable"}`, { method: "POST" }),
  enterService: (slug: string) => request<void>(`/services/${slug}/enter`, { method: "POST" }),
  listGroups: () => request<Group[]>("/groups"),
  createGroup: (data: { name: string; description?: string | null }) =>
    request<Group>("/groups", { method: "POST", body: JSON.stringify(data) }),
  deleteGroup: (id: string) => request<void>(`/groups/${id}`, { method: "DELETE" }),
  getUserGroups: (userId: string) => request<string[]>(`/users/${userId}/groups`),
  setUserGroups: (userId: string, groupIds: string[]) =>
    request<string[]>(`/users/${userId}/groups`, { method: "PUT", body: JSON.stringify({ group_ids: groupIds }) }),
```

`request` returns `undefined` for 204 and `res.json()` otherwise; `enterService` returns 200 with an empty body, so change the end of `request` to tolerate it:

```ts
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
```

- [ ] **Step 4: Run test + build, expect PASS**

Run: `cd frontend && npx vitest run src/api/services-client.test.ts && npm run build`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/api/services-client.test.ts
git commit -m "feat(web): services and groups api client, X-Styx-Client header"
```

---

### Task 2: Groups panel and per-user group picker

**Files:**
- Create: `frontend/src/components/system/groups-panel.tsx`
- Modify: `frontend/src/components/system/users-panel.tsx` (add a "Groups" action per user that opens `UserGroupsDialog`)
- Create: `frontend/src/components/system/user-groups-dialog.tsx`
- Modify: `frontend/src/components/settings/nav-config.tsx` (new section `groups` under administration)
- Test: `frontend/src/components/system/__tests__/groups-panel.test.tsx`

**Interfaces:**
- Consumes: `api.listGroups`, `api.createGroup`, `api.deleteGroup`, `api.getUserGroups`, `api.setUserGroups`, `api.listServices`.
- Produces: `export function GroupsPanel()`, `export function UserGroupsDialog({ userId, username, open, onOpenChange })`.

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/system/__tests__/groups-panel.test.tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";

const listGroups = vi.fn(async () => [{ id: "g1", name: "media", description: null, member_count: 2 }]);
const listServices = vi.fn(async () => [
  { id: "s1", slug: "jellyfin", name: "Jellyfin", allowed_groups: ["media"], enabled: true },
]);
const deleteGroup = vi.fn(async () => undefined);
vi.mock("@/api/client", () => ({
  api: { listGroups: (...a: unknown[]) => listGroups(...a), listServices: (...a: unknown[]) => listServices(...a),
         deleteGroup: (...a: unknown[]) => deleteGroup(...a), createGroup: vi.fn() },
  ApiError: class extends Error {},
}));

import { GroupsPanel } from "../groups-panel";

describe("GroupsPanel", () => {
  test("lists groups and warns about services on delete", async () => {
    render(<GroupsPanel />);
    await waitFor(() => expect(screen.getByText("media")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /delete media/i }));
    await waitFor(() => expect(screen.getByText(/Jellyfin/)).toBeInTheDocument());
    expect(screen.getByText(/only admins will be able to open/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect failure** — `npx vitest run src/components/system/__tests__/groups-panel.test.tsx`

- [ ] **Step 3: Implement `groups-panel.tsx`**

```tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Trash2, Users } from "lucide-react";
import { api, ApiError, type Group, type ProxiedService } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/common/confirm-dialog";

export function GroupsPanel() {
  const [groups, setGroups] = useState<Group[]>([]);
  const [services, setServices] = useState<ProxiedService[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [pending, setPending] = useState<Group | null>(null);

  const load = async () => {
    const [g, s] = await Promise.all([api.listGroups(), api.listServices()]);
    setGroups(g); setServices(s);
  };
  useEffect(() => { void load(); }, []);

  const create = async () => {
    try {
      await api.createGroup({ name: name.trim(), description: desc.trim() || null });
      setName(""); setDesc(""); await load();
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Failed to create group"); }
  };
  const affected = pending ? services.filter((s) => s.allowed_groups.includes(pending.name)) : [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2"><Users className="h-4 w-4" /> Groups</CardTitle>
        <CardDescription>Groups control which users may open a proxied service.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void create(); }}>
          <Input placeholder="name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="description (optional)" value={desc} onChange={(e) => setDesc(e.target.value)} />
          <Button type="submit" disabled={!name.trim()}>Add</Button>
        </form>
        <ul className="divide-y">
          {groups.map((g) => (
            <li key={g.id} className="flex items-center justify-between py-2">
              <div>
                <div className="font-medium">{g.name}</div>
                <div className="text-xs text-muted-foreground">
                  {g.description ?? ""} · {g.member_count} member{g.member_count === 1 ? "" : "s"}
                </div>
              </div>
              <Button variant="ghost" size="sm" aria-label={`Delete ${g.name}`} onClick={() => setPending(g)}>
                <Trash2 className="h-4 w-4" />
              </Button>
            </li>
          ))}
          {groups.length === 0 && <li className="py-2 text-sm text-muted-foreground">No groups yet.</li>}
        </ul>
      </CardContent>
      <ConfirmDialog
        open={pending !== null}
        onOpenChange={(o) => { if (!o) setPending(null); }}
        title={`Delete group ${pending?.name ?? ""}?`}
        description={affected.length
          ? `These services require this group: ${affected.map((s) => s.name).join(", ")}. ` +
            "After deletion only admins will be able to open them until you edit their allowed groups."
          : "Members lose this group immediately."}
        confirmLabel="Delete"
        onConfirm={async () => {
          if (!pending) return;
          await api.deleteGroup(pending.id); setPending(null); await load();
        }}
      />
    </Card>
  );
}
```

Check `ConfirmDialog`'s actual prop names in `components/common/confirm-dialog.tsx` and match them (`title`, `description`, `onConfirm` exist; adjust `confirmLabel` to whatever the component calls it).

- [ ] **Step 4: Implement `user-groups-dialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type Group } from "@/api/client";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function UserGroupsDialog({ userId, username, open, onOpenChange }:
  { userId: string; username: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [groups, setGroups] = useState<Group[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!open) return;
    void Promise.all([api.listGroups(), api.getUserGroups(userId)]).then(([g, mine]) => {
      setGroups(g); setSelected(new Set(mine));
    });
  }, [open, userId]);
  const save = async () => {
    try { await api.setUserGroups(userId, [...selected]); onOpenChange(false); }
    catch { toast.error("Failed to save groups"); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Groups for {username}</DialogTitle>
          <DialogDescription>Services restricted to a group are only visible to its members.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {groups.map((g) => (
            <label key={g.id} className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={selected.has(g.id)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(g.id); else next.delete(g.id);
                  setSelected(next);
                }} />
              {g.name}
            </label>
          ))}
          {groups.length === 0 && <p className="text-sm text-muted-foreground">No groups defined.</p>}
        </div>
        <Button onClick={() => void save()}>Save</Button>
      </DialogContent>
    </Dialog>
  );
}
```

In `users-panel.tsx`, add a `DropdownMenuItem` "Groups…" to each user's menu that sets
`const [groupsFor, setGroupsFor] = useState<{ id: string; username: string } | null>(null);`
and render `<UserGroupsDialog open={groupsFor !== null} userId={groupsFor?.id ?? ""} username={groupsFor?.username ?? ""} onOpenChange={(o) => { if (!o) setGroupsFor(null); }} />` once at the bottom of the panel.

In `nav-config.tsx`, import `GroupsPanel` and `UsersRound` from lucide, then add after the `users` section:

```ts
      { id: "groups", label: "Groups", icon: UsersRound,
        description: "Group users to control who can open proxied services.",
        tooltip: "Create groups and assign members", Component: GroupsPanel },
```

- [ ] **Step 5: Run test + build, expect PASS. Commit**

```bash
git add frontend/src/components/system/groups-panel.tsx frontend/src/components/system/user-groups-dialog.tsx frontend/src/components/system/users-panel.tsx frontend/src/components/settings/nav-config.tsx frontend/src/components/system/__tests__/groups-panel.test.tsx
git commit -m "feat(web): groups admin panel and per-user group picker"
```

---

### Task 3: Services admin panel and form with risk callouts

**Files:**
- Create: `frontend/src/components/common/risk-callout.tsx`
- Create: `frontend/src/components/system/service-form.tsx`
- Create: `frontend/src/components/system/services-panel.tsx`
- Modify: `frontend/src/components/settings/nav-config.tsx`
- Test: `frontend/src/components/system/__tests__/service-form.test.tsx`

**Interfaces:**
- Consumes: Task 1 types/methods.
- Produces: `export function RiskCallout({ children })`, `export const RISK = {...}` (callout copy), `export function ServiceForm({ initial, presets, groups, onSubmit, onCancel })`, `export function ServicesPanel()`.

- [ ] **Step 1: Write failing tests**

```tsx
// frontend/src/components/system/__tests__/service-form.test.tsx
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { ServiceForm } from "../service-form";
import { RISK } from "@/components/common/risk-callout";

const presets = [{ id: "sonarr", name: "Sonarr", icon: null, default_port: 8989, mount_mode: "path",
  auth_mode: "sso-with-bypass", bypass_rules: [{ path_prefix: "/sonarr/api", required_header: "X-Api-Key" }],
  health_path: "/sonarr/ping", verify_tls: true, base_url_hint: "URL Base = /sonarr", warnings: [] }] as const;

function setup(initial?: Parameters<typeof ServiceForm>[0]["initial"]) {
  const onSubmit = vi.fn();
  render(<ServiceForm initial={initial} presets={[...presets]} groups={[]} onSubmit={onSubmit} onCancel={() => {}} />);
  return onSubmit;
}

describe("ServiceForm", () => {
  test("bypass rule callout appears and empty prefix blocks save", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Auth mode"), { target: { value: "sso-with-bypass" } });
    fireEvent.click(screen.getByRole("button", { name: /add bypass rule/i }));
    expect(screen.getByText(RISK.bypass("<prefix>"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeDisabled();
  });

  test("app-native and tls callouts", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Auth mode"), { target: { value: "app-native" } });
    expect(screen.getByText(RISK.appNative)).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Verify upstream TLS"));
    expect(screen.getByText(RISK.tls)).toBeInTheDocument();
  });

  test("switching kind to docker-local clears upstream_url", () => {
    const onSubmit = setup();
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "x" } });
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "X" } });
    fireEvent.change(screen.getByLabelText("Upstream URL"), { target: { value: "http://10.0.0.1" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "docker-local" } });
    fireEvent.change(screen.getByLabelText("Container"), { target: { value: "c" } });
    fireEvent.change(screen.getByLabelText("Container port"), { target: { value: "80" } });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ kind: "docker-local", upstream_url: null, container: "c", container_port: 80 });
  });

  test("preset fills fields and shows hint", () => {
    setup();
    fireEvent.change(screen.getByLabelText("Preset"), { target: { value: "sonarr" } });
    expect(screen.getByLabelText("Slug")).toHaveValue("sonarr");
    expect(screen.getByText(/URL Base = \/sonarr/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: `risk-callout.tsx`**

```tsx
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";

export const RISK = {
  bypass: (prefix: string) =>
    `Requests matching ${prefix} are reachable from the internet WITHOUT Styx login. ` +
    "Only the app's own credential and rate limiting protect them.",
  appNative: "Styx does not authenticate this service. The app must enforce its own login.",
  tls: "Upstream certificate is not verified. Traffic between Styx and this host can be intercepted on your LAN.",
  cookieRoot: "Takes over the root of the hostname for this browser. One service at a time. " +
    "Mobile apps cannot use this mode. To leave, open /_styx/exit.",
} as const;

export function RiskCallout({ children }: { children: ReactNode }) {
  return (
    <div role="alert" className="flex gap-2 rounded-md border border-red-500/40 bg-red-500/10 p-2 text-xs text-red-200">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{children} <a className="underline" href="/docs/SERVICES/#security-model" target="_blank" rel="noreferrer">Learn more</a></span>
    </div>
  );
}
```

- [ ] **Step 4: `service-form.tsx`**

```tsx
import { useState } from "react";
import type { BypassRule, Group, ProxiedService, ProxiedServiceInput, ServicePreset } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { RISK, RiskCallout } from "@/components/common/risk-callout";

const EMPTY: ProxiedServiceInput = {
  slug: "", name: "", icon: null, kind: "url", upstream_url: "", container: null, container_port: null,
  mount_mode: "path", auth_mode: "sso", bypass_rules: [], allowed_groups: [], verify_tls: true,
  health_path: null, preset_id: null, enabled: true,
};

type Props = {
  initial?: ProxiedService; presets: ServicePreset[]; groups: Group[];
  discovered?: { name: string; port: number; preset: string | null } | null;
  onSubmit: (data: ProxiedServiceInput) => void | Promise<void>; onCancel: () => void;
};

export function ServiceForm({ initial, presets, groups, discovered, onSubmit, onCancel }: Props) {
  const [f, setF] = useState<ProxiedServiceInput>(() => {
    if (initial) { const { id: _i, upstream_fallback: _u, health_status: _h, health_checked_at: _c,
      created_at: _a, updated_at: _b, ...rest } = initial; return rest; }
    if (discovered) return { ...EMPTY, kind: "docker-local", upstream_url: null, container: discovered.name,
      container_port: discovered.port, slug: discovered.name.toLowerCase().replace(/[^a-z0-9-]/g, "-"),
      name: discovered.name };
    return EMPTY;
  });
  const set = <K extends keyof ProxiedServiceInput>(k: K, v: ProxiedServiceInput[K]) => setF({ ...f, [k]: v });
  const preset = presets.find((p) => p.id === f.preset_id) ?? null;

  const applyPreset = (id: string) => {
    const p = presets.find((x) => x.id === id);
    if (!p) { set("preset_id", null); return; }
    setF({ ...f, preset_id: p.id, slug: f.slug || p.id, name: f.name || p.name, icon: p.icon,
      mount_mode: p.mount_mode, auth_mode: p.auth_mode, bypass_rules: p.bypass_rules,
      health_path: p.health_path, verify_tls: p.verify_tls,
      container_port: f.kind === "docker-local" ? (f.container_port ?? p.default_port) : f.container_port });
  };
  const setKind = (kind: ProxiedServiceInput["kind"]) =>
    setF(kind === "url" ? { ...f, kind, container: null, container_port: null, upstream_url: f.upstream_url ?? "" }
                        : { ...f, kind, upstream_url: null });
  const setRule = (i: number, r: Partial<BypassRule>) =>
    set("bypass_rules", f.bypass_rules.map((x, j) => (j === i ? { ...x, ...r } : x)));

  const valid = f.slug.trim() && f.name.trim()
    && (f.kind === "url" ? !!f.upstream_url?.trim() : !!f.container && !!f.container_port)
    && f.bypass_rules.every((r) => r.path_prefix.startsWith("/"));

  return (
    <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (valid) void onSubmit({ ...f, bypass_rules: f.auth_mode === "sso-with-bypass" ? f.bypass_rules : [] }); }}>
      <div>
        <Label htmlFor="preset">Preset</Label>
        <select id="preset" className="w-full rounded-md border bg-background p-2 text-sm"
          value={f.preset_id ?? ""} onChange={(e) => applyPreset(e.target.value)}>
          <option value="">— none —</option>
          {presets.map((p) => <option key={p.id} value={p.id}>{p.icon ?? ""} {p.name}</option>)}
        </select>
        {preset?.base_url_hint && <p className="mt-1 text-xs text-muted-foreground">App setting: {preset.base_url_hint}</p>}
        {preset?.warnings.map((w) => <RiskCallout key={w}>{w}</RiskCallout>)}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label htmlFor="slug">Slug</Label>
          <Input id="slug" value={f.slug} disabled={!!initial} onChange={(e) => set("slug", e.target.value)} /></div>
        <div><Label htmlFor="name">Name</Label>
          <Input id="name" value={f.name} onChange={(e) => set("name", e.target.value)} /></div>
      </div>
      <div>
        <Label htmlFor="kind">Kind</Label>
        <select id="kind" className="w-full rounded-md border bg-background p-2 text-sm" value={f.kind}
          onChange={(e) => setKind(e.target.value as ProxiedServiceInput["kind"])}>
          <option value="url">URL (any host:port)</option>
          <option value="docker-local">Local docker container</option>
        </select>
      </div>
      {f.kind === "url" ? (
        <div><Label htmlFor="upstream">Upstream URL</Label>
          <Input id="upstream" placeholder="http://192.168.1.10:8989" value={f.upstream_url ?? ""}
            onChange={(e) => set("upstream_url", e.target.value)} /></div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <div><Label htmlFor="container">Container</Label>
            <Input id="container" value={f.container ?? ""} onChange={(e) => set("container", e.target.value)} /></div>
          <div><Label htmlFor="cport">Container port</Label>
            <Input id="cport" type="number" value={f.container_port ?? ""}
              onChange={(e) => set("container_port", e.target.value ? Number(e.target.value) : null)} /></div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label htmlFor="mount">Mount mode</Label>
          <select id="mount" className="w-full rounded-md border bg-background p-2 text-sm" value={f.mount_mode}
            onChange={(e) => set("mount_mode", e.target.value as ProxiedServiceInput["mount_mode"])}>
            <option value="path">Path (/slug, app has base URL)</option>
            <option value="cookie-root">Cookie root (takeover)</option>
          </select>
        </div>
        <div>
          <Label htmlFor="auth">Auth mode</Label>
          <select id="auth" className="w-full rounded-md border bg-background p-2 text-sm" value={f.auth_mode}
            onChange={(e) => set("auth_mode", e.target.value as ProxiedServiceInput["auth_mode"])}>
            <option value="sso">SSO (Styx login required)</option>
            <option value="sso-with-bypass">SSO with bypass rules</option>
            <option value="app-native">App native (no Styx auth)</option>
          </select>
        </div>
      </div>
      {f.mount_mode === "cookie-root" && <RiskCallout>{RISK.cookieRoot}</RiskCallout>}
      {f.auth_mode === "app-native" && <RiskCallout>{RISK.appNative}</RiskCallout>}
      {f.auth_mode === "sso-with-bypass" && (
        <div className="space-y-2">
          {f.bypass_rules.map((r, i) => (
            <div key={i} className="space-y-1">
              <div className="flex gap-2">
                <Input aria-label="Bypass path prefix" placeholder="/slug/api" value={r.path_prefix}
                  onChange={(e) => setRule(i, { path_prefix: e.target.value })} />
                <Input aria-label="Required header" placeholder="X-Api-Key (optional)" value={r.required_header ?? ""}
                  onChange={(e) => setRule(i, { required_header: e.target.value || null })} />
                <Button type="button" variant="ghost" onClick={() => set("bypass_rules", f.bypass_rules.filter((_, j) => j !== i))}>×</Button>
              </div>
              <RiskCallout>{RISK.bypass(r.path_prefix || "<prefix>")}</RiskCallout>
            </div>
          ))}
          <Button type="button" variant="outline" size="sm"
            onClick={() => set("bypass_rules", [...f.bypass_rules, { path_prefix: "", required_header: null }])}>
            Add bypass rule
          </Button>
        </div>
      )}
      <div>
        <Label>Allowed groups (empty = any logged-in user)</Label>
        <div className="flex flex-wrap gap-3 text-sm">
          {groups.map((g) => (
            <label key={g.id} className="flex items-center gap-1">
              <input type="checkbox" checked={f.allowed_groups.includes(g.name)}
                onChange={(e) => set("allowed_groups", e.target.checked
                  ? [...f.allowed_groups, g.name] : f.allowed_groups.filter((n) => n !== g.name))} />
              {g.name}
            </label>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div><Label htmlFor="health">Health path</Label>
          <Input id="health" placeholder="/ping" value={f.health_path ?? ""}
            onChange={(e) => set("health_path", e.target.value || null)} /></div>
        <label className="flex items-center gap-2 self-end text-sm">
          <input type="checkbox" aria-label="Verify upstream TLS" checked={f.verify_tls}
            onChange={(e) => set("verify_tls", e.target.checked)} />
          Verify upstream TLS
        </label>
      </div>
      {!f.verify_tls && <RiskCallout>{RISK.tls}</RiskCallout>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="ghost" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={!valid}>Save</Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: `services-panel.tsx`**

```tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Globe, Plus, RefreshCw } from "lucide-react";
import { api, ApiError, type DiscoveredContainer, type Group, type ProxiedService,
  type ProxiedServiceInput, type ServicePreset } from "@/api/client";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ServiceForm } from "./service-form";

type Editing = { kind: "new" } | { kind: "edit"; svc: ProxiedService }
  | { kind: "discovered"; c: DiscoveredContainer } | null;

export function ServicesPanel() {
  const [services, setServices] = useState<ProxiedService[]>([]);
  const [presets, setPresets] = useState<ServicePreset[]>([]);
  const [groups, setGroups] = useState<Group[]>([]);
  const [discovered, setDiscovered] = useState<DiscoveredContainer[] | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [toDelete, setToDelete] = useState<ProxiedService | null>(null);

  const load = async () => {
    const [s, p, g] = await Promise.all([api.listServices(), api.listServicePresets(), api.listGroups()]);
    setServices(s); setPresets(p); setGroups(g);
  };
  useEffect(() => { void load(); }, []);

  const discover = async () => {
    try { setDiscovered(await api.discoverContainers()); }
    catch (e) { toast.error(e instanceof ApiError ? e.message : "Discovery failed"); }
  };
  const submit = async (data: ProxiedServiceInput) => {
    try {
      if (editing?.kind === "edit") { const { slug: _s, ...rest } = data; await api.updateService(editing.svc.id, rest); }
      else await api.createService(data);
      setEditing(null); await load(); toast.success("Saved");
    } catch (e) { toast.error(e instanceof ApiError ? e.message : "Save failed"); }
  };
  const dot = (s: ProxiedService) => ({ healthy: "bg-emerald-500", unhealthy: "bg-red-500", unknown: "bg-zinc-500" }[s.health_status]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2"><Globe className="h-4 w-4" /> Services</CardTitle>
          <CardDescription>Internal apps proxied through this host. Every service is internet-reachable through Styx.</CardDescription>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => void discover()}><RefreshCw className="mr-1 h-4 w-4" />Add from container</Button>
          <Button size="sm" onClick={() => setEditing({ kind: "new" })}><Plus className="mr-1 h-4 w-4" />Add service</Button>
        </div>
      </CardHeader>
      <CardContent>
        <table className="w-full text-sm">
          <thead className="text-left text-xs text-muted-foreground">
            <tr><th>Name</th><th>Slug</th><th>Mode</th><th>Auth</th><th>Health</th><th>Enabled</th><th /></tr>
          </thead>
          <tbody>
            {services.map((s) => (
              <tr key={s.id} className="border-t">
                <td className="py-2">{s.icon} {s.name}{s.upstream_fallback && <Badge variant="outline" className="ml-2">fallback</Badge>}</td>
                <td>/{s.slug}</td><td>{s.mount_mode}</td>
                <td>{s.auth_mode}{s.bypass_rules.length > 0 && <Badge variant="destructive" className="ml-1">bypass</Badge>}</td>
                <td><span className={`inline-block h-2 w-2 rounded-full ${dot(s)}`} title={s.health_status} /></td>
                <td><input type="checkbox" aria-label={`Enable ${s.name}`} checked={s.enabled}
                  onChange={async (e) => { await api.setServiceEnabled(s.id, e.target.checked); await load(); }} /></td>
                <td className="text-right">
                  <Button variant="ghost" size="sm" onClick={() => setEditing({ kind: "edit", svc: s })}>Edit</Button>
                  <Button variant="ghost" size="sm" onClick={() => setToDelete(s)}>Delete</Button>
                </td>
              </tr>
            ))}
            {services.length === 0 && <tr><td colSpan={7} className="py-4 text-muted-foreground">No services yet.</td></tr>}
          </tbody>
        </table>
      </CardContent>

      <Dialog open={discovered !== null} onOpenChange={(o) => { if (!o) setDiscovered(null); }}>
        <DialogContent>
          <DialogHeader><DialogTitle>Running containers</DialogTitle></DialogHeader>
          <ul className="divide-y text-sm">
            {(discovered ?? []).map((c) => (
              <li key={c.name} className="flex items-center justify-between py-2">
                <div><div className="font-medium">{c.name}</div><div className="text-xs text-muted-foreground">{c.image} · ports {c.ports.join(", ") || "none"}</div></div>
                <Button size="sm" disabled={c.ports.length === 0}
                  onClick={() => { setDiscovered(null); setEditing({ kind: "discovered", c }); }}>Expose</Button>
              </li>
            ))}
            {discovered?.length === 0 && <li className="py-2 text-muted-foreground">No eligible containers.</li>}
          </ul>
        </DialogContent>
      </Dialog>

      <Dialog open={editing !== null} onOpenChange={(o) => { if (!o) setEditing(null); }}>
        <DialogContent className="max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing?.kind === "edit" ? `Edit ${editing.svc.name}` : "Add service"}</DialogTitle></DialogHeader>
          {editing && (
            <ServiceForm
              initial={editing.kind === "edit" ? editing.svc : undefined}
              discovered={editing.kind === "discovered"
                ? { name: editing.c.name, port: editing.c.ports[0], preset: editing.c.suggested_preset } : null}
              presets={presets} groups={groups} onSubmit={submit} onCancel={() => setEditing(null)} />
          )}
        </DialogContent>
      </Dialog>

      <ConfirmDialog open={toDelete !== null} onOpenChange={(o) => { if (!o) setToDelete(null); }}
        title={`Delete ${toDelete?.name ?? ""}?`} description="The route is removed immediately."
        onConfirm={async () => { if (!toDelete) return; await api.deleteService(toDelete.id); setToDelete(null); await load(); }} />
    </Card>
  );
}
```

When `discovered.preset` is set, `ServiceForm` should call `applyPreset(discovered.preset)` once on mount: add `useEffect(() => { if (discovered?.preset) applyPreset(discovered.preset); }, []);` with an eslint-disable comment for exhaustive-deps.

In `nav-config.tsx`, import `ServicesPanel` and `Globe` from lucide, add after `workstations`:

```ts
      { id: "services", label: "Services", icon: Globe,
        description: "Proxy internal apps (Jellyfin, *arr, Nextcloud…) through this host.",
        tooltip: "Add and configure proxied services", Component: ServicesPanel },
```

- [ ] **Step 6: Run tests + build, expect PASS. Commit**

```bash
git add frontend/src/components/common/risk-callout.tsx frontend/src/components/system/service-form.tsx frontend/src/components/system/services-panel.tsx frontend/src/components/settings/nav-config.tsx frontend/src/components/system/__tests__/service-form.test.tsx
git commit -m "feat(web): services admin panel with explicit risk callouts"
```

---

### Task 4: Home page service tiles

**Files:**
- Create: `frontend/src/components/instances/service-list.tsx`
- Modify: `frontend/src/components/instances/instance-workspace.tsx` (render `<ServiceList />` above `<WorkstationList />`)
- Test: `frontend/src/components/instances/__tests__/service-list.test.tsx`

**Interfaces:**
- Consumes: `api.listServices`, `api.enterService`.
- Produces: `export function ServiceList()`.

- [ ] **Step 1: Write failing test**

```tsx
// frontend/src/components/instances/__tests__/service-list.test.tsx
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";

const listServices = vi.fn(async () => [
  { id: "1", slug: "sonarr", name: "Sonarr", icon: "📺", mount_mode: "path", health_status: "unhealthy", enabled: true, bypass_rules: [], allowed_groups: [] },
  { id: "2", slug: "unraid", name: "Unraid", icon: "🟠", mount_mode: "cookie-root", health_status: "healthy", enabled: true, bypass_rules: [], allowed_groups: [] },
]);
const enterService = vi.fn(async () => undefined);
vi.mock("@/api/client", () => ({ api: { listServices: () => listServices(), enterService: (s: string) => enterService(s) } }));

import { ServiceList } from "../service-list";

describe("ServiceList", () => {
  test("path tile opens new tab even when unhealthy; cookie-root tile enters then navigates", async () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign }, writable: true });
    render(<ServiceList />);
    await waitFor(() => expect(screen.getByText("Sonarr")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /open sonarr/i }));
    expect(open).toHaveBeenCalledWith("/sonarr", "_blank", "noopener");
    fireEvent.click(screen.getByRole("button", { name: /open unraid/i }));
    await waitFor(() => expect(enterService).toHaveBeenCalledWith("unraid"));
    expect(assign).toHaveBeenCalledWith("/");
  });

  test("renders nothing when empty", async () => {
    listServices.mockResolvedValueOnce([]);
    const { container } = render(<ServiceList />);
    await waitFor(() => expect(listServices).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement**

```tsx
// frontend/src/components/instances/service-list.tsx
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, type ProxiedService } from "@/api/client";

const DOT = { healthy: "bg-emerald-500", unhealthy: "bg-red-500", unknown: "bg-zinc-500" } as const;

export function ServiceList() {
  const [services, setServices] = useState<ProxiedService[]>([]);
  useEffect(() => {
    let live = true;
    const load = () => api.listServices().then((s) => { if (live) setServices(s.filter((x) => x.enabled)); }).catch(() => {});
    void load();
    const t = setInterval(load, 30_000);
    return () => { live = false; clearInterval(t); };
  }, []);
  if (services.length === 0) return null;

  const open = async (s: ProxiedService) => {
    if (s.mount_mode === "path") { window.open(`/${s.slug}`, "_blank", "noopener"); return; }
    try { await api.enterService(s.slug); window.location.assign("/"); }
    catch { toast.error(`Could not open ${s.name}`); }
  };

  return (
    <section className="mb-3">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Services</h2>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {services.map((s) => (
          <button key={s.id} type="button" aria-label={`Open ${s.name}`} onClick={() => void open(s)}
            title={s.mount_mode === "cookie-root" ? "Takes over this browser tab's host. Return via /_styx/exit" : `/${s.slug}`}
            className="flex items-center gap-2 rounded-md border bg-card p-2 text-left text-sm hover:bg-accent">
            <span className="text-lg">{s.icon ?? "🔗"}</span>
            <span className="flex-1 truncate">{s.name}</span>
            <span className={`h-2 w-2 rounded-full ${DOT[s.health_status]}`} title={s.health_status} />
          </button>
        ))}
      </div>
    </section>
  );
}
```

In `instance-workspace.tsx`: `import { ServiceList } from "./service-list";` and render `<ServiceList />` directly above `<WorkstationList />`.

- [ ] **Step 4: Run tests + build, expect PASS. Commit**

```bash
git add frontend/src/components/instances/service-list.tsx frontend/src/components/instances/instance-workspace.tsx frontend/src/components/instances/__tests__/service-list.test.tsx
git commit -m "feat(web): service tiles on home"
```

---

### Task 5: Documentation

**Files:**
- Create: `docs/SERVICES.md`
- Modify: `docs/PRODUCTION.md` (append bullets under `## Security Posture`)
- Modify: `zensical.toml` (nav entry after Workstations)
- Modify: `CLAUDE.md` (project structure: add `routers/services.py`, `routers/services_auth.py`, `routers/groups.py`, `services/service_routes.py`, `services/service_health.py`, `templates/services/`)

- [ ] **Step 1: Write `docs/SERVICES.md`**

Sections, each 1–3 short paragraphs, no placeholders:

```markdown
# Proxied Services

Styx can proxy any internal HTTP service (Jellyfin, the *arr stack, Nextcloud, GitLab,
Unraid, Audiobookshelf, anything at `ip:port`) through the single Styx hostname.
Admins add services under **Settings → Administration → Services**; users see tiles
on the home page for the services their groups allow.

## One hostname, two mount modes
- **Path** (`https://<host>/<slug>`): the app must be configured with that base URL
  (each preset shows the exact setting). Works in browsers and mobile apps.
- **Cookie root**: for apps with no base-URL support. Clicking the tile sets a routing
  cookie and the app takes over `/` for that browser. One cookie-root service at a time;
  leave via `https://<host>/_styx/exit`. Mobile apps cannot use this mode.

## Auth modes
| mode | who can reach it | use for |
| sso | logged-in Styx users in the allowed groups | browser-only apps |
| sso-with-bypass | as above, plus unauthenticated requests matching a bypass rule | apps with mobile clients / API keys |
| app-native | anyone on the internet; the app enforces its own login | apps with their own SSO |

## Groups
Create groups under Administration → Groups, assign users, then pick allowed groups on a
service. Empty allowed-groups means every logged-in user. Admins can always open everything.

## Discovery
"Add from container" lists running containers on the Styx host. Exposing one attaches it
to the `styx-services` network (shared only with Traefik, never the backend); if that fails
Styx falls back to `host.docker.internal:<port>` and shows a *fallback* badge (the port must
then be published on the host). Health of attached containers shows as unknown.

## Security model
Every service is reachable from the internet through Cloudflare → Traefik → Styx.
- Rate limiting and IP banning apply to every service route.
- Identity headers (`X-Styx-*`, `X-authentik-*`) are stripped from client requests.
- **Bypass rules are the only unauthenticated surface.** A rule = path prefix + optional
  required header name. The header requirement filters scanners; it is not authentication.
  Only the app's own credential protects those requests.
- **app-native** means Styx does no authentication at all for that service.
- **Verify upstream TLS off** means traffic between Styx and that host can be intercepted
  on your LAN. Use it only for self-signed appliances such as Unraid.
- The routing cookie is a selector, not a credential: access is checked on every request.
- Access checks run on `/internal/services/<slug>/auth-check`, a path no Traefik router
  exposes. A valid refresh token keeps service access alive past the 15-minute access token.
- Client IPs (rate limits, bans, audit) come from forwarded headers only when the peer is in
  `TRUSTED_PROXY_CIDRS` (default: loopback + docker bridge pools).
- Deleting a group removes it from every service; a service left with no groups is disabled.
- **Known limitation:** services share the Styx origin, so the browser sends Styx session
  cookies to them. Only proxy apps you trust with Styx sessions.
- All service changes are written to the audit log.
```

- [ ] **Step 2: Append to `docs/PRODUCTION.md` Security Posture**

```markdown
- **Proxied services:** every service route carries rate limiting, IP ban gate, identity-header stripping and a per-request forwardAuth ACL. Bypass rules, app-native mode and disabled TLS verification are explicit admin opt-ins with red warnings in the UI. See [Services](SERVICES.md#security-model).
```

- [ ] **Step 3: Nav + CLAUDE.md**

In `zensical.toml` add `{ "Services" = "SERVICES.md" },` after the Workstations line. In `CLAUDE.md` project structure add the new files with one-line descriptions.

- [ ] **Step 4: Commit**

```bash
git add docs/SERVICES.md docs/PRODUCTION.md zensical.toml CLAUDE.md
git commit -m "docs(services): proxied services guide and security model"
```

---

### Task 6: Full gate

- [ ] **Step 1: Backend** — `cd backend && .venv/bin/python -m pytest -q && .venv/bin/python -m ruff check app tests`
- [ ] **Step 2: Frontend** — `cd frontend && npm run build && npm test`
- [ ] **Step 3: Line counts** — `wc -l frontend/src/components/system/service-form.tsx frontend/src/components/system/services-panel.tsx frontend/src/api/client.ts` each under 500; if `client.ts` crosses 500, move the new types to `frontend/src/lib/types.ts` and re-export.
- [ ] **Step 4: Commit fixes** — `git commit -am "chore(services): gate fixes"`.
- [ ] **Step 5: Hand off** — invoke `superpowers:finishing-a-development-branch`.
