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

const ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#4f46e5"/><rect x="7" y="9" width="18" height="11" rx="1.5" fill="#e0e7ff"/><rect x="12" y="23" width="8" height="2" fill="#e0e7ff"/></svg>';

/** Workstation icons: a small valid SVG so shots show real icons instead of broken images. */
export async function mockWorkstationIcons(page: Page) {
  await page.route("**/api/workstations/*/icon*", (route: Route) =>
    route.fulfill({ status: 200, contentType: "image/svg+xml", body: ICON_SVG }));
}
