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
    await expect(page.getByRole("region", { name: "Services" })).toBeVisible();
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
    await expect(page.getByText("Dev desktop")).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/home-instances-${sz.w}-${t}.png` });
    expect(await overflow(page), `${sz.w}px ${t}`).toBeLessThanOrEqual(0);
  }
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
    await page.screenshot({ path: `${SHOTS}/users-390-${t}.png`, fullPage: true });
  }
});
