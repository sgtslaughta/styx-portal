import { execFileSync } from "node:child_process";
import { expect, request, test, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";
import { ADMIN, SHOTS, STYX_COOKIES, apiCall, eventually, jellyfinSeedNetworkXml, jellyfinToken, openSettings, uiLogin } from "./helpers";

test.describe.configure({ mode: "serial" });

const BASE = "http://127.0.0.1:18080";
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

/** Services -> Add from container -> pick a preset -> save. Leaves the Services panel open. */
async function addFromContainer(container: string, preset: string, name: string, slug: string) {
  await openSettings(page, "Services");
  await page.getByRole("button", { name: "Add from container" }).click();
  await page.getByRole("dialog", { name: "Running containers" })
    .getByRole("button", { name: `Expose ${container}` }).click();
  const form = page.getByRole("dialog").filter({ has: page.locator("#ack-origin") });
  if ((await form.locator("#preset").inputValue()) !== preset) await form.locator("#preset").selectOption(preset);
  await form.locator("#name").fill(name);
  await form.locator("#slug").fill(slug);
  await form.locator("#ack-origin").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toBeHidden();
  await expect(page.getByRole("listitem").filter({ hasText: `/${slug}` })).toBeVisible();
}

async function openDrawer(name: string) {
  await openSettings(page, "Services");
  await page.getByRole("button", { name: `Edit ${name}` }).click();
  const drawer = page.getByRole("dialog").filter({ has: page.locator("#ack-origin") });
  await expect(drawer.getByRole("region", { name: "Base path" })).toBeVisible({ timeout: 30_000 });
  return drawer;
}

const serviceId = async (slug: string): Promise<string> =>
  (await apiCall(ctx, "GET", "/api/services") as { id: string; slug: string }[]).find((s) => s.slug === slug)!.id;

async function applyViaUi(name: string, slug: string, tag: string) {
  const drawer = await openDrawer(name);
  await drawer.getByRole("button", { name: `Set base path to /${slug}` }).click();
  const consent = page.getByRole("dialog", { name: `Change ${name}'s settings?` });
  await expect(consent).toBeVisible();
  for (const h of ["File", "Setting", "Now", "After"]) await expect(consent.getByRole("columnheader", { name: h })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-consent-${tag}.png` });
  await consent.getByRole("button", { name: `Restart ${name} and apply` }).click();
  return { drawer, consent };
}

test("m1 sonarr: adopted container, consent, managed base path", async () => {
  test.setTimeout(300_000);
  await addFromContainer("styx-e2e-sonarr-1", "sonarr", "Sonarr", "sonarr");
  // Sonarr writes /config/config.xml on first boot.
  const id = await serviceId("sonarr");
  await expect.poll(async () => (await apiCall(ctx, "POST", `/api/services/${id}/mount/plan`)).method,
    { timeout: 180_000, intervals: [3000] }).toBe("config_file");

  const drawer = await openDrawer("Sonarr");
  await drawer.getByRole("button", { name: "Set base path to /sonarr" }).click();
  const consent = page.getByRole("dialog", { name: "Change Sonarr's settings?" });
  for (const h of ["File", "Setting", "Now", "After"]) await expect(consent.getByRole("columnheader", { name: h })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/config/config.xml" })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/Config/UrlBase" })).toBeVisible();
  await expect(consent.getByRole("cell", { name: "/sonarr", exact: true })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-consent-sonarr.png` });
  await consent.getByRole("button", { name: "Restart Sonarr and apply" }).click();

  const section = drawer.getByRole("region", { name: "Base path" });
  await expect(section.getByText("Base path set. Sonarr answers at /sonarr.")).toBeVisible({ timeout: 120_000 });
  for (const step of ["Back up settings", "Apply base path", "Restart app", "Check it answers"])
    await expect(section.getByText(step)).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-done-sonarr.png` });
  await eventually(async () => expect((await page.request.get("/sonarr/ping")).status()).toBe(200), 60_000);
});

test("m2 jellyfin: managed base path", async () => {
  test.setTimeout(420_000);
  await addFromContainer("styx-e2e-jellyfin-1", "jellyfin", "Jellyfin", "jellyfin");
  const id = await serviceId("jellyfin");
  // network.xml only exists once Jellyfin has saved network settings.
  await expect(async () => { jellyfinSeedNetworkXml(); }).toPass({ timeout: 120_000, intervals: [3000] });
  await expect.poll(async () => (await apiCall(ctx, "POST", `/api/services/${id}/mount/plan`)).method,
    { timeout: 180_000, intervals: [3000] }).toBe("config_file");

  const { drawer } = await applyViaUi("Jellyfin", "jellyfin", "jellyfin");
  await expect(drawer.getByRole("region", { name: "Base path" }).getByText("Base path set. Jellyfin answers at /jellyfin."))
    .toBeVisible({ timeout: 180_000 });
  await page.screenshot({ path: `${SHOTS}/mount-done-jellyfin.png` });
  await eventually(async () => expect((await page.request.get("/jellyfin/health")).status()).toBe(200), 60_000);
});

test.describe("m3 jellyfin native client", () => {
  let anon: APIRequestContext;
  test.beforeAll(async () => { anon = await request.newContext(); });
  test.afterAll(async () => { await anon?.dispose(); });

  const get = (path: string, headers: Record<string, string> = {}) =>
    anon.get(`${BASE}${path}`, { headers, maxRedirects: 0, failOnStatusCode: false });
  const stolen = (h: Record<string, string>) =>
    Object.entries(h).filter(([k, v]) => k === "set-cookie" && STYX_COOKIES.some((c) => v.includes(`${c}=`)));

  test("native apps off: Styx login required; on: Jellyfin's own auth works", async () => {
    test.setTimeout(240_000);
    const closed = await get("/jellyfin/System/Info", { Authorization: 'MediaBrowser Token="x"' });
    expect([302, 401]).toContain(closed.status());

    const drawer = await openDrawer("Jellyfin");
    await drawer.getByLabel("Allow native apps").click();
    await expect(drawer.getByText(/exposed to the internet/).first()).toBeVisible();
    await page.screenshot({ path: `${SHOTS}/mount-native-on.png` });
    await drawer.locator("#ack-origin").check();
    await drawer.getByRole("button", { name: "Save" }).click();
    await expect(drawer).toBeHidden();

    // Wait for Traefik to load the bypass routers; sign in with no Styx cookies (wizard was done in m2).
    let token = "";
    await eventually(async () => { token = await jellyfinToken(anon, `${BASE}/jellyfin`); expect(token).toBeTruthy(); }, 60_000);

    const me = await get("/jellyfin/Users/Me", { Authorization: `MediaBrowser Token="${token}"` });
    expect(me.status()).toBe(200);
    expect((await me.json()).Name).toBe("e2e");
    expect(stolen(me.headers())).toEqual([]);

    const qs = await get(`/jellyfin/System/Info?api_key=${token}`);
    expect(qs.status()).toBe(200);
    expect(stolen(qs.headers())).toEqual([]);

    const bearer = await get("/jellyfin/Users/Me", { Authorization: `Bearer ${token}` });
    expect([302, 401]).toContain(bearer.status());
    expect(stolen(bearer.headers())).toEqual([]);
  });
});

test("m4 rollback: broken app gets its settings back", async () => {
  test.setTimeout(240_000);
  await addFromContainer("styx-e2e-brokenapp-1", "brokenapp", "Broken app", "brokenapp");
  const { drawer } = await applyViaUi("Broken app", "brokenapp", "brokenapp");
  const section = drawer.getByRole("region", { name: "Base path" });
  await expect(section.getByText(/Styx put its settings back/)).toBeVisible({ timeout: 150_000 });
  await expect(section.getByText("Check it answers")).toBeVisible();
  await section.getByText("App log").click();
  await expect(section.locator("pre")).not.toBeEmpty();
  await expect(section.getByRole("button", { name: "Try again" })).toBeVisible();
  await expect(section.getByRole("button", { name: "Use focus mode instead" })).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/mount-rollback-brokenapp.png` });

  const xml = execFileSync("docker", ["compose", "-p", "styx-e2e", "exec", "-T", "brokenapp", "cat", "/config/config.xml"],
    { encoding: "utf8" });
  expect(xml).toContain("<UrlBase></UrlBase>");
});

test("m5 already set: no apply button", async () => {
  const drawer = await openDrawer("Sonarr");
  await expect(drawer.getByRole("region", { name: "Base path" })
    .getByText(/Base path (is set to \/sonarr|set\. Sonarr answers at \/sonarr)/)).toBeVisible();
  await expect(drawer.getByRole("button", { name: /Set base path/ })).toHaveCount(0);
});
