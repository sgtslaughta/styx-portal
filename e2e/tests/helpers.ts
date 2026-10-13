import { expect, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

export const ADMIN = { username: "admin", password: "Styx-e2e-Admin-Quartz-Lantern-91" };
export const MEMBER = { username: "alice", password: "Styx-e2e-Member-Willow-Harbor-57" };
export const OUTSIDER = { username: "bob", password: "Styx-e2e-Outsider-Cobalt-Meadow-38" };
export const STYX_COOKIES = ["access_token", "refresh_token", "styx_proxy", "csrf_token", "styx_svc"];
export const SHOTS = "screenshots";

/** traefik/whoami echoes the request line and headers as plain text. */
export const isWhoami = (body: string) => /^Hostname: /m.test(body) && /^RemoteAddr: /m.test(body);
export const headerLines = (body: string, name: string) =>
  body.split("\n").filter((l) => l.toLowerCase().startsWith(`${name.toLowerCase()}:`))
    .map((l) => l.slice(name.length + 1).trim());

export async function uiLogin(page: Page, u: { username: string; password: string }, path = "/login") {
  await page.goto(path);
  await page.locator("#username").fill(u.username);
  await page.locator("#password").fill(u.password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

export async function openSettings(page: Page, section: string) {
  await page.goto("/");
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: section, exact: true }).filter({ visible: true }).first().click();
  await expect(page.getByRole("heading", { level: 2, name: section })).toBeVisible();
}

/** Same request context as the page (shares cookies); adds the CSRF header. */
export async function apiCall(ctx: BrowserContext, method: string, url: string, data?: unknown) {
  const csrf = (await ctx.cookies()).find((c) => c.name === "csrf_token")?.value ?? "";
  const res = await ctx.request.fetch(url, {
    method, data, headers: { "X-CSRF-Token": csrf, "X-Styx-Client": "1" },
  });
  expect(res.ok(), `${method} ${url} -> ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.status() === 204 ? null : res.json();
}

/** Poll until `fn` passes: Traefik reloads the file provider asynchronously. */
export async function eventually(fn: () => Promise<void>, timeout = 15_000) {
  await expect(async () => { await fn(); }).toPass({ timeout, intervals: [250, 500, 1000] });
}

export async function getNoRedirect(req: APIRequestContext, url: string, headers: Record<string, string> = {}) {
  return req.get(url, { maxRedirects: 0, headers });
}

export async function setTheme(page: Page, want: "light" | "dark") {
  for (let i = 0; i < 3; i++) {
    if ((await page.evaluate(() => localStorage.getItem("theme"))) === want) break;
    await page.getByRole("button", { name: "Toggle theme" }).click();
  }
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBe(want);
  await expect(page.locator("html")).toHaveClass(want === "dark" ? /dark/ : /^(?!.*dark).*$/);
}
