import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import {
  ADMIN, MEMBER, SHOTS, STYX_COOKIES, ensureService, eventually, headerLines, isWhoami, settled, uiLogin, updateService,
} from "./helpers";

test.describe.configure({ mode: "serial" });

const TAB = "Open the Styx menu (Alt+Shift+S)";
let admin: { ctx: BrowserContext; page: Page };
let member: { ctx: BrowserContext; page: Page };

test.beforeAll(async ({ browser }) => {
  for (const [who, u] of [["admin", ADMIN], ["member", MEMBER]] as const) {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await uiLogin(page, u);
    await expect(page.getByRole("button", { name: "Log out" })).toBeVisible();
    if (who === "admin") admin = { ctx, page }; else member = { ctx, page };
  }
  const c = admin.ctx;
  await updateService(c, "sonarr", { allowed_groups: ["media"] });
  const focus = { kind: "docker-local", container: "styx-e2e-focusapp-1", container_port: 80, mount_mode: "cookie-root" };
  await ensureService(c, { slug: "focusapp", name: "Focusapp", ...focus });
  await ensureService(c, { slug: "focusapp2", name: "Focusapp Two", ...focus });
  await ensureService(c, { slug: "frameblock", name: "Frameblock", kind: "docker-local", container: "styx-e2e-frameblock-1", container_port: 80 });
  const who = { kind: "url", upstream_url: "http://whoami-url:80", container: null, container_port: null };
  await ensureService(c, { slug: "idon", name: "Idon", pass_identity: true, ...who });
  await ensureService(c, { slug: "idoff", name: "Idoff", pass_identity: false, ...who });
  // Traefik loads the new routers asynchronously.
  for (const slug of ["idon", "idoff"])
    await eventually(async () => expect(isWhoami(await (await member.ctx.request.get(`/${slug}/`)).text())).toBe(true), 60_000);
});
test.afterAll(async () => { await admin?.ctx.close(); await member?.ctx.close(); });

const frameOf = (p: Page) => p.frames().find((f) => f !== p.mainFrame());
const tab = (p: Page) => p.locator(`[aria-label="${TAB}"]`); // aria-hidden while the modal dock is open
const dock = (p: Page) => p.getByRole("dialog");

test("s1 shell keeps the URL in sync with the frame", async () => {
  const p = member.page;
  await p.goto("/");
  await p.getByRole("link", { name: "Open Sonarr" }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/sonarr\/$/);
  await expect(p.frameLocator("iframe").locator("body")).toBeVisible();
  await eventually(async () => {
    const f = frameOf(p)!;
    await f.goto(`${p.url().split("/_styx")[0]}/sonarr/calendar`);
    await expect(p).toHaveURL(/\/_styx\/app\/sonarr\/calendar$/, { timeout: 3000 });
  }, 60_000);
  await p.reload();
  await expect(p).toHaveURL(/\/_styx\/app\/sonarr\/calendar$/);
  await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/sonarr\/calendar$/);
});

/** Keyboard focus is inside the dock. */
async function dockHasFocus(p: Page) {
  await expect.poll(() => p.evaluate(() => !!document.querySelector("[role=dialog]")?.contains(document.activeElement))).toBe(true);
}

/** With styx_svc set, `/` and the SPA assets are the focus app's. Serve the Styx SPA files by fetching them
 *  without the takeover cookie; /api calls still carry styx_svc, so the tile shows the focus state. */
async function homeWhileFocused(p: Page) {
  const match = (u: URL) => !/^\/(api|_styx)\b/.test(u.pathname);
  await p.route(match, async (route) => {
    const h = route.request().headers();
    const cookie = (h["cookie"] ?? "").split("; ").filter((c) => !c.startsWith("styx_svc=")).join("; ");
    await route.fulfill({ response: await route.fetch({ headers: { ...h, cookie } }) });
  });
  await p.goto("/");
  await expect(p.getByRole("region", { name: "Services" })).toBeVisible();
}

const FERRY = "styx.ferry";

test("s2 dock on Sonarr: hotkey, focus, current app, Esc, drag side persists", async () => {
  const p = member.page;
  try {
    await p.goto("/_styx/app/sonarr/");
    await expect(tab(p)).toBeVisible();
    await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/sonarr\/$/);
    await expect(tab(p)).toHaveAttribute("aria-expanded", "false");
    await p.keyboard.press("Alt+Shift+S");
    await expect(dock(p)).toBeVisible();
    // No focus assertion here: Sonarr's modal focus trap pulls focus back into the frame (see s2c for a calm app).
    await expect(tab(p)).toHaveAttribute("aria-expanded", "true");
    await expect(dock(p).getByRole("link", { name: /Sonarr/ })).toHaveAttribute("aria-current", "page");
    await p.keyboard.press("Escape"); // typed inside the frame: the shell forwards it
    await expect(dock(p)).toBeHidden();

    for (const vp of [{ w: 1440, h: 900 }, { w: 390, h: 844 }]) {
      await p.setViewportSize({ width: vp.w, height: vp.h });
      await p.keyboard.press("Alt+Shift+S");
      await expect(dock(p)).toBeVisible();
      await settled(dock(p));
      const box = (await dock(p).boundingBox())!;
      if (vp.w === 390) { // phone: bottom sheet, flush with the bottom edge, full width
        expect(box.x).toBeLessThanOrEqual(1);
        expect(box.width).toBeGreaterThanOrEqual(vp.w - 1);
        expect(Math.abs(box.y + box.height - vp.h)).toBeLessThanOrEqual(1);
      } else { // desktop: side panel, not a sheet
        expect(box.width).toBeLessThan(vp.w / 2);
        expect(box.height).toBeGreaterThanOrEqual(vp.h - 1);
      }
      for (const theme of ["light", "dark"] as const) {
        await p.evaluate((t) => { localStorage.setItem("theme", t); document.documentElement.classList.toggle("dark", t === "dark"); }, theme);
        await p.screenshot({ path: `${SHOTS}/shell-dock-${vp.w}-${theme}.png` });
      }
      await p.keyboard.press("Escape");
      await expect(dock(p)).toBeHidden();
      const tb = (await tab(p).boundingBox())!;
      expect(tb.width, "edge tab touch target").toBeGreaterThanOrEqual(44);
      expect(tb.height, "edge tab touch target").toBeGreaterThanOrEqual(44);
    }
    await p.setViewportSize({ width: 1440, height: 900 });
    await p.evaluate(() => { localStorage.setItem("theme", "light"); document.documentElement.classList.remove("dark"); });

    // Drag the tab over the app frame: the product turns the iframe's pointer events off for the drag.
    await expect.poll(async () => (await tab(p).boundingBox())!.x).toBeGreaterThan(1300); // re-placed after the resize
    await settled(tab(p));
    const box = (await tab(p).boundingBox())!;
    await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await p.mouse.down();
    await p.mouse.move(box.x - 200, box.y + 40, { steps: 10 });
    await expect(p.locator("iframe")).toHaveCSS("pointer-events", "none");
    await p.mouse.move(60, box.y + 40, { steps: 10 });
    await p.mouse.move(20, box.y + 40, { steps: 5 });
    await p.mouse.up();
    await expect(p.locator("iframe")).not.toHaveCSS("pointer-events", "none");
    await expect.poll(() => p.evaluate((k) => JSON.parse(localStorage.getItem(k) ?? "{}").side, FERRY)).toBe("left");
    await p.reload();
    await expect.poll(async () => (await tab(p).boundingBox())!.x).toBeLessThan(720);
  } finally {
    await p.evaluate((k) => localStorage.removeItem(k), FERRY).catch(() => {});
  }
});

test("s2b Esc closes a hotkey-opened dock even when the frame held focus", async () => {
  const p = member.page;
  await p.goto("/_styx/app/sonarr/");
  await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/sonarr\/$/);
  await frameOf(p)!.evaluate(() => { document.body.tabIndex = 0; document.body.focus(); });
  await p.keyboard.press("Alt+Shift+S");
  await expect(dock(p)).toBeVisible();
  await p.keyboard.press("Escape");
  await expect(dock(p)).toBeHidden();
});

test("s2c focus moves into the dock and Esc hands it back to the tab (calm app)", async () => {
  const p = member.page;
  await p.goto("/_styx/app/idon/");
  await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/idon\/$/);
  await p.keyboard.press("Alt+Shift+S");
  await expect(dock(p)).toBeVisible();
  await dockHasFocus(p);
  await p.keyboard.press("Escape");
  await expect(dock(p)).toBeHidden();
  await expect(tab(p)).toBeFocused();
});

test("s3 focus swap clears root service workers; exit clears styx_svc", async () => {
  const p = await member.ctx.newPage(); // own page: the init script below must not leak into later tests
  try {
  await p.goto("/_styx/app/sonarr/");
  await tab(p).click();
  await dock(p).getByRole("link", { name: /Focusapp(?! Two)/ }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/focusapp\/$/);
  // The focus app registers its root-scoped worker inside the frame.
  await expect.poll(() => p.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length),
    { timeout: 30_000 }).toBeGreaterThan(0);

  // The shell unregisters root workers before it mounts the next frame: count them the moment the
  // iframe appears (the new app has not run yet, so it cannot have re-registered).
  await p.addInitScript(() => {
    new MutationObserver((_, obs) => {
      if (!document.querySelector("iframe")) return;
      obs.disconnect();
      void navigator.serviceWorker.getRegistrations().then((r) => { (window as unknown as { swAtFrame: number }).swAtFrame = r.length; });
    }).observe(document, { childList: true, subtree: true });
  });
  await tab(p).click();
  await dock(p).getByRole("link", { name: /Focusapp Two/ }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/focusapp2\/$/);
  await expect(p.locator("iframe")).toBeVisible();
  await expect.poll(() => p.evaluate(() => (window as unknown as { swAtFrame?: number }).swAtFrame)).toBe(0);

  await homeWhileFocused(p);
  await expect(p.getByRole("link", { name: "Exit Focusapp Two" })).toBeVisible();
  await expect(p.getByRole("link", { name: "Open Focusapp Two" })).toContainText(/Opens full screen/);
  await expect(p.getByRole("link", { name: "Open Focusapp Two" })).toHaveAttribute("aria-current", "true");
  await expect(p.getByRole("link", { name: "Open Focusapp", exact: true })).not.toHaveAttribute("aria-current");
  await p.getByRole("link", { name: "Exit Focusapp Two" }).click();
  await expect.poll(async () => (await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);
  await p.unrouteAll({ behavior: "ignoreErrors" });
  await p.goto("/");
  await expect(p.getByRole("link", { name: "Open Focusapp Two" })).toBeVisible();
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);
  } finally { await p.close(); }
});

test("s4 cross-site open needs a click and sets no cookie", async () => {
  const r = await member.ctx.request.get("/_styx/open/focusapp", { headers: { "Sec-Fetch-Site": "cross-site" }, maxRedirects: 0 });
  expect(r.status()).toBe(200);
  expect(r.headers()["set-cookie"] ?? "").not.toContain("styx_svc");
  const html = await r.text();
  expect(html).toMatch(/Open app/i);
  expect(html).not.toMatch(/<form/i);
  expect(html).toContain('href="/_styx/open/focusapp"');
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);

  const p = member.page;
  const missing = await member.ctx.request.get("/_styx/open/focusapp", { maxRedirects: 0 });
  expect(missing.status()).toBe(200); // no Sec-Fetch-Site header from a bare client: also unconfirmed
  await p.route("**/_styx/open/focusapp?confirm", (rt) => rt.fulfill({ status: 200, contentType: "text/html", body: html }));
  await p.goto("/_styx/open/focusapp?confirm");
  await p.unroute("**/_styx/open/focusapp?confirm");
  await p.getByRole("link", { name: "Open app" }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/focusapp\/$/);
  await p.goto("/_styx/exit?next=/");
});

test("s5 frame-blocking app gets the blocked card", async () => {
  const p = member.page;
  await p.goto("/_styx/app/frameblock/");
  await expect(p.getByRole("heading", { name: "Frameblock can't run inside Styx" })).toBeVisible({ timeout: 30_000 });
  const link = p.getByRole("link", { name: "Open Frameblock on its own" });
  await expect(link).toHaveAttribute("href", "/frameblock/");
  await expect(p.locator("iframe")).toHaveCount(0);
});

test("s6 identity headers only when enabled; spoofing is replaced", async () => {
  const get = async (slug: string) => {
    await eventually(async () => expect(isWhoami(await (await member.ctx.request.get(`/${slug}/`)).text())).toBe(true), 30_000);
    return (await member.ctx.request.get(`/${slug}/`, { headers: { "X-Styx-User": "mallory", "X-Styx-Groups": "admins" } })).text();
  };
  const on = await get("idon");
  expect(headerLines(on, "X-Styx-User")).toEqual([MEMBER.username]);
  expect(headerLines(on, "X-Styx-Email").length).toBe(1);
  expect(headerLines(on, "X-Styx-Groups")).toEqual(["media"]);
  expect(on).not.toContain("mallory");
  const off = await get("idoff");
  expect(off).not.toMatch(/^X-Styx-/im);
  for (const c of STYX_COOKIES) expect(headerLines(off, "Cookie").join(";")).not.toContain(`${c}=`);
});

test("s7 service responses are framable only by Styx", async () => {
  for (const path of ["/idon/", "/sonarr/ping"]) {
    const r = await member.ctx.request.get(path);
    expect(r.status(), path).toBeLessThan(400);
    expect(r.headers()["x-frame-options"], path).toBe("SAMEORIGIN");
  }
});

