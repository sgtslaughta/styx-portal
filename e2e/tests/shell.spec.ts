import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import {
  ADMIN, MEMBER, SHOTS, STYX_COOKIES, ensureService, eventually, headerLines, isWhoami, openSettings, uiLogin, updateService,
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

async function openShell(p: Page, slug: string) {
  await p.goto("/");
  await p.getByRole("link", { name: new RegExp(`Open ${slug}`, "i") }).first().click();
}

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

/** Focus is inside the dock and stays there (an iframe hotkey briefly takes it back). */
async function dockHasFocus(p: Page) {
  await expect.poll(() => p.evaluate(async () => {
    const d = document.querySelector("[role=dialog]");
    const inside = () => !!d && d.contains(document.activeElement);
    if (!inside()) return false;
    await new Promise((r) => setTimeout(r, 200));
    return inside();
  }), { timeout: 10_000 }).toBe(true);
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
async function endHomeWhileFocused(p: Page) { await p.unrouteAll({ behavior: "ignoreErrors" }); }

async function dockShots(p: Page, tag: string) {
  await p.waitForTimeout(400);
  await p.screenshot({ path: `${SHOTS}/shell-dock-${tag}.png` });
}

test("s2 dock: hotkey, current app, Esc, drag side persists", async () => {
  const p = member.page;
  await p.goto("/_styx/app/idon/");
  await expect(tab(p)).toBeVisible();
  await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/idon\/$/); 
  await expect(tab(p)).toHaveAttribute("aria-expanded", "false");
  await p.keyboard.press("Alt+Shift+S");
  await expect(dock(p)).toBeVisible();
  await dockHasFocus(p);
  await expect(tab(p)).toHaveAttribute("aria-expanded", "true");
  await expect(dock(p).getByRole("link", { name: /Idon/ })).toHaveAttribute("aria-current", "page");
  await p.keyboard.press("Escape");
  await expect(dock(p)).toBeHidden();
  await expect(tab(p)).toBeFocused();
  await p.keyboard.press("Alt+Shift+S");
  await expect(dock(p)).toBeVisible();
  await dockHasFocus(p);
  for (const vp of [{ w: 1440, h: 900 }, { w: 390, h: 844 }]) {
    await p.setViewportSize({ width: vp.w, height: vp.h });
    for (const theme of ["light", "dark"] as const) {
      await p.evaluate((t) => { localStorage.setItem("theme", t); document.documentElement.classList.toggle("dark", t === "dark"); }, theme);
      await dockShots(p, `${vp.w}-${theme}`);
    }
  }
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.evaluate(() => { localStorage.setItem("theme", "light"); document.documentElement.classList.remove("dark"); });
  await p.keyboard.press("Escape");
  await expect(dock(p)).toBeHidden();

  // CDP mouse events follow the hit-test into the iframe (a real browser keeps a pressed mouse on the
  // parent document); take the frame out of hit-testing so the synthetic drag behaves like one.
  await p.evaluate(() => { document.querySelector("iframe")!.style.pointerEvents = "none"; });
  const box = (await tab(p).boundingBox())!;
  await p.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await p.mouse.down();
  await p.mouse.move(60, box.y + 40, { steps: 10 });
  await p.mouse.move(20, box.y + 40, { steps: 5 });
  await p.mouse.up();
  await expect.poll(() => p.evaluate(() => JSON.parse(localStorage.getItem("styx.ferry") ?? "{}").side)).toBe("left");
  await p.reload();
  await expect.poll(async () => (await tab(p).boundingBox())!.x).toBeLessThan(720);
});

test("s2b Esc closes a hotkey-opened dock even when the frame held focus", async () => {
  const p = member.page;
  await p.goto("/_styx/app/idon/");
  await expect.poll(() => frameOf(p)?.url() ?? "", { timeout: 30_000 }).toMatch(/\/idon\/$/);
  await frameOf(p)!.evaluate(() => { document.body.tabIndex = 0; document.body.focus(); });
  await p.keyboard.press("Alt+Shift+S");
  await expect(dock(p)).toBeVisible();
  await dockHasFocus(p);
  await p.keyboard.press("Escape");
  await expect(dock(p)).toBeHidden({ timeout: 3000 });
  await expect(tab(p)).toBeFocused();
});

test("s3 focus swap clears root service workers; exit clears styx_svc", async () => {
  const p = member.page;
  await p.goto("/_styx/app/sonarr/");
  await tab(p).click();
  await dock(p).getByRole("link", { name: /Focusapp(?! Two)/ }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/focusapp\/$/);
  // The focus app registers its root-scoped worker inside the frame.
  await expect.poll(() => p.evaluate(async () => (await navigator.serviceWorker.getRegistrations()).length),
    { timeout: 30_000 }).toBeGreaterThan(0);

  // The shell unregisters root workers before it mounts the next frame: count them the moment the
  // iframe appears (the new app has not run yet, so it cannot have re-registered).
  await member.ctx.addInitScript(() => {
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
  await expect(p.getByRole("link", { name: "Open Focusapp Two" })).toContainText(/Opens on its own/);
  await expect(p.getByRole("link", { name: "Open Focusapp Two" }).locator("..")).toHaveClass(/ring-obol/);
  await p.getByRole("link", { name: "Exit Focusapp Two" }).click();
  await expect.poll(async () => (await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);
  await endHomeWhileFocused(p);
  await p.goto("/");
  await expect(p.getByRole("link", { name: "Open Focusapp Two" })).toBeVisible();
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);
});

test("s4 cross-site open needs a click and sets no cookie", async () => {
  const r = await member.ctx.request.get("/_styx/open/focusapp", { headers: { "Sec-Fetch-Site": "cross-site" }, maxRedirects: 0 });
  expect(r.status()).toBe(200);
  expect(r.headers()["set-cookie"] ?? "").not.toContain("styx_svc");
  const html = await r.text();
  expect(html).toMatch(/Open focusapp/i);
  expect(html).not.toMatch(/<form/i);
  expect(html).toContain('href="/_styx/open/focusapp"');
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);

  const p = member.page;
  const missing = await member.ctx.request.get("/_styx/open/focusapp", { maxRedirects: 0 });
  expect(missing.status()).toBe(200); // no Sec-Fetch-Site header from a bare client: also unconfirmed
  await p.route("**/_styx/open/focusapp?confirm", (rt) => rt.fulfill({ status: 200, contentType: "text/html", body: html }));
  await p.goto("/_styx/open/focusapp?confirm");
  await p.setViewportSize({ width: 1440, height: 900 });
  await p.screenshot({ path: `${SHOTS}/focus-confirm-1440-light.png` });
  await p.unroute("**/_styx/open/focusapp?confirm");
  await p.getByRole("link", { name: "Open focusapp" }).click();
  await expect(p).toHaveURL(/\/_styx\/app\/focusapp\/$/);
  await p.goto("/_styx/exit?next=/");
});

// PRODUCT BUG (reported): Chromium fires no `load` event for an iframe blocked by CSP frame-ancestors,
// and use-frame-sync only checks isFrameBlocked() on load, so the shell shows a blank frame, not the card.
test("s5 frame-blocking app gets the blocked card", async () => {
  test.fail();
  const p = member.page;
  await p.goto("/_styx/app/frameblock/");
  await expect(p.getByRole("heading", { name: "Frameblock can't run inside Styx" })).toBeVisible({ timeout: 30_000 });
  const link = p.getByRole("link", { name: "Open Frameblock on its own" });
  await expect(link).toHaveAttribute("href", "/frameblock/");
  await p.screenshot({ path: `${SHOTS}/blocked-frame-1440-light.png` });
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

/** Polish screenshots: <screen>-<width>-<theme>.png at 1440x900 and 390x844, light and dark. */
test("s8 polish screenshots", async ({ browser }) => {
  test.setTimeout(300_000);
  const anon = await browser.newContext();
  const login = await anon.newPage();
  const m = member.page;
  const a = admin.page;
  const theme = async (p: Page, t: "light" | "dark") => {
    await p.evaluate((v) => localStorage.setItem("theme", v), t);
    await p.emulateMedia({ colorScheme: t });
  };
  const shot = async (p: Page, name: string, w: number, t: string) => {
    await p.waitForTimeout(500); // let transitions settle
    await p.screenshot({ path: `${SHOTS}/${name}-${w}-${t}.png` });
  };
  const sizes = [{ w: 1440, h: 900 }, { w: 390, h: 844 }];
  const themes = ["light", "dark"] as const;
  const each = async (fn: (w: number, t: "light" | "dark") => Promise<void>) => {
    for (const sz of sizes) for (const t of themes) {
      for (const p of [login, m, a]) await p.setViewportSize({ width: sz.w, height: sz.h });
      await fn(sz.w, t);
    }
  };

  await login.goto("/login");
  await each(async (w, t) => {
    await theme(login, t);
    await login.goto("/login");
    await expect(login.locator("#username")).toBeVisible();
    await shot(login, "login", w, t);
  });

  // Shell with Sonarr and the dock open.
  await each(async (w, t) => {
    await theme(m, t);
    await m.goto("/_styx/app/sonarr/");
    await m.evaluate((v) => document.documentElement.classList.toggle("dark", v === "dark"), t);
    await tab(m).click();
    await expect(dock(m)).toBeVisible();
    await shot(m, "shell-sonarr-dock", w, t);
    await m.keyboard.press("Escape");
  });

  // Confirm page for a cross-site focus open.
  const confirm = await (await m.context().request.get("/_styx/open/focusapp", { headers: { "Sec-Fetch-Site": "cross-site" } })).text();
  await each(async (w, t) => {
    await theme(m, t);
    await m.goto("/_styx/exit?next=/");
    await m.context().route("**/_styx/open/focusapp?confirm", (r) => r.fulfill({ status: 200, contentType: "text/html", body: confirm }));
    await m.goto("/_styx/open/focusapp?confirm");
    await shot(m, "focus-confirm", w, t);
    await m.context().unroute("**/_styx/open/focusapp?confirm");
  });

  // Home with a focused focus app.
  await m.goto("/_styx/open/focusapp");
  await each(async (w, t) => {
    await theme(m, t);
    await homeWhileFocused(m);
    await m.evaluate((v) => document.documentElement.classList.toggle("dark", v === "dark"), t);
    await shot(m, "home-focus", w, t);
    await m.unrouteAll({ behavior: "ignoreErrors" });
  });
  await m.goto("/_styx/exit?next=/");

  // Admin drawer on the rolled-back Broken app: consent dialog, then the rolled-back state.
  const drawer = async () => {
    await openSettings(a, "Services");
    await a.getByRole("button", { name: "Edit Broken app" }).click();
    const d = a.getByRole("dialog").filter({ has: a.locator("#ack-origin") });
    await expect(d.getByRole("region", { name: "Base path" })).toBeVisible();
    return d;
  };
  await each(async (w, t) => {
    await theme(a, t);
    const d = await drawer();
    await shot(a, "drawer-rolled-back", w, t);
    await d.getByRole("button", { name: "Try again" }).click();
    await expect(a.getByRole("dialog", { name: "Change Broken app's settings?" })).toBeVisible();
    await shot(a, "drawer-consent", w, t);
    await a.keyboard.press("Escape");
    await a.keyboard.press("Escape");
  });

  // Running stepper: start one apply, then capture all four variants inside its 90 s verify window.
  const d = await drawer();
  await d.getByRole("button", { name: "Try again" }).click();
  await a.getByRole("dialog", { name: "Change Broken app's settings?" }).getByRole("button", { name: "Restart Broken app and apply" }).click();
  await expect(a.getByRole("dialog").filter({ has: a.locator("#ack-origin") }).getByText(/Check it answers/)).toBeVisible();
  await each(async (w, t) => {
    await theme(a, t);
    await a.evaluate((v) => document.documentElement.classList.toggle("dark", v === "dark"), t);
    await shot(a, "drawer-running", w, t);
  });
  await anon.close();
});
