import { test, expect, type Page } from "@playwright/test";
import { writeFileSync, mkdirSync } from "node:fs";
import { ADMIN, setupCode, uiLogin } from "./helpers";
import { INSTANCES, mockApi } from "./shots-mocks";

const OUT = "screenshots/audit";
const SIZES = [{ n: "390", w: 390, h: 844 }, { n: "412", w: 412, h: 915 }, { n: "844l", w: 844, h: 390 }, { n: "1440", w: 1440, h: 900 }];
const SECTIONS = ["overview", "health", "sessions", "logs", "users", "sso", "workstations", "services", "images", "streaming",
  "security", "timeouts", "signin-card", "connected", "profiles"];
const report: Record<string, unknown> = {};

/** Horizontal overflow + elements wider than viewport + small tap targets. */
const probe = (page: Page) => page.evaluate(() => {
  const vw = innerWidth, out: string[] = [], small: string[] = [];
  const name = (e: Element) => `${e.tagName.toLowerCase()}${e.id ? "#" + e.id : ""}[${(e.getAttribute("aria-label") || (e as HTMLElement).innerText || "").trim().slice(0, 30)}]`;
  for (const e of document.querySelectorAll("body *")) {
    const r = e.getBoundingClientRect();
    if (!r.width || getComputedStyle(e).visibility === "hidden") continue;
    if (r.right > vw + 1 && !e.closest("[class*=overflow-x-auto],[class*=overflow-auto]")) out.push(`${name(e)} right=${Math.round(r.right)}`);
    if (e.matches("button,a,[role=tab],[role=switch],input,select") && (r.width < 40 || r.height < 40) && r.right > 0 && r.left < vw)
      small.push(`${name(e)} ${Math.round(r.width)}x${Math.round(r.height)}`);
  }
  return { docOverflowX: document.documentElement.scrollWidth - vw, docHeight: document.documentElement.scrollHeight,
    wide: out.slice(0, 15), smallTargets: small.slice(0, 40) };
});

async function snap(page: Page, key: string) {
  await page.waitForTimeout(400);
  await page.screenshot({ path: `${OUT}/${key}.png`, fullPage: true });
  report[key] = await probe(page);
  writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
}

test("mobile audit", async ({ browser }) => {
  mkdirSync(OUT, { recursive: true });
  const ctx = await browser.newContext({ isMobile: true, hasTouch: true, viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto("/");
  await page.waitForURL(/\/(setup|login)$/);
  if (page.url().endsWith("/setup")) {
    await snap(page, "setup-390");
    await page.locator("#username").fill(ADMIN.username);
    await page.locator("#setup-code").fill(setupCode());
    await page.locator("#password").fill(ADMIN.password);
    await page.getByRole("button", { name: "Create admin" }).click();
    await page.waitForURL((u) => !u.pathname.endsWith("/setup"));
    await page.context().clearCookies();
  }
  await page.goto("/login");
  await snap(page, "login-390");
  await uiLogin(page, ADMIN);
  await page.waitForURL((u) => !u.pathname.endsWith("/login"));
  await page.waitForTimeout(1500);
  await snap(page, "after-login-390");
  writeFileSync(`${OUT}/after-login.txt`, await page.locator("body").ariaSnapshot());
  await mockApi(page, "GET", "/api/instances", INSTANCES);
  for (const s of SIZES) {
    await page.setViewportSize({ width: s.w, height: s.h });
    for (const theme of s.n === "390" ? ["dark", "light"] : ["dark"]) {
      await page.evaluate((t) => localStorage.setItem("theme", t), theme);
      await page.emulateMedia({ colorScheme: theme as "dark" | "light", reducedMotion: "reduce" });
      const k = (x: string) => `${x}-${s.n}-${theme}`;
      await page.goto("/");
      await page.waitForTimeout(800);
      await snap(page, k("home"));
      for (const tab of await page.getByRole("tab").all()) {
        const label = ((await tab.textContent()) || "tab").trim().replace(/\W+/g, "_").slice(0, 20);
        if (!(await tab.isVisible())) continue; await tab.click({ timeout: 5000 }).catch(() => {});
        await snap(page, k(`home-tab-${label}`));
      }
      const nc = page.getByRole("button", { name: /new container/i }).first();
      if (await nc.isVisible().catch(() => false)) {
        if (await nc.click().then(() => true, () => false)) { await snap(page, k("new-container")); await page.keyboard.press("Escape"); }
        else report[k("new-container")] = "BLOCKED: New container click intercepted";
      }
      if (theme !== "dark") continue;
      const sb = page.getByRole("button", { name: "Admin", exact: true });
      if (!(await sb.isVisible())) { report[k("settings")] = "NO VISIBLE SETTINGS BUTTON"; continue; }
      if (!(await sb.click().then(() => true, () => false))) { report[k("settings")] = "BLOCKED: Admin click intercepted"; continue; }
      await page.waitForTimeout(600);
      for (const id of SECTIONS) {
        await page.evaluate((i) => window.dispatchEvent(new CustomEvent("styx:settings-section", { detail: i })), id);
        await snap(page, k(`settings-${id}`));
      }
    }
  }
  writeFileSync(`${OUT}/report.json`, JSON.stringify(report, null, 1));
});
