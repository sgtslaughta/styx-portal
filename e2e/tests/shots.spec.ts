import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { ADMIN, MEMBER, SHOTS, apiCall, ensureService, eventually, isWhoami, openSettings, settled, uiLogin } from "./helpers";

// Polish screenshots: <screen>-<width>-<theme>.png at 1440x900 and 390x844, light and dark.
// Self-seeding: creates its own services (it only needs the users and group from the services spec).
test.describe.configure({ mode: "serial" });

const SIZES = [{ w: 1440, h: 900 }, { w: 390, h: 844 }];
const THEMES = ["light", "dark"] as const;
type Theme = (typeof THEMES)[number];
type Ctx = { ctx: BrowserContext; page: Page };
let admin: Ctx;
let member: Ctx;
let anon: Ctx;

test.beforeAll(async ({ browser }) => {
  const open = async (u?: typeof ADMIN): Promise<Ctx> => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    if (u) { await uiLogin(page, u); await expect(page.getByRole("button", { name: "Log out" })).toBeVisible(); }
    return { ctx, page };
  };
  [admin, member, anon] = [await open(ADMIN), await open(MEMBER), await open()];
  const focus = { kind: "docker-local", container: "styx-e2e-focusapp-1", container_port: 80, mount_mode: "cookie-root" };
  await ensureService(admin.ctx, { slug: "shotfocus", name: "Shot focus", ...focus });
  await ensureService(admin.ctx, { slug: "shotblock", name: "Shot blocked", kind: "docker-local", container: "styx-e2e-frameblock-1", container_port: 80 });
  await ensureService(admin.ctx, { slug: "shotwho", name: "Shot who", kind: "url", upstream_url: "http://whoami-url:80", container: null, container_port: null });
  await ensureService(admin.ctx, {
    slug: "shotsapp", name: "Shot app", preset_id: "brokenapp", container: "styx-e2e-brokenapp-1", health_path: "/", allowed_groups: [],
  });
  await eventually(async () => expect(isWhoami(await (await member.ctx.request.get("/shotwho/")).text())).toBe(true), 60_000);
});
test.afterAll(async () => { for (const c of [admin, member, anon]) await c?.ctx.close(); });

async function setSize(w: number, h: number) { for (const c of [admin, member, anon]) await c.page.setViewportSize({ width: w, height: h }); }
async function setTheme(p: Page, t: Theme) {
  await p.evaluate((v) => localStorage.setItem("theme", v), t); // read by the SPA and the shell on load
  await p.emulateMedia({ colorScheme: t });
}
/** Every size x theme combination; `fn` navigates and shoots. */
async function each(fn: (w: number, t: Theme, name: (screen: string) => string) => Promise<void>) {
  for (const sz of SIZES) for (const t of THEMES) {
    await setSize(sz.w, sz.h);
    await fn(sz.w, t, (screen) => `${SHOTS}/${screen}-${sz.w}-${t}.png`);
  }
}
const shotsId = async () => ((await apiCall(admin.ctx, "GET", "/api/services")) as { id: string; slug: string }[]).find((x) => x.slug === "shotsapp")!.id;

test("login", async () => {
  await anon.page.goto("/login");
  await each(async (_w, t, file) => {
    await setTheme(anon.page, t);
    await anon.page.goto("/login");
    await expect(anon.page.getByRole("button", { name: "Sign in" })).toBeVisible();
    await anon.page.screenshot({ path: file("login") });
  });
});

test("shell with the dock open", async () => {
  const p = member.page;
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    await p.goto("/_styx/app/shotwho/");
    const frame = p.locator("iframe");
    await expect(frame).toBeVisible();
    await p.keyboard.press("Alt+Shift+S");
    const dock = p.getByRole("dialog");
    await expect(dock.getByRole("link", { name: /Shot who/ })).toHaveAttribute("aria-current", "page");
    await settled(dock);
    await p.screenshot({ path: file("shell-dock") });
    await p.keyboard.press("Escape");
    await expect(dock).toBeHidden();
  });
});

test("blocked frame card", async () => {
  const p = member.page;
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    await p.goto("/_styx/app/shotblock/");
    await expect(p.getByRole("heading", { name: "Shot blocked can't run inside Styx" })).toBeVisible({ timeout: 30_000 });
    await expect(p.getByRole("link", { name: "Open Shot blocked on its own" })).toHaveAttribute("href", "/shotblock/");
    await p.screenshot({ path: file("blocked-frame") });
  });
});

test("focus confirm page", async () => {
  const p = member.page;
  const html = await (await member.ctx.request.get("/_styx/open/shotfocus", { headers: { "Sec-Fetch-Site": "cross-site" } })).text();
  expect(html).toContain('href="/_styx/open/shotfocus"');
  await p.route("**/_styx/open/shotfocus?confirm", (r) => r.fulfill({ status: 200, contentType: "text/html", body: html }));
  try {
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/_styx/open/shotfocus?confirm");
      await expect(p.getByRole("link", { name: "Open app" })).toBeVisible();
      await p.screenshot({ path: file("focus-confirm") });
    });
  } finally { await p.unroute("**/_styx/open/shotfocus?confirm"); }
});

test("home with a focused focus app", async () => {
  const p = member.page;
  await p.goto("/_styx/open/shotfocus");
  await expect(p).toHaveURL(/\/_styx\/app\/shotfocus\/$/);
  // While styx_svc is set "/" is the focus app's: serve the Styx SPA files without that cookie.
  await p.route((u) => !/^\/(api|_styx)\b/.test(u.pathname), async (route) => {
    const h = route.request().headers();
    const cookie = (h["cookie"] ?? "").split("; ").filter((c) => !c.startsWith("styx_svc=")).join("; ");
    await route.fulfill({ response: await route.fetch({ headers: { ...h, cookie } }) });
  });
  try {
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/");
      await expect(p.getByRole("link", { name: "Open Shot focus" })).toHaveAttribute("aria-current", "true");
      await expect(p.getByRole("link", { name: "Exit Shot focus" })).toBeVisible();
      await p.screenshot({ path: file("home-focus") });
    });
  } finally {
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await p.goto("/_styx/exit?next=/");
  }
});

test("service drawer: consent, running, rolled back (waits for the job to finish)", async () => {
  test.setTimeout(480_000);
  const p = admin.page;
  const drawer = async () => {
    await openSettings(p, "Services");
    await p.getByRole("button", { name: "Edit Shot app" }).click();
    const d = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
    await expect(d.getByRole("region", { name: "Base path" })).toBeVisible({ timeout: 30_000 });
    return d;
  };
  const consent = () => p.getByRole("dialog", { name: "Change Shot app's settings?" });

  await each(async (_w, t, file) => {
    await setTheme(p, t);
    const d = await drawer();
    await d.getByRole("button", { name: "Set base path to /shotsapp" }).click();
    await expect(consent()).toBeVisible();
    await settled(consent());
    await p.screenshot({ path: file("drawer-consent") });
    await p.keyboard.press("Escape");
    await expect(consent()).toBeHidden();
  });

  const d = await drawer();
  await d.getByRole("button", { name: "Set base path to /shotsapp" }).click();
  await consent().getByRole("button", { name: "Restart Shot app and apply" }).click();
  const region = d.getByRole("region", { name: "Base path" });
  await expect(region.getByText(/^Check the app responds/)).toBeVisible({ timeout: 60_000 });
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    await p.evaluate((v) => document.documentElement.classList.toggle("dark", v === "dark"), t);
    await expect(region.getByText(/^Check the app responds/)).toBeVisible();
    await p.screenshot({ path: file("drawer-running") });
  });

  // The app never answers: wait for the rollback so no job is left running.
  const id = await shotsId();
  await expect.poll(async () => (await apiCall(admin.ctx, "GET", `/api/services/${id}/mount/jobs/latest`)).state,
    { timeout: 300_000, intervals: [3000] }).toBe("rolled_back");
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    const dd = await drawer();
    await expect(dd.getByText(/Styx put its settings back/)).toBeVisible();
    await p.screenshot({ path: file("drawer-rolled-back") });
  });
});
