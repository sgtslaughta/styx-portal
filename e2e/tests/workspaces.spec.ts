import { expect, test, type BrowserContext } from "@playwright/test";
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
  await expect(p.getByRole("button", { name: "Log out" })).toBeVisible(); // login must land before we navigate away
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

const DESK = {
  id: "desk-1", template_id: "t", name: "Desk", subdomain: "desk", container_id: null, status: "running",
  error_message: null, env_overrides: {}, volume_names: [], created_at: "2026-01-01T00:00:00",
  started_at: null, stopped_at: null, last_activity: null, session_config: null,
};

/** One running instance, no workstations; /i/desk/ is a plain page (the e2e stack has no container). */
async function stubDesk(ctx: BrowserContext) {
  await ctx.route("**/api/instances", (r) => r.request().method() === "GET" ? r.fulfill({ json: [DESK] }) : r.fallback());
  await ctx.route("**/api/workstations/mine", (r) => r.fulfill({ json: [] }));
  await ctx.route("**/i/desk/**", (r) => r.fulfill({ contentType: "text/html", body: "<title>desk</title><p>desk stream</p>" }));
}

test("workspace Connect: prompt, new tab goes via /connecting to the stream; dock does the same", async ({ browser }) => {
  const ctx = await browser.newContext();
  const p = await ctx.newPage();
  await uiLogin(p, ADMIN);
  await expect(p.getByRole("button", { name: "Log out" })).toBeVisible();
  try {
    await apiCall(ctx, "PUT", "/api/auth/me/preferences", { open_apps: null, open_workspaces: null });
    await stubDesk(ctx);
    // a) home
    await p.goto("/");
    await p.getByRole("tab", { name: "Workspaces" }).click();
    await p.getByRole("button", { name: "Connect" }).first().click();
    const dlg = p.getByRole("dialog", { name: "Open Desk" });
    const [tab] = await Promise.all([ctx.waitForEvent("page"), dlg.getByRole("button", { name: "Open in new tab" }).click()]);
    await expect(tab).toHaveURL(/\/i\/desk\/$/, { timeout: 15_000 });
    await expect(tab.getByText("desk stream")).toBeVisible();
    await expect(p).toHaveURL(/\/$/);
    await tab.close();
    // b) dock; prefs back to Ask first
    await apiCall(ctx, "PUT", "/api/auth/me/preferences", { open_workspaces: null });
    // Real Sonarr keeps stealing focus into its iframe while loading; a static frame keeps the focus assertion honest.
    await ctx.route((u) => u.pathname.startsWith("/sonarr/"), (r) => r.request().resourceType() === "document"
      ? r.fulfill({ contentType: "text/html", body: "<title>sonarr</title><p>sonarr</p>" }) : r.fallback());
    await p.goto("/_styx/app/sonarr/");
    await expect.poll(() => p.frames().some((f) => f.url().includes("/sonarr/"))).toBe(true);
    await p.waitForLoadState("load");
    await p.locator('[aria-label="Open the Styx menu (Alt+Shift+S)"]').click();
    const dock = p.getByRole("dialog");
    await dock.getByRole("tab", { name: "Workspaces" }).click();
    await dock.getByRole("button", { name: /Desk/ }).click();
    const prompt = p.getByRole("dialog", { name: "Open Desk" });
    await expect(prompt).toBeVisible();
    await expect(p.getByRole("dialog")).toHaveCount(1); // the dock closed
    await expect(prompt.getByRole("button", { name: "Open in new tab" })).toBeFocused();
  } finally {
    await apiCall(ctx, "PUT", "/api/auth/me/preferences", { open_apps: null, open_workspaces: null });
    await ctx.close();
  }
});
