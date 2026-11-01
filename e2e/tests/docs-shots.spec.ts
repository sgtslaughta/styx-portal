// Docs screenshots: seeds demo data into the isolated e2e stack, then captures docs/assets/screens/*.
// Run: e2e/docs-shots/run.sh   (see docs/assets/screens/README.md)
import { test, type BrowserContext, type Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { apiCall } from "./helpers";
import { seed, render, type SeedOut } from "../docs-shots/seed";
import { composeHero } from "../docs-shots/hero";
import type { Scene } from "../docs-shots/scenes";

const OUT = resolve(__dirname, "../../docs/assets/screens");
mkdirSync(OUT, { recursive: true });
test.describe.configure({ mode: "serial" });

let admin: BrowserContext;
let out: SeedOut;
const failures: string[] = [];
const png = (n: string) => `${OUT}/${n}.png`;

async function step(name: string, fn: () => Promise<void>) {
  try { await fn(); } catch (e) { failures.push(`${name}: ${String(e).split("\n")[0]}`); console.log("FAILED", name, String(e).slice(0, 300)); }
}
/** Plain UI capture; optionally also composes a hero from the same frame. */
async function shot(p: Page, browser: import("@playwright/test").Browser, name: string, hero?: string) {
  await p.waitForTimeout(900);
  const buf = await p.screenshot({ animations: "disabled" });
  writeFileSync(png(name), buf);
  if (hero) await composeHero(browser, buf, png(hero));
}
/** Fresh context sharing the admin session, so each page gets exactly one theme init script. */
async function themed(browser: import("@playwright/test").Browser, theme: "dark" | "light") {
  const ctx = await browser.newContext({ storageState: await admin.storageState() });
  await ctx.addInitScript((t) => localStorage.setItem("theme", t), theme);
  const p = await ctx.newPage();
  await p.emulateMedia({ colorScheme: theme, reducedMotion: "reduce" });
  return p;
}

/** Open Settings > section (no heading assertions: some sections render two h2s). */
async function openSettings(p: Page, section: string) {
  await p.goto("/");
  await p.getByRole("button", { name: "Settings", exact: true }).or(p.getByText("Settings", { exact: true })).first().click();
  await p.getByRole("button", { name: section, exact: true }).filter({ visible: true }).last().click();
  await p.waitForTimeout(500);
}

const NOTES_HTML = `<!doctype html><meta charset=utf-8><style>*{box-sizing:border-box;margin:0}body{font:15px system-ui;display:flex;height:100vh;background:#fbfbfd;color:#1b1d24}
aside{width:280px;border-right:1px solid #e3e5ec;padding:22px 16px;background:#f3f4f8}h1{font-size:18px;margin-bottom:16px}.n{padding:10px 12px;border-radius:8px;margin-bottom:6px}.n.a{background:#e4e8f6}.n small{display:block;color:#6b7280;margin-top:2px}
main{flex:1;padding:44px 64px;max-width:820px}h2{font-size:28px;margin-bottom:14px}p{line-height:1.7;margin-bottom:12px;color:#374151}li{margin:6px 0 6px 18px}</style>
<aside><h1>Notes</h1><div class=n>Welcome<small>Today</small></div><div class="n a">Render queue<small>Yesterday</small></div><div class=n>Team standup<small>Mon</small></div><div class=n>GPU benchmarks<small>Last week</small></div></aside>
<main><h2>Render queue</h2><p>Shots scheduled for the weekend run on render-box.</p><ul><li>scene-v3: 240 frames</li><li>scene-v4: lighting pass</li><li>turntable: final export</li></ul><p>Remember to check disk space before the batch starts.</p></main>`;

const inst = (n: number, name: string, tpl: string, status: string, more: object = {}) => ({
  id: `demo-${n}`, template_id: tpl, name, subdomain: `demo${n}`, container_id: `c${n}`, status, error_message: null,
  env_overrides: {}, volume_names: [], created_at: "2026-10-30T08:00:00", started_at: "2026-10-31T08:01:00", stopped_at: null,
  last_activity: new Date().toISOString(), session_config: null, ...more,
});

async function mockInstances(p: Page, browser: import("@playwright/test").Browser, list: object[]) {
  await p.route((u) => u.pathname === "/api/instances", (r) => r.request().method() === "GET"
    ? r.fulfill({ json: list }) : r.fallback());
  const scenes: Scene[] = ["code", "browser", "terminal", "files"];
  const jpgs = await Promise.all(scenes.map((s) => render(browser, s, 640, 360, 72)));
  await p.route((u) => /^\/api\/instances\/demo-(\d+)\/screenshot$/.test(u.pathname), (r) => {
    const n = Number(/demo-(\d+)/.exec(new URL(r.request().url()).pathname)![1]);
    return r.fulfill({ body: jpgs[(n - 1) % jpgs.length], contentType: "image/jpeg" });
  });
}

test.beforeAll(async ({ browser }) => {
  const s = await seed(browser);
  admin = s.admin; out = s.out;
});

test("login pages", async ({ browser }) => {
  const ctx = await browser.newContext();
  await ctx.addInitScript(() => localStorage.setItem("theme", "dark"));
  const p = await ctx.newPage();
  await p.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await step("ui-login", async () => {
    await p.goto("/login");
    await p.locator("#username").waitFor();
    await p.mouse.move(0, 0);
    await shot(p, browser, "ui-login");
  });
  await step("ui-login-2fa", async () => {
    await p.route((u) => u.pathname === "/api/auth/login", (r) => r.fulfill({ json: { mfa_required: true, challenge: ["B4", "E7", "A2"] } }));
    await p.locator("#username").fill("alice");
    await p.locator("#password").fill("not-a-real-password");
    await p.getByRole("button", { name: "Sign in" }).click();
    await p.getByLabel("B4").waitFor();
    await shot(p, browser, "ui-login-2fa");
  });
  await ctx.close();
});

test("dashboard, desktops, workstations", async ({ browser }) => {
  const p = await themed(browser, "dark");
  const tpls = (await apiCall(admin, "GET", "/api/templates")) as { id: string; name: string }[];
  const t = (i: number) => tpls[i % tpls.length].id;
  await mockInstances(p, browser, [
    inst(1, "Dev desktop", t(1), "running"), inst(2, "Web browser", t(0), "running"),
    inst(3, "Notes", t(2), "paused"), inst(4, "Build sandbox", t(3), "stopped", { started_at: null }),
  ]);
  await step("workstations tab", async () => {
    await p.goto("/");
    await p.getByRole("tab", { name: "Workspaces" }).click();
    await p.getByText("studio-pc").first().waitFor();
    await p.waitForTimeout(1500);
    await shot(p, browser, "ui-desktops");
    await p.getByText("studio-pc").first().click();
    await p.waitForTimeout(1200);
    await shot(p, browser, "ui-workstations", "hero-dashboard");
  });
  await step("light dashboard", async () => {
    const p = await themed(browser, "light");
    await mockInstances(p, browser, [inst(1, "Dev desktop", t(1), "running"), inst(2, "Web browser", t(0), "running")]);
    await p.goto("/");
    await p.getByRole("tab", { name: "Workspaces" }).click();
    await p.getByText("studio-pc").first().waitFor();
    await p.waitForTimeout(1500);
    await shot(p, browser, "ui-dashboard-light");
  });
  await step("template picker", async () => {
    await p.goto("/");
    await p.getByText("Template gallery", { exact: true }).click();
    await p.waitForTimeout(1200);
    await p.getByRole("button", { name: "Launch" }).first().click();
    await p.getByRole("dialog").waitFor();
    await shot(p, browser, "ui-desktop-launch");
  });
  await p.close();
});

test("services + shell", async ({ browser }) => {
  const p = await themed(browser, "dark");
  await step("ui-services", async () => {
    await p.goto("/");
    await p.getByRole("tab", { name: "Apps" }).click();
    await p.waitForTimeout(3500);
    await shot(p, browser, "ui-services");
  });
  await step("ui-service-form", async () => {
    await openSettings(p, "Services");
    await p.waitForTimeout(800);
    await p.getByRole("button", { name: "Add service" }).click();
    await p.getByRole("dialog").waitFor();
    await p.waitForTimeout(800);
    await shot(p, browser, "ui-service-form");
  });
  await step("ui-shell-dock", async () => {
    await p.route((u) => !u.pathname.startsWith("/_styx") && !u.pathname.startsWith("/api"), (r) => {
      const q = r.request();
      return q.resourceType() === "document" && q.frame().parentFrame() ? r.fulfill({ contentType: "text/html", body: NOTES_HTML }) : r.fallback();
    });
    // Dock icons: the shell build requests /api/services/<id>/icon; serve letter tiles (as the portal's auto icons look).
    await p.route((u) => /^\/api\/services\/[^/]+\/icon$/.test(u.pathname), async (r) => {
      const id = new URL(r.request().url()).pathname.split("/")[3];
      const svc = ((await apiCall(admin, "GET", "/api/services")) as { id: string; name: string }[]).find((x) => x.id === id);
      const hue = [...(svc?.name ?? "?")].reduce((a, c) => a + c.charCodeAt(0), 0) * 47 % 360;
      return r.fulfill({ contentType: "image/svg+xml", body: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="hsl(${hue} 45% 42%)"/><text x="32" y="43" font-size="32" font-family="sans-serif" font-weight="700" text-anchor="middle" fill="#fff">${(svc?.name ?? "?")[0]}</text></svg>` });
    });
    await p.goto("/_styx/app/notes/");
    await p.locator("iframe").waitFor();
    await p.waitForTimeout(1500);
    await p.keyboard.press("Alt+Shift+S");
    await p.getByRole("dialog").waitFor();
    await p.waitForTimeout(1200);
    await shot(p, browser, "ui-shell-dock", "hero-services");
  });
  await p.close();
});

test("admin", async ({ browser }) => {
  const p = await themed(browser, "dark");
  for (const [section, name, hero] of [["Users", "ui-admin-users"], ["Groups", "ui-admin-groups"], ["Settings", "ui-admin-settings", "hero-admin"],
    ["SSO Providers", "ui-admin-sso"], ["Health", "ui-health"], ["Workstations", "ui-workstation-settings"]] as const) {
    await step(name, async () => {
      await openSettings(p, section);
      await p.waitForTimeout(2200);
      if (name === "ui-workstation-settings") await p.getByText("Stream settings").first().click();
      await shot(p, browser, name, hero);
    });
  }
  await step("ui-enroll", async () => {
    await openSettings(p, "Workstations");
    await p.getByRole("button", { name: /enroll|add workstation|new workstation/i }).first().click();
    await p.waitForTimeout(2000);
    // Demo values only: swap the live (ephemeral) token, pin and container-network address for placeholders.
    await p.evaluate(() => {
      for (const el of document.querySelectorAll("code, pre")) {
        const t = el.textContent ?? "";
        if (!t.includes("curl")) continue;
        el.textContent = t.replace(/https?:\/\/[\d.]+(:\d+)?/g, "https://styx.example.com").replace(/--token \S+/g, "--token c-DEMO0000TOKEN0000")
          .replace(/sha256[:/][0-9a-f]+/g, "sha256/AbCdEf0123DEMOPIN").replace(/'sha256[^']*'/g, "'sha256//DEMO'");
      }
    });
    await shot(p, browser, "ui-enroll");
  });
  await step("ui-templates", async () => {
    await p.goto("/");
    await p.getByText("Template gallery", { exact: true }).click();
    await p.waitForTimeout(1500);
    await shot(p, browser, "ui-templates");
  });
  await p.close();
});

test.afterAll(() => { if (failures.length) console.log("FAILURES:\n" + failures.join("\n")); });
