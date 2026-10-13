import { expect, test, type BrowserContext, type Locator, type Page } from "@playwright/test";
import { ADMIN, MEMBER, SHOTS, apiCall, ensureService, eventually, isWhoami, openSettings, settled, uiLogin } from "./helpers";
import { CHIP_JOBS, MOUNT_STATES, mockApi } from "./shots-mocks";

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
  await ensureService(admin.ctx, { slug: "shotattn", name: "Shot attention", kind: "docker-local", container: "styx-e2e-frameblock-1", container_port: 80 });
  await ensureService(admin.ctx, {
    slug: "shotjelly", name: "Shot Jelly", kind: "url", upstream_url: "http://whoami-url:80", container: null, container_port: null, preset_id: "jellyfin",
  });
  await eventually(async () => expect(isWhoami(await (await member.ctx.request.get("/shotwho/")).text())).toBe(true), 60_000);
});
test.afterAll(async () => { for (const c of [admin, member, anon]) await c?.ctx.close(); });

async function setSize(w: number, h: number) { for (const c of [admin, member, anon]) await c.page.setViewportSize({ width: w, height: h }); }
async function setTheme(p: Page, t: Theme) {
  await p.evaluate((v) => localStorage.setItem("theme", v), t); // read by the SPA and the shell on load
  await p.emulateMedia({ colorScheme: t, reducedMotion: "reduce" }); // no mid-transition frames in shots
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
  await anon.page.mouse.move(0, 0); // keep the pointer ripple out of the shots
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

// ---- Polish pass 2: the states that were missing from the shot set --------------------------------------------

const TAB = "Open the Styx menu (Alt+Shift+S)";
const setFerry = (p: Page, side: "left" | "right") => p.evaluate((v) => localStorage.setItem("styx.ferry", JSON.stringify({ side: v, y: 0.5 })), side);
/** A keyboard-driven focus, so :focus-visible matches for a programmatic focus(). */
async function kbFocus(p: Page, loc: Locator) { await p.keyboard.press("Tab"); await loc.focus(); await expect(loc).toBeFocused(); }
const svcId = async (slug: string) => ((await apiCall(admin.ctx, "GET", "/api/services")) as { id: string; slug: string }[]).find((x) => x.slug === slug)!.id;
/** Settings > Services > Edit <name>; resolves to the form drawer. */
async function editDrawer(name: string, region = true) {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("button", { name: `Edit ${name}` }).click();
  const d = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  if (region) await expect(d.getByRole("region", { name: "Base path" })).toBeVisible({ timeout: 30_000 });
  else await expect(d.locator("#name")).toBeVisible();
  await settled(d);
  return d;
}
/** Settings > Services > Add service, with a URL service filled in. */
async function addDrawer() {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("button", { name: "Add service" }).click();
  const d = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  await d.locator("#name").fill("Example");
  await d.locator("#slug").fill("example");
  await d.locator("#upstream").fill("https://192.168.1.10:8443");
  await settled(d);
  return d;
}

test("edge tab at rest and idle, both sides", async () => {
  test.setTimeout(240_000);
  const p = member.page;
  for (const side of ["left", "right"] as const) {
    await each(async (_w, t, file) => {
      await p.goto("/");
      await setFerry(p, side);
      await setTheme(p, t);
      await p.goto("/_styx/app/shotwho/");
      await expect(p.locator("iframe")).toBeVisible();
      const tab = p.getByRole("button", { name: TAB });
      await expect(tab).toBeVisible();
      await p.mouse.move(200, 200);
      await settled(tab);
      await p.screenshot({ path: file(`edge-tab-rest-${side}`) });
      await p.waitForTimeout(3800); // idle fade after 3s
      await p.screenshot({ path: file(`edge-tab-idle-${side}`) });
    });
  }
  await p.evaluate(() => localStorage.removeItem("styx.ferry"));
});

test("dock: focus app current, and on the left", async () => {
  const p = member.page;
  await p.goto("/_styx/open/shotfocus");
  await expect(p).toHaveURL(/\/_styx\/app\/shotfocus\/$/);
  try {
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/_styx/app/shotfocus/");
      await expect(p.locator("iframe")).toBeVisible();
      await p.keyboard.press("Alt+Shift+S");
      const dock = p.getByRole("dialog");
      await expect(dock.getByRole("link", { name: "Exit focus" })).toBeVisible();
      await settled(dock);
      await p.screenshot({ path: file("dock-focus") });
      await p.keyboard.press("Escape");
      await expect(dock).toBeHidden();
    });
  } finally { await p.goto("/_styx/exit?next=/"); }
  await p.evaluate(() => localStorage.setItem("styx.ferry", JSON.stringify({ side: "left", y: 0.5 })));
  try {
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/_styx/app/shotwho/");
      await expect(p.locator("iframe")).toBeVisible();
      await p.keyboard.press("Alt+Shift+S");
      const dock = p.getByRole("dialog");
      await expect(dock.getByRole("link", { name: /Shot who/ })).toHaveAttribute("aria-current", "page");
      await settled(dock);
      await p.screenshot({ path: file("dock-left") });
      await p.keyboard.press("Escape");
      await expect(dock).toBeHidden();
    });
  } finally { await p.evaluate(() => localStorage.removeItem("styx.ferry")); }
});

test("service form: mount mode, no-method hint, bypass error", async () => {
  test.setTimeout(240_000);
  const p = admin.page;
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    let d = await addDrawer();
    await d.getByText("Advanced", { exact: true }).click();
    await d.locator("#mount").scrollIntoViewIfNeeded();
    await p.screenshot({ path: file("form-mount-path") });
    await d.locator("#mount").selectOption("cookie-root");
    await d.locator("#mount").scrollIntoViewIfNeeded();
    await p.screenshot({ path: file("form-mount-focus") });
    // A preset that leaves the base path to the user shows the app's setting hint.
    await d.locator("#mount").selectOption("path");
    const presets = await d.locator("#preset option").evaluateAll((o) => (o as HTMLOptionElement[]).map((x) => x.value).filter(Boolean));
    for (const id of presets) {
      await d.locator("#preset").selectOption(id);
      if (await d.getByText(/^App setting:/).isVisible()) break;
    }
    await d.getByText("Access", { exact: true }).first().scrollIntoViewIfNeeded();
    await p.screenshot({ path: file("form-mount-hint") });
    await p.keyboard.press("Escape");
    await expect(d).toBeHidden();

    d = await addDrawer();
    await d.getByText("Advanced", { exact: true }).click();
    await d.locator("#auth").selectOption("sso-with-bypass");
    await d.getByRole("button", { name: "Add bypass rule" }).click();
    await d.getByLabel("Bypass path prefix").fill("api");
    await d.getByLabel("Bypass path prefix").blur();
    await d.getByLabel("Bypass path prefix").scrollIntoViewIfNeeded();
    await p.screenshot({ path: file("form-bypass-error") });
    await p.keyboard.press("Escape");
    await expect(d).toBeHidden();
  });
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    const d = await editDrawer("Shot blocked"); // docker-local with no managed method: the user sets the base path
    await expect(d.getByText(/in the app yourself, or use a preset/)).toBeVisible();
    await p.screenshot({ path: file("drawer-no-method") });
    await p.keyboard.press("Escape");
    const j = await editDrawer("Shot Jelly", false);
    await j.getByLabel("Allow native apps").click();
    await expect(j.getByText(/exposed to the internet/).first()).toBeVisible();
    await p.screenshot({ path: file("mount-native-on") });
    await p.keyboard.press("Escape");
  });
});

test("mount states: done, verified, running, failed, plan error, log open", async () => {
  test.setTimeout(300_000);
  const p = admin.page;
  const id = await svcId("shotsapp");
  const plan = new RegExp(`/api/services/${id}/mount/plan$`);
  const latest = new RegExp(`/api/services/${id}/mount/jobs/latest$`);
  try {
    for (const [name, st] of Object.entries(MOUNT_STATES)) {
      await p.unrouteAll({ behavior: "ignoreErrors" });
      await mockApi(p, "POST", plan, st.plan);
      if (st.job) await mockApi(p, "GET", latest, st.job); else await mockApi(p, "GET", latest, { detail: "No job" }, 404);
      await each(async (_w, t, file) => {
        await setTheme(p, t);
        const d = await editDrawer("Shot app");
        if (name === "log-open") await d.getByText("App log", { exact: true }).click();
        if (name === "running") await expect(d.getByRole("progressbar")).toBeVisible();
        await p.screenshot({ path: file(`mount-${name}`) });
        await p.keyboard.press("Escape");
      });
    }
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await mockApi(p, "POST", plan, { detail: "Docker did not answer in time." }, 502);
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      const d = await editDrawer("Shot app", false);
      await expect(d.getByText(/Couldn't check Shot app's settings/)).toBeVisible();
      await p.screenshot({ path: file("mount-plan-error") });
      await p.keyboard.press("Escape");
    });
  } finally { await p.unrouteAll({ behavior: "ignoreErrors" }); }
});

test("service rows with mount chips", async () => {
  const p = admin.page;
  const [a, b, c] = [await svcId("shotblock"), await svcId("shotattn"), await svcId("shotsapp")];
  try {
    await mockApi(p, "GET", new RegExp(`/api/services/${c}/mount/jobs/latest$`), MOUNT_STATES["log-open"].job);
    await mockApi(p, "GET", new RegExp(`/api/services/${a}/mount/jobs/latest$`), CHIP_JOBS.done);
    // "Base path set" reads the server-owned mount_managed flag: set it on the shotblock row only.
    await p.route((u) => u.pathname === "/api/services", async (route) => {
      if (route.request().method() !== "GET") return route.fallback();
      const res = await route.fetch();
      const rows = (await res.json()) as { id: string; mount_managed: boolean }[];
      return route.fulfill({ response: res, json: rows.map((r) => (r.id === a ? { ...r, mount_managed: true } : r)) });
    });
    await mockApi(p, "GET", new RegExp(`/api/services/${b}/mount/jobs/latest$`), CHIP_JOBS.failed);
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await openSettings(p, "Services");
      for (const chip of ["Base path set", "Rolled back", "Needs attention"]) await expect(p.getByText(chip, { exact: true }).first()).toBeVisible();
      await p.screenshot({ path: file("services-chips") });
    });
  } finally { await p.unrouteAll({ behavior: "ignoreErrors" }); }
});

test("empty states: services, discover, home tiles", async () => {
  test.setTimeout(240_000);
  const { page: p } = admin;
  try {
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await openSettings(p, "Services");
      await p.getByRole("button", { name: "Add from container" }).click();
      const dlg = p.getByRole("dialog", { name: "Running containers" });
      await expect(dlg).toBeVisible();
      await settled(dlg);
      await p.screenshot({ path: file("discover-list") });
      await p.keyboard.press("Escape");
    });
    await mockApi(p, "GET", "/api/services/discover", []);
    await mockApi(p, "GET", "/api/services", []);
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await openSettings(p, "Services");
      await expect(p.getByText("No services yet", { exact: true })).toBeVisible();
      await p.screenshot({ path: file("services-empty") });
      await p.getByRole("button", { name: "Pick a container" }).click();
      const dlg = p.getByRole("dialog", { name: "Running containers" });
      await expect(dlg.getByText(/No eligible containers/)).toBeVisible();
      await settled(dlg);
      await p.screenshot({ path: file("discover-empty") });
      await p.keyboard.press("Escape");
      await p.goto("/");
      await expect(p.getByText(/No services yet. Add one in/)).toBeVisible();
      await p.screenshot({ path: file("home-no-services-admin") });
    });
  } finally { await p.unrouteAll({ behavior: "ignoreErrors" }); }
  const m = member.page;
  await mockApi(m, "GET", "/api/services", []);
  try {
    await each(async (_w, t, file) => {
      await setTheme(m, t);
      await m.goto("/");
      await expect(m.getByRole("button", { name: "Log out" })).toBeVisible();
      await expect(m.getByText("No instances yet")).toBeVisible(); // the real empty state, not the skeleton
      await m.screenshot({ path: file("home-no-tiles-member") });
    });
  } finally { await m.unrouteAll({ behavior: "ignoreErrors" }); }
});

test("login: error, SSO providers, signing in", async () => {
  test.setTimeout(240_000);
  const p = anon.page;
  const fill = async () => { await p.locator("#username").fill("alice"); await p.locator("#password").fill("wrong-password-1"); };
  await p.goto("/login");
  try {
    await mockApi(p, "POST", "/api/auth/login", { detail: "Incorrect username or password" }, 401);
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/login");
      await fill();
      await p.getByRole("button", { name: "Sign in" }).click();
      await expect(p.locator("#login-error")).toBeVisible();
      await p.screenshot({ path: file("login-error") });
    });
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await mockApi(p, "GET", "/api/auth/oauth/providers", [
      { name: "authentik", display_label: "Authentik", icon_url: null }, { name: "github", display_label: "GitHub", icon_url: null }]);
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/login");
      await expect(p.getByRole("link", { name: "Continue with Authentik" })).toBeVisible();
      await p.screenshot({ path: file("login-sso") });
    });
    await p.unrouteAll({ behavior: "ignoreErrors" });
    await p.route((u) => u.pathname === "/api/auth/login", async (r) => { await new Promise((ok) => setTimeout(ok, 8000)); await r.abort().catch(() => {}); });
    await each(async (_w, t, file) => {
      await setTheme(p, t);
      await p.goto("/login");
      await fill();
      await p.getByRole("button", { name: /^Sign in$/ }).click();
      await expect(p.getByRole("button", { name: /Signing in/ })).toBeVisible();
      await p.screenshot({ path: file("login-signing-in") });
    });
  } finally { await p.unrouteAll({ behavior: "ignoreErrors" }); }
});

test("keyboard focus states", async () => {
  test.setTimeout(240_000);
  const m = member.page;
  const html = await (await member.ctx.request.get("/_styx/open/shotfocus", { headers: { "Sec-Fetch-Site": "cross-site" } })).text();
  await m.route("**/_styx/open/shotfocus?confirm", (r) => r.fulfill({ status: 200, contentType: "text/html", body: html }));
  try {
    await each(async (_w, t, file) => {
      await setTheme(m, t);
      await m.goto("/_styx/open/shotfocus?confirm");
      await kbFocus(m, m.getByRole("link", { name: "Open app" }));
      await m.screenshot({ path: file("focus-confirm-button") });
      await m.goto("/");
      await kbFocus(m, m.getByRole("link", { name: "Open Shot who" }));
      await m.screenshot({ path: file("focus-tile") });
      await m.goto("/_styx/app/shotwho/");
      await expect(m.locator("iframe")).toBeVisible();
      await m.keyboard.press("Alt+Shift+S");
      const dock = m.getByRole("dialog");
      await settled(dock);
      await kbFocus(m, dock.getByRole("link", { name: /Shot blocked/ }));
      await m.screenshot({ path: file("focus-dock-link") });
      await m.keyboard.press("Escape");
    });
  } finally { await m.unrouteAll({ behavior: "ignoreErrors" }); }
  const p = admin.page;
  await each(async (_w, t, file) => {
    await setTheme(p, t);
    const d = await editDrawer("Shot app");
    await kbFocus(p, d.locator("#preset"));
    await p.screenshot({ path: file("focus-drawer-select") });
    await p.keyboard.press("Escape");
  });
});

test("backend pages: service unavailable", async () => {
  const p = anon.page;
  await each(async (_w, t, file) => {
    await p.emulateMedia({ colorScheme: t });
    await p.goto("/api/service-unavailable");
    await expect(p.getByRole("heading", { name: "Service unavailable" })).toBeVisible();
    await p.evaluate(() => document.fonts.ready);
    await p.screenshot({ path: file("service-unavailable") });
  });
});
