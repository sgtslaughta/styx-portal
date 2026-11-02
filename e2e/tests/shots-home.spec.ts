import { expect, test, type Page } from "@playwright/test";
import { ADMIN, MEMBER, SHOTS, openSettings, uiLogin } from "./helpers";
import { INSTANCES, mockApi } from "./shots-mocks";

// Home layout gates: no page-level vertical overflow, and the header with every count chip at 390.
const SIZES = [{ w: 1440, h: 900 }, { w: 390, h: 844 }];
const THEMES = ["light", "dark"] as const;

async function login(page: Page, u: typeof ADMIN) {
  await uiLogin(page, u);
  await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
}
const overflow = (page: Page) => page.evaluate(() => document.documentElement.scrollHeight - innerHeight);

test("home has no vertical overflow at 1440 and 390", async ({ page }) => {
  await login(page, MEMBER);
  for (const sz of SIZES) {
    await page.setViewportSize({ width: sz.w, height: sz.h });
    await page.goto("/");
    await expect(page.getByRole("region", { name: "Apps" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollHeight <= innerHeight), `${sz.w}px`).toBe(true);
    expect(await overflow(page)).toBeLessThanOrEqual(0);
  }
});

test("home with running, paused, stopped and errored instances", async ({ page }) => {
  await login(page, ADMIN);
  await mockApi(page, "GET", "/api/instances", INSTANCES);
  for (const sz of SIZES) for (const t of THEMES) {
    await page.setViewportSize({ width: sz.w, height: sz.h });
    await page.evaluate((v) => localStorage.setItem("theme", v), t);
    await page.emulateMedia({ colorScheme: t, reducedMotion: "reduce" });
    await page.goto("/");
    await page.getByRole("tab", { name: "Workspaces" }).click(); // instances live on the Workspaces tab
    await expect(page.getByText("Dev desktop")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/home-instances-${sz.w}-${t}.png` });
    expect(await overflow(page), `${sz.w}px ${t}`).toBeLessThanOrEqual(0);
  }
});

test("phone 390: header fits, Log out in account menu, New container tappable", async ({ page }) => {
  await login(page, ADMIN);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  // Nothing may stick out past the right edge (header used to push Log out off-screen).
  const widest = await page.evaluate(() => Math.max(...[...document.querySelectorAll("header *")].map((e) => e.getBoundingClientRect().right)));
  expect(widest, "header right edge").toBeLessThanOrEqual(390);
  // The status rail is hidden on phones, so it can't swallow taps on content.
  await expect(page.getByRole("complementary", { name: "Server status" })).toBeHidden();
  await page.getByRole("button", { name: "New container" }).click();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: /Account menu/ }).click();
  await expect(page.getByRole("menuitem", { name: "Log out" })).toBeVisible();
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
