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
