import type { Page, Route } from "@playwright/test";

/** Fulfil matching API calls with canned JSON (the states that are slow or impossible to reach for real). */
export async function mockApi(page: Page, method: string, pathname: RegExp | string, body: unknown, status = 200) {
  await page.route((u) => (typeof pathname === "string" ? u.pathname === pathname : pathname.test(u.pathname)), (route: Route) =>
    route.request().method() === method
      ? route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) })
      : route.fallback());
}

const STEPS = [
  ["backup", "Back up settings"], ["apply", "Apply base path"], ["restart", "Restart app"], ["verify", "Check the app responds"],
] as const;
type StepState = "pending" | "active" | "done" | "failed" | "skipped";
const steps = (states: StepState[], extra: Record<string, object> = {}) =>
  STEPS.map(([id, label], i) => ({ id, label, state: states[i], detail: null, ...extra[id] }));
const job = (state: string, s: ReturnType<typeof steps>, more: object = {}) => ({
  id: "mock-job", state, steps: s, changes: [], backup_dir: "/data/backups/shotsapp/20261013T094107Z",
  changed: false, log_excerpt: null, created_at: "2026-10-13T09:41:00Z", finished_at: "2026-10-13T09:41:30Z", ...more,
});
const PLAN = { method: "config_file", changes: [], needs_consent: false, reason: null };
const LOG = Array.from({ length: 14 }, (_, i) => `[2026-10-13 09:41:${10 + i}] Info: startup step ${i + 1} ok`)
  .concat(["[2026-10-13 09:41:24] Fatal: cannot bind /shotsapp: address already in use"]).join("\n");

/** Mount-section fixtures: plan + latest job for the base-path states. */
export const MOUNT_STATES = {
  done: { plan: PLAN, job: job("done", steps(["done", "done", "done", "done"], { backup: { detail: "/data/backups/shotsapp/20261013T094107Z" } })) },
  verified: { plan: PLAN, job: null },
  running: { plan: PLAN, job: job("running", steps(["done", "done", "active", "pending"], { restart: { percent: 60 } }), { finished_at: null }) },
  failed: {
    plan: PLAN,
    job: job("failed", steps(["done", "failed", "skipped", "skipped"], { apply: { detail: "Could not write /config/config.xml" } }), { changed: true }),
  },
  "log-open": {
    plan: { ...PLAN, changes: [{ target: "/config/config.xml", key: "/Config/UrlBase", old: "", new: "/shotsapp" }] },
    job: job("rolled_back", steps(["done", "done", "done", "failed"], { verify: { detail: "No answer after 60 seconds" } }), { log_excerpt: LOG, changed: true }),
  },
} as const;

export const CHIP_JOBS = {
  done: job("done", steps(["done", "done", "done", "done"])),
  failed: job("failed", steps(["done", "failed", "skipped", "skipped"])),
};

const inst = (n: number, name: string, status: string, more: object = {}) => ({
  id: `mock-inst-${n}`, template_id: "mock-tpl", name, subdomain: `mock${n}`, container_id: `c${n}`, status,
  error_message: null, env_overrides: {}, volume_names: [], created_at: "2026-10-13T08:00:00",
  started_at: "2026-10-13T08:01:00", stopped_at: null, last_activity: "2026-10-13T09:30:00", session_config: null, ...more,
});
/** Running, paused, stopped and errored instances: fills every header count chip. */
export const INSTANCES = [
  inst(1, "Dev desktop", "running"), inst(2, "Browser", "running"), inst(3, "Notes", "paused"),
  inst(4, "Old build", "stopped", { started_at: null }),
  inst(5, "Broken app", "error", { error_message: "Container exited with code 1" }),
];

const ws = (n: number, name: string, more: object = {}) => ({
  id: `mock-ws-${n}`, name, subdomain: `ws${n}`, hostname: `ws${n}.lan`, lan_ip: `10.0.0.${n}`, port: 8080,
  status: "online", display_server: "wayland", gpu_info: {}, os_info: {}, agent_version: "0.9.31", agent_outdated: false,
  stream_settings: {}, all_users: true, last_heartbeat: "2026-10-13T09:40:00Z", last_error: null, created_at: "2026-10-01T00:00:00Z",
  allowed_user_ids: [], in_use: false, in_use_by: null, in_use_self: false, icon_kind: "auto", icon_etag: "", ...more,
});
/** Online desktops: one in use by me (Recent + Resume), one by someone else, one offline. */
export const WORKSTATIONS = [
  ws(1, "Studio PC", { in_use: true, in_use_self: true }), ws(2, "Gaming rig", { in_use: true, in_use_by: "bob" }),
  ws(3, "Office mini"), ws(4, "Old laptop", { status: "offline" }),
];
