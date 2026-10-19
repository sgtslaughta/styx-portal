import { expect, test, type Page } from "@playwright/test";
import { ADMIN, MEMBER, SHOTS, accountMenu, openHome, openSettings, uiLogin } from "./helpers";
import { INSTANCES, mockApi } from "./shots-mocks";

// Home layout gates: no page-level vertical overflow; header, nav and panes at 1440 and 390.
const SIZES = [{ w: 1440, h: 900 }, { w: 390, h: 844 }];
const THEMES = ["light", "dark"] as const;

async function login(page: Page, u: typeof ADMIN) {
  await uiLogin(page, u);
  await expect(accountMenu(page)).toBeVisible();
}
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollHeight - innerHeight);
async function look(page: Page, w: number, h: number, t: (typeof THEMES)[number]) {
  await page.setViewportSize({ width: w, height: h });
  await page.evaluate((v) => localStorage.setItem("theme", v), t);
  await page.emulateMedia({ colorScheme: t, reducedMotion: "reduce" });
}

const STUDIO = {
  id: "ws-studio", name: "Studio", subdomain: "studio", hostname: "studio-host", lan_ip: "10.0.0.5", port: 8443,
  status: "online", display_server: "wayland", gpu_info: { model: "RTX 4090" }, os_info: { pretty_name: "Ubuntu 24.04" },
  agent_version: "0.7.0", agent_outdated: false, stream_settings: {}, all_users: true,
  last_heartbeat: new Date().toISOString(), last_error: null, created_at: "2026-01-01T00:00:00Z", allowed_user_ids: [],
  in_use: false, in_use_by: null, in_use_self: false, icon_kind: "auto", icon_etag: "e",
};

test("home has no vertical overflow at 1440 and 390", async ({ page }) => {
  await login(page, MEMBER);
  for (const sz of SIZES) {
    await page.setViewportSize({ width: sz.w, height: sz.h });
    await openHome(page, "Apps");
    await expect(page.getByRole("region", { name: "Apps" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight), `${sz.w}px`).toBe(true);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  }
});

test("home with running, paused, stopped and errored instances", async ({ page }) => {
  await login(page, ADMIN);
  await mockApi(page, "GET", "/api/instances", INSTANCES);
  for (const sz of SIZES) for (const t of THEMES) {
    await look(page, sz.w, sz.h, t);
    await openHome(page, "Workspaces");
    await expect(page.getByText("Dev desktop")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/home-instances-${sz.w}-${t}.png` });
    expect(await overflow(page), `${sz.w}px ${t}`).toBeLessThanOrEqual(0);
  }
});

test("home workstation pane: online, offline, phone overlay", async ({ page }) => {
  await login(page, ADMIN);
  await mockApi(page, "GET", "/api/workstations/mine",
    [STUDIO, { ...STUDIO, id: "ws-lab", name: "Lab", status: "offline", last_error: "Agent stopped" }]);
  await mockApi(page, "GET", "/api/instances", INSTANCES);
  for (const sz of SIZES) for (const t of THEMES) {
    await look(page, sz.w, sz.h, t);
    await openHome(page, "Workspaces");
    await page.getByRole("button", { name: /^Studio/ }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Studio" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Connect", exact: true })).toBeEnabled();
    await page.screenshot({ path: `${SHOTS}/home-ws-pane-${sz.w}-${t}.png` });
    expect(await overflow(page), `${sz.w}px ${t}`).toBeLessThanOrEqual(0);
    if (sz.w === 390) await page.getByRole("button", { name: "Back" }).click();
    await page.getByRole("button", { name: /^Lab/ }).click();
    await expect(page.getByRole("button", { name: "Offline", exact: true })).toBeDisabled();
    await page.screenshot({ path: `${SHOTS}/home-ws-offline-${sz.w}-${t}.png` });
  }
});

test("header account menu and theme toggle are right-aligned at 390", async ({ page }) => {
  await login(page, MEMBER);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const toggle = (await page.getByRole("button", { name: "Toggle theme" }).boundingBox())!;
  const menu = (await accountMenu(page).boundingBox())!;
  expect(toggle.x + toggle.width, "controls right edge").toBeGreaterThanOrEqual(390 - 24);
  expect(menu.x, "account menu starts in the right half").toBeGreaterThan(195);
});

test("Log out lives in the account menu", async ({ browser }) => {
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await login(page, MEMBER);
  await accountMenu(page).click();
  await page.getByRole("menuitem", { name: "Log out" }).click();
  await expect(page.locator("#username")).toBeVisible();
  await ctx.close();
});

test("users table at 390 stays inside its card", async ({ page }) => {
  await login(page, ADMIN);
  await page.setViewportSize({ width: 390, height: 844 });
  for (const t of THEMES) {
    await page.evaluate((v) => localStorage.setItem("theme", v), t);
    await page.emulateMedia({ colorScheme: t, reducedMotion: "reduce" });
    await openSettings(page, "Users");
    await expect(page.getByRole("row").filter({ hasText: MEMBER.username })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    // The table's own wrapper must not scroll sideways: actions collapse into the More menu.
    expect(await page.locator("table").evaluate((t) => t.parentElement!.scrollWidth <= t.parentElement!.clientWidth)).toBe(true);
    await page.screenshot({ path: `${SHOTS}/users-390-${t}.png`, fullPage: true });
  }
});
