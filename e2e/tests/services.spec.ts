import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test";
import {
  ADMIN, MEMBER, OUTSIDER, STYX_COOKIES, apiCall, eventually, getNoRedirect, headerLines,
  isWhoami, openSettings, uiLogin, updateService,
} from "./helpers";
import { captureAll } from "./screens";

test.describe.configure({ mode: "serial" });

let admin: { ctx: BrowserContext; page: Page };
let member: { ctx: BrowserContext; page: Page };
let outsider: { ctx: BrowserContext; page: Page };

async function fresh(browser: Browser) {
  const ctx = await browser.newContext();
  return { ctx, page: await ctx.newPage() };
}

async function invite(page: Page, browser: Browser, u: { username: string; password: string }) {
  await openSettings(page, "Users");
  await page.getByRole("button", { name: "Generate invite" }).click();
  const url = (await page.locator("code", { hasText: "/accept-invite/" }).textContent())!.trim();
  const s = await fresh(browser);
  await s.page.goto(url);
  await s.page.locator("#username").fill(u.username);
  await s.page.locator("#password").fill(u.password);
  await s.page.locator("#password").press("Enter");
  await expect(s.page).toHaveURL(/\/$/);
  await expect(s.page.getByText(u.username, { exact: true })).toBeVisible();
  return s;
}

const echo = async (p: Page, path: string) => {
  const res = await p.request.get(path);
  return { status: res.status(), body: await res.text() };
};

test.afterAll(async () => {
  for (const s of [admin, member, outsider]) await s?.ctx.close();
});

test("a. admin bootstraps, creates group, users and membership", async ({ browser }) => {
  admin = await fresh(browser);
  const p = admin.page;
  await p.goto("/");
  await expect(p).toHaveURL(/\/setup$/);
  await p.locator("#username").fill(ADMIN.username);
  await p.locator("#password").fill(ADMIN.password);
  await p.getByRole("button", { name: "Create admin" }).click();
  await expect(p).not.toHaveURL(/\/setup$/);
  // App bug (reported): SetupWizard's `!setupRequired -> <Navigate to="/login">` wins the
  // race against its own nav("/"), so a freshly created admin lands on /login while
  // already signed in. Record it, then continue from "/".
  if (p.url().endsWith("/login")) {
    test.info().annotations.push({ type: "app-bug", description: "post-setup redirect lands on /login" });
    await p.goto("/");
  }
  await expect(p.getByRole("button", { name: "Settings", exact: true })).toBeVisible();

  await openSettings(p, "Groups");
  await p.locator("#group-name").fill("media");
  await p.locator("#group-desc").fill("Media apps");
  await p.getByRole("button", { name: "Add group" }).click();
  await expect(p.getByRole("listitem").filter({ hasText: "media" })).toContainText("0 members");

  member = await invite(p, browser, MEMBER);
  outsider = await invite(p, browser, OUTSIDER);

  await openSettings(p, "Users");
  await p.getByRole("row").filter({ hasText: MEMBER.username }).getByRole("button", { name: "More" }).click();
  await p.getByRole("menuitem", { name: /Groups/ }).click();
  const dlg = p.getByRole("dialog", { name: `Groups for ${MEMBER.username}` });
  await dlg.getByLabel("media").check();
  await dlg.getByRole("button", { name: "Save" }).click();
  await expect(dlg).toBeHidden();
  await openSettings(p, "Groups");
  await expect(p.getByRole("listitem").filter({ hasText: "media" })).toContainText("1 member");
});

test("b. admin adds a path-mode SSO service from a discovered container", async () => {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("button", { name: "Add from running container" }).first().click();
  const picker = p.getByRole("dialog", { name: "Running containers" });
  await expect(picker).toContainText("styx-e2e-whoami-1");
  // The shim narrows discovery to labelled containers; none of the live stack shows up.
  await expect(picker).not.toContainText("remote-access");
  await picker.getByRole("button", { name: "Expose styx-e2e-whoami-1" }).click();

  const form = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  await expect(form.locator("#kind")).toHaveValue("docker-local");
  await expect(form.locator("#cport")).toHaveValue("80");
  await form.locator("#name").fill("Whoami");
  await form.locator("#slug").fill("whoami");

  await form.getByText("Advanced", { exact: true }).click();
  // Every risk callout from spec §9 renders for its trigger.
  await expect(form.getByRole("alert").filter({ hasText: "Proxied apps share Styx's origin" })).toBeVisible();
  await form.locator("#mount").selectOption("cookie-root");
  await expect(form.getByRole("alert").filter({ hasText: "Takes over the root of the hostname" })).toBeVisible();
  await form.locator("#mount").selectOption("path");
  await form.locator("#auth").selectOption("app-native");
  await expect(form.getByRole("alert").filter({ hasText: "Styx does not authenticate this service" })).toBeVisible();
  await form.locator("#auth").selectOption("sso-with-bypass");
  await form.getByRole("button", { name: "Add bypass rule" }).click();
  await form.getByLabel("Bypass path prefix").fill("/whoami/x");
  await expect(form.getByRole("alert").filter({ hasText: "Requests matching /whoami/x are reachable from the internet WITHOUT Styx login" })).toBeVisible();
  await form.getByRole("button", { name: "Remove bypass rule 1" }).click();
  await form.locator("#auth").selectOption("sso");
  await form.getByLabel("Verify upstream TLS").click();
  await expect(form.getByRole("alert").filter({ hasText: "Upstream certificate is not verified" })).toBeVisible();
  await form.getByLabel("Verify upstream TLS").click();
  await expect(form.getByRole("alert").filter({ hasText: "Upstream certificate is not verified" })).toHaveCount(0);

  await form.getByLabel("media", { exact: true }).check();
  const save = form.getByRole("button", { name: "Save" });
  await expect(save).toBeDisabled(); // acknowledgement is mandatory
  await form.locator("#ack-origin").check();
  await save.click();
  await expect(form).toBeHidden();
  await expect(p.getByRole("listitem").filter({ hasText: "/whoami" })).toContainText("SSO");

  // Admin may open everything; wait for Traefik to load the new router.
  await eventually(async () => expect(isWhoami((await echo(p, "/whoami/")).body)).toBe(true));
});

test("c. member opens the tile; upstream sees identity headers but no Styx cookies", async () => {
  const p = member.page;
  await member.ctx.addCookies([{ name: "app_pref", value: "keep-me", url: "http://127.0.0.1:18080" }]);
  await p.goto("/");
  // Identity headers are opt-in per service.
  await updateService(admin.ctx, "whoami", { pass_identity: true });
  const plain = await apiCall(admin.ctx, "POST", "/api/services", {
    name: "Plain", slug: "plain", kind: "url", upstream_url: "http://whoami-url:80", mount_mode: "path", auth_mode: "sso",
    allowed_groups: ["media"],
  });
  try {
    const tile = p.getByRole("link", { name: "Open Whoami" });
    await expect(tile).toBeVisible();
    await expect(tile).toHaveAttribute("href", "/_styx/app/whoami/");
    const cookieNames = (await member.ctx.cookies()).map((c) => c.name);
    expect(cookieNames).toEqual(expect.arrayContaining(["styx_proxy", "csrf_token", "app_pref"]));

    await tile.click();
    // First open asks where to open; stay in this tab, without remembering (shell.spec expects the prompt too).
    const dlg = p.getByRole("dialog", { name: "Open Whoami" });
    await dlg.getByRole("checkbox", { name: "Remember for all apps" }).uncheck();
    await dlg.getByRole("button", { name: "Open here" }).click();
    await p.waitForURL(/\/_styx\/app\/whoami\/$/);
    // The shell renders the app in an iframe.
    const app = p.frameLocator("iframe");
    await eventually(async () => expect(isWhoami(await app.locator("body").innerText())).toBe(true));
    const body = await app.locator("body").innerText();
    expect(body).toMatch(/^GET \/whoami\/ HTTP/m);
    const cookies = headerLines(body, "Cookie").join("; ");
    for (const name of STYX_COOKIES) expect(cookies).not.toContain(`${name}=`);
    expect(cookies).toContain("app_pref=keep-me");
    expect(headerLines(body, "X-Styx-User")).toEqual([MEMBER.username]);
    expect(headerLines(body, "X-Styx-Groups")).toEqual(["media"]);

    // Client-supplied identity headers are replaced, not appended.
    const spoof = await p.request.get("/whoami/", {
      headers: { "X-Styx-User": "root", "X-Styx-Groups": "admins", "X-authentik-username": "root" },
    });
    const sb = await spoof.text();
    expect(headerLines(sb, "X-Styx-User")).toEqual([MEMBER.username]);
    expect(headerLines(sb, "X-Styx-Groups")).toEqual(["media"]);
    expect(headerLines(sb, "X-Authentik-Username").filter(Boolean)).toEqual([]);

    // A service without pass_identity gets no identity headers at all.
    const sl = (plain as Svc).slug;
    await eventually(async () => expect(isWhoami((await echo(p, `/${sl}/`)).body)).toBe(true));
    const pb = (await echo(p, `/${sl}/`)).body;
    expect(headerLines(pb, "X-Styx-User")).toEqual([]);
    expect(headerLines(pb, "X-Styx-Groups")).toEqual([]);
  } finally {
    await apiCall(admin.ctx, "DELETE", `/api/services/${(plain as Svc).id}`);
  }
});

test("d. non-member: no tile, direct access denied", async () => {
  const p = outsider.page;
  await p.goto("/");
  await expect(p.getByRole("button", { name: "Settings", exact: true })).toBeVisible();
  await expect(p.getByRole("link", { name: "Open Whoami" })).toHaveCount(0);
  const res = await p.goto("/whoami/");
  expect(res!.status()).toBe(403);
  const body = await res!.text();
  expect(isWhoami(body)).toBe(false);
  expect(body).toContain("No access"); // Styx page, not raw JSON
});

test("e. anonymous is sent to login with a safe next, and lands back on the app", async ({ browser }) => {
  const anon = await fresh(browser);
  const raw = await getNoRedirect(anon.ctx.request, "/whoami/", { Accept: "text/html" });
  expect(raw.status()).toBe(302);
  expect(raw.headers()["location"]).toBe("http://127.0.0.1:18080/login?next=/whoami/");
  const xhr = await getNoRedirect(anon.ctx.request, "/whoami/", { Accept: "application/json" });
  expect(xhr.status()).toBe(401);

  await anon.page.goto("/whoami/");
  await expect(anon.page).toHaveURL(/\/login\?next=\/whoami\/$/);
  await anon.page.locator("#username").fill(MEMBER.username);
  await anon.page.locator("#password").fill(MEMBER.password);
  await anon.page.getByRole("button", { name: "Sign in" }).click();
  await anon.page.waitForURL("http://127.0.0.1:18080/whoami/");
  expect(isWhoami(await anon.page.locator("body").innerText())).toBe(true);
  await anon.ctx.close();
});

test("f. internal auth-check endpoints are not routed by Traefik", async () => {
  for (const path of ["/internal/services/whoami/auth-check", "/internal/workstations/x/auth-check", "/internal/instances/x/auth-check",
    "/internal/strip", "/internal/services/whoami/strip"]) {
    const res = await getNoRedirect(member.ctx.request, path, { "X-Forwarded-Uri": "/whoami/" });
    const body = await res.text();
    // Not the backend: the SPA catch-all (index.html) or a 404, never an auth decision.
    expect([200, 404], path).toContain(res.status());
    expect(res.headers()["x-styx-user"], path).toBeUndefined();
    if (res.status() === 200) expect(body, path).toContain('<div id="root">');
  }
});

test("g. slug boundary: /whoamix and /assets never reach whoami", async () => {
  const p = member.page;
  const sib = await echo(p, "/whoamix");
  expect(isWhoami(sib.body)).toBe(false);
  expect(sib.body).toContain('<div id="root">');
  const bare = await echo(p, "/whoami");
  expect(isWhoami(bare.body)).toBe(true);
  await p.goto("/");
  const asset = await p.locator("script[src^='/assets/']").first().getAttribute("src");
  const a = await p.request.get(asset!);
  expect(a.status()).toBe(200);
  expect(a.headers()["content-type"]).toContain("javascript");
});

test("h. cookie-root service: enter, takeover, Styx API via X-Styx-Client, exit", async () => {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("button", { name: "Add service" }).click();
  const form = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  await form.locator("#name").fill("Echo Root");
  await form.locator("#slug").fill("echoroot");
  await form.locator("#upstream").fill("http://whoami-url:80");
  await form.getByText("Advanced", { exact: true }).click();
  await form.locator("#mount").selectOption("cookie-root");
  await form.getByLabel("media", { exact: true }).check();
  await form.locator("#ack-origin").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toBeHidden();
  // A cookie-root router flips /api gating; give Traefik time to load it.
  await eventually(async () => {
    const r = await p.request.get("/api/auth/me", { headers: { "X-Styx-Client": "1" } });
    expect(r.ok()).toBe(true);
  });

  await updateService(admin.ctx, "echoroot", { pass_identity: true });

  const m = member.page;
  // Focus open: same-origin navigation sets styx_svc, then lands in the shell.
  await m.goto("/_styx/open/echoroot");
  await expect(m).toHaveURL("http://127.0.0.1:18080/_styx/app/echoroot/");
  const app = m.frameLocator("iframe");
  // Traefik may not have loaded the new cookie-root router yet: reload the shell until it answers.
  await eventually(async () => {
    await m.reload();
    expect(isWhoami(await app.locator("body").innerText({ timeout: 3000 }))).toBe(true);
  });
  const body = await app.locator("body").innerText();
  expect(body).toContain("Name: whoami-url");
  for (const name of STYX_COOKIES) expect(headerLines(body, "Cookie").join(";")).not.toContain(`${name}=`);
  expect(headerLines(body, "X-Styx-User")).toEqual([MEMBER.username]);

  // Takeover: with styx_svc set, a top-level GET / is the app, not the Styx SPA.
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(true);
  const root = await member.ctx.request.get("/");
  const rootBody = await root.text();
  expect(isWhoami(rootBody)).toBe(true);
  expect(rootBody).not.toContain('<div id="root">');

  const fromPage = await m.evaluate(async () => {
    const styx = await fetch("/api/auth/me", { headers: { "X-Styx-Client": "1" } });
    const app = await fetch("/api/anything");
    return { styx: styx.status, me: await styx.json().catch(() => null), app: await app.text() };
  });
  expect(fromPage.styx).toBe(200);
  expect(fromPage.me?.username).toBe(MEMBER.username);
  expect(fromPage.app).toMatch(/^GET \/api\/anything HTTP/m);

  await m.goto("/_styx/exit");
  await expect(m).toHaveURL("http://127.0.0.1:18080/");
  await expect(m.getByRole("link", { name: "Open Whoami" })).toBeVisible();
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);
  // After exit, / serves Styx again.
  const after = await (await member.ctx.request.get("/")).text();
  expect(isWhoami(after)).toBe(false);
  expect(after).toContain('<div id="root">');
});

test("h2. focus: top-level loads are wrapped in the shell; stale old-format cookie is not focus", async () => {
  const m = member.page;
  await m.goto("/_styx/open/echoroot");
  await expect(m).toHaveURL("http://127.0.0.1:18080/_styx/app/echoroot/");
  // A plain top-level load while the cookie is set lands in the shell (dock reachable), app framed.
  await eventually(async () => {
    await m.goto("/");
    await expect(m).toHaveURL(/\/_styx\/app\/echoroot\/$/);
    expect(isWhoami(await m.frameLocator("iframe").locator("body").innerText({ timeout: 3000 }))).toBe(true);
  });
  await expect(m.getByRole("button", { name: "Open the Styx menu (Alt+Shift+S)" })).toBeVisible();
  await m.goto("/_styx/exit");
  expect((await member.ctx.cookies()).some((c) => c.name === "styx_svc")).toBe(false);

  // Cookie from before instance binding (or a deleted/re-created service): Styx home, not the app.
  await member.ctx.addCookies([{ name: "styx_svc", value: "echoroot", url: "http://127.0.0.1:18080" }]);
  await m.goto("/");
  await expect(m.getByRole("link", { name: "Open Whoami" })).toBeVisible();
  expect(isWhoami(await (await member.ctx.request.get("/")).text())).toBe(false);
  await m.goto("/_styx/exit");
});

test("i. bypass rule: only the exact prefix on a segment boundary skips login", async ({ browser }) => {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("button", { name: "Edit Whoami" }).click();
  const form = p.getByRole("dialog").filter({ has: p.locator("#ack-origin") });
  await form.getByText("Advanced", { exact: true }).click();
  await form.locator("#auth").selectOption("sso-with-bypass");
  await form.getByRole("button", { name: "Add bypass rule" }).click();
  await form.getByLabel("Bypass path prefix").fill("/whoami/api");
  await expect(form.getByRole("alert").filter({ hasText: "Requests matching /whoami/api are reachable" })).toBeVisible();
  await form.locator("#ack-origin").check();
  await form.getByRole("button", { name: "Save" }).click();
  await expect(form).toBeHidden();

  const anon = await fresh(browser);
  const req = anon.ctx.request;
  await eventually(async () => {
    const ok = await getNoRedirect(req, "/whoami/api/x");
    expect(ok.status()).toBe(200);
    expect(await ok.text()).toMatch(/^GET \/whoami\/api\/x HTTP/m);
  });
  for (const path of ["/whoami/api%2f..%2fadmin", "/whoami/api%2F..%2Fadmin", "/whoami/apix",
    "/whoami/api/../admin", "/whoami/admin"]) {
    const r = await getNoRedirect(req, path);
    expect(isWhoami(await r.text()), path).toBe(false);
    expect([302, 400, 401, 404], `${path} -> ${r.status()}`).toContain(r.status());
  }
  await anon.ctx.close();
});

test("k. screenshots of the new admin screens", async () => {
  test.setTimeout(240_000);
  await captureAll(admin.page, member.page);
});

test("j. disabling a service denies members within one route refresh", async () => {
  const p = admin.page;
  await openSettings(p, "Services");
  await p.getByRole("switch", { name: "Enable Whoami" }).click();
  await expect(p.getByRole("switch", { name: "Enable Whoami" })).not.toBeChecked();
  const t0 = Date.now();
  await eventually(async () => expect(isWhoami((await echo(member.page, "/whoami/")).body)).toBe(false), 10_000);
  test.info().annotations.push({ type: "deny-latency-ms", description: String(Date.now() - t0) });
  await member.page.goto("/");
  await expect(member.page.getByRole("link", { name: "Open Echo Root" })).toHaveAttribute("href", "/_styx/open/echoroot");
  await expect(member.page.getByRole("link", { name: "Open Whoami" })).toHaveCount(0);
  // The bypass prefix dies with the service too.
  expect(isWhoami((await echo(member.page, "/whoami/api/x")).body)).toBe(false);
});

test("cleanup: authenticated API still healthy", async () => {
  const svcs = await apiCall(admin.ctx, "GET", "/api/services");
  expect(svcs.map((s: { slug: string }) => s.slug).sort()).toEqual(["echoroot", "whoami"]);
});
