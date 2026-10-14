import { execFileSync } from "node:child_process";
import { expect, request, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";
import { ADMIN, SHOTS, STYX_COOKIES, eventually, jellyfinToken, openSettings, uiLogin } from "./helpers";

test.describe.configure({ mode: "serial" });

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:18080";
let ctx: BrowserContext;
let page: Page;

test.beforeAll(async ({ browser }) => {
  ctx = await browser.newContext();
  page = await ctx.newPage();
  await page.goto("/");
  const create = page.getByRole("button", { name: "Create admin" });
  const signIn = page.getByRole("button", { name: "Sign in" });
  await expect(create.or(signIn)).toBeVisible();
  if (await create.isVisible()) { // run alone (-g): the services spec did not bootstrap the admin
    await page.locator("#username").fill(ADMIN.username);
    await page.locator("#password").fill(ADMIN.password);
    await create.click();
    await expect(page).not.toHaveURL(/\/setup$/);
  } else {
    await uiLogin(page, ADMIN);
  }
  // After setup the SPA may land on /login while already signed in; re-enter from "/".
  await expect(page.getByRole("button", { name: "Settings", exact: true })).toBeVisible().catch(async () => {
    await page.goto("/");
    await expect(page.getByRole("button", { name: "Settings", exact: true })).toBeVisible();
  });
});
test.afterAll(async () => { await ctx?.close(); });

/**
 * Services -> Add from running container -> pick a preset -> Save and set base path. Returns with the
 * drawer in setup mode and the consent dialog already open (the drawer re-plans until the app has written its settings file).
 */
async function addFromContainer(container: string, preset: string, name: string, slug: string) {
  await openSettings(page, "Services");
  await page.getByRole("button", { name: "Add from running container" }).click();
  await page.getByRole("dialog", { name: "Running containers" })
    .getByRole("button", { name: `Expose ${container}` }).click();
  const form = page.getByRole("dialog").filter({ has: page.locator("#ack-origin") });
  if ((await form.locator("#preset").inputValue()) !== preset) await form.locator("#preset").selectOption(preset);
  await form.locator("#name").fill(name);
  await form.locator("#slug").fill(slug);
  await form.locator("#ack-origin").check();
  await form.getByRole("button", { name: "Save and set base path" }).click();
  await expect(page.getByText("Service saved. Next: set its base path.")).toBeVisible();
  const drawer = page.getByRole("dialog").filter({ has: page.getByRole("heading", { name: `Set up ${name}` }) });
  await expect(drawer.getByRole("region", { name: "Base path" })).toBeVisible({ timeout: 30_000 });
  await expect(drawer.getByRole("button", { name: /^Save/ })).toHaveCount(0);
  const consent = page.getByRole("dialog", { name: `Change ${name}'s settings?` });
  await expect(consent).toBeVisible({ timeout: 180_000 });
  return { drawer, consent };
}

async function openDrawer(name: string) {
  await openSettings(page, "Services");
  await page.getByRole("button", { name: `Edit ${name}` }).click();
  const drawer = page.getByRole("dialog").filter({ has: page.locator("#ack-origin") });
  await expect(drawer.getByRole("region", { name: "Base path" })).toBeVisible({ timeout: 30_000 });
  return drawer;
}

async function applyViaUi(name: string, tag: string, added: Awaited<ReturnType<typeof addFromContainer>>, newFile = false) {
  const { drawer, consent } = added;
  for (const h of ["File", "Setting", "Now", "After"]) await expect(consent.getByRole("columnheader", { name: h })).toBeVisible();
  if (newFile) {
    await expect(consent.getByText(/\(new file\)/).first()).toBeVisible();
    await expect(consent.getByText("(no file yet)").first()).toBeVisible();
  }
  await page.screenshot({ path: `${SHOTS}/mount-consent-${tag}.png` });
  await consent.getByRole("button", { name: `Restart ${name} and apply` }).click();
  return { drawer, consent };
}

test("m1 sonarr: adopted container, consent, managed base path", async () => {
  test.setTimeout(300_000);
  const { drawer, consent } = await addFromContainer("styx-e2e-sonarr-1", "sonarr", "Sonarr", "sonarr");
  for (const h of ["File", "Setting", "Now", "After"]) await expect(consent.getByRole("columnheader", { name: h })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/config/config.xml" })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/Config/UrlBase" })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/sonarr", exact: true })).toBeVisible();
  const row = consent.getByRole("row").filter({ hasText: "/config/config.xml" });
  await expect(row.getByRole("cell").nth(2)).toHaveText(/^\s*(\(not set\))?\s*$/);
  await page.screenshot({ path: `${SHOTS}/mount-consent-sonarr.png` });
  await consent.getByRole("button", { name: "Restart Sonarr and apply" }).click();

  const section = drawer.getByRole("region", { name: "Base path" });
  await expect(section.getByText("Base path set. Sonarr answers at /sonarr.")).toBeVisible({ timeout: 120_000 });
  for (const step of ["Back up settings", "Apply base path", "Restart app", "Check the app responds"])
    await expect(section.getByText(new RegExp(`^${step}\\s*\\(Done\\)`))).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-done-sonarr.png` });
  await eventually(async () => expect((await page.request.get("/sonarr/ping")).status()).toBe(200), 60_000);
  await drawer.getByRole("button", { name: "Done" }).click();
  await expect(drawer).toBeHidden();
});

test("m2 jellyfin: managed base path", async () => {
  test.setTimeout(420_000);
  // A fresh Jellyfin has no network.xml (only system.xml); Styx creates it, so no seeding here.
  const added = await addFromContainer("styx-e2e-jellyfin-1", "jellyfin", "Jellyfin", "jellyfin");
  const { drawer } = await applyViaUi("Jellyfin", "jellyfin", added, true);
  await expect(drawer.getByRole("region", { name: "Base path" }).getByText("Base path set. Jellyfin answers at /jellyfin."))
    .toBeVisible({ timeout: 180_000 });
  await page.screenshot({ path: `${SHOTS}/mount-done-jellyfin.png` });
  await eventually(async () => expect((await page.request.get("/jellyfin/health")).status()).toBe(200), 60_000);
  await drawer.getByRole("button", { name: "Done" }).click();
  await expect(drawer).toBeHidden();
});

test.describe("m3 jellyfin native client", () => {
  /** Fresh cookie-less context per probe; asserts it holds no Styx cookies before and after. */
  async function probe(path: string, headers: Record<string, string> = {}) {
    const anon = await request.newContext();
    try {
      const noStyxCookies = async () =>
        expect((await anon.storageState()).cookies.filter((c) => STYX_COOKIES.includes(c.name))).toEqual([]);
      await noStyxCookies();
      const res = await anon.get(`${BASE}${path}`, { headers, maxRedirects: 0, failOnStatusCode: false });
      const text = await res.text();
      await noStyxCookies();
      expect(res.headers()["set-cookie"] ?? "").not.toMatch(new RegExp(`(${STYX_COOKIES.join("|")})=`));
      return { res, text };
    } finally { await anon.dispose(); }
  }
  /** A Styx denial: 302 to /login (navigation) or Styx's own 401 JSON; never Jellyfin's answer. */
  async function expectStyxDenied(path: string, headers: Record<string, string> = {}) {
    const { res, text } = await probe(path, headers);
    if (res.status() === 302) expect(res.headers()["location"]).toContain("/login");
    else { expect(res.status()).toBe(401); expect(JSON.parse(text)).toMatchObject({ detail: "Not authenticated" }); }
  }

  test("native apps off: Styx login required; on: Jellyfin's own auth works", async () => {
    test.setTimeout(240_000);
    await expectStyxDenied("/jellyfin/System/Info", { Authorization: 'MediaBrowser Token="x"' });

    const drawer = await openDrawer("Jellyfin");
    await drawer.getByLabel("Allow native apps").click();
    await expect(drawer.getByText(/exposed to the internet/).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/mount-native-on.png` });
    await drawer.locator("#ack-origin").check();
    await drawer.getByRole("button", { name: "Save" }).click();
    await expect(drawer).toBeHidden();

    // Wait for Traefik to load the bypass routers (wizard was done in m2).
    let token = "";
    await eventually(async () => {
      const anon = await request.newContext();
      try { token = await jellyfinToken(anon, `${BASE}/jellyfin`); } finally { await anon.dispose(); }
      expect(token).toBeTruthy();
    }, 60_000);

    const me = await probe("/jellyfin/Users/Me", { Authorization: `MediaBrowser Token="${token}"` });
    expect(me.res.status()).toBe(200);
    expect(JSON.parse(me.text).Name).toBe("e2e");

    expect((await probe(`/jellyfin/System/Info?api_key=${token}`)).res.status()).toBe(200);

    await expectStyxDenied("/jellyfin/Users/Me", { Authorization: `Bearer ${token}` });
    await expectStyxDenied("/jellyfin/Users/Me");
  });
});

test("m4 rollback: broken app gets its settings back", async () => {
  test.setTimeout(240_000);
  const added = await addFromContainer("styx-e2e-brokenapp-1", "brokenapp", "Broken app", "brokenapp");
  const { drawer } = await applyViaUi("Broken app", "brokenapp", added);
  const section = drawer.getByRole("region", { name: "Base path" });
  await expect(section.getByText(/Styx put its settings back/)).toBeVisible({ timeout: 150_000 });
  await expect(section.getByText(/^Check the app responds\s*\(Failed\)/)).toBeVisible();
  await section.getByText("App log").click();
  await expect(section.locator("pre")).not.toBeEmpty();
  await expect(section.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(section.getByRole("button", { name: "Use focus mode instead" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-rollback-brokenapp.png` });

  const xml = execFileSync("docker", ["compose", "-p", "styx-e2e", "exec", "-T", "brokenapp", "cat", "/config/config.xml"],
    { encoding: "utf8" });
  expect(xml).toContain("<UrlBase></UrlBase>");
  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
});

test("m5 already set: no apply button", async () => {
  const drawer = await openDrawer("Sonarr");
  await expect(drawer.getByRole("region", { name: "Base path" })
    .getByText(/Base path (is set to \/sonarr|set\. Sonarr answers at \/sonarr)/)).toBeVisible();
  await expect(drawer.getByRole("button", { name: /Set base path/ })).toHaveCount(0);
});
