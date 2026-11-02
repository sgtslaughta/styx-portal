import { execFileSync } from "node:child_process";
import { expect, type Locator, type APIRequestContext, type BrowserContext, type Page } from "@playwright/test";

export const ADMIN = { username: "admin", password: "Styx-e2e-Admin-Quartz-Lantern-91" };
export const MEMBER = { username: "alice", password: "Styx-e2e-Member-Willow-Harbor-57" };
export const OUTSIDER = { username: "bob", password: "Styx-e2e-Outsider-Cobalt-Meadow-38" };
export const STYX_COOKIES = ["access_token", "refresh_token", "styx_proxy", "csrf_token", "styx_svc"];
export const SHOTS = "screenshots";

/** First-run setup code, read from the backend's data volume (POST /api/auth/setup needs it). */
export function setupCode(): string {
  return execFileSync("docker", ["compose", "-p", "styx-e2e", "exec", "-T", "backend", "cat", "/app/data/setup-token"],
    { stdio: "pipe" }).toString().trim();
}

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
    const btn = page.getByRole("button", { name: "Toggle theme" });
    if (await btn.isVisible()) await btn.click();
    else { // phones: the toggle lives in the account menu
      await page.getByRole("button", { name: /Account menu/ }).click();
      await page.getByRole("menuitem", { name: "Toggle theme" }).click();
    }
  }
  expect(await page.evaluate(() => localStorage.getItem("theme"))).toBe(want);
  await expect(page.locator("html")).toHaveClass(want === "dark" ? /dark/ : /^(?!.*dark).*$/);
}

export async function waitHttp(req: APIRequestContext, url: string, ok = (s: number) => s < 400, timeout = 120_000) {
  await expect.poll(async () => (await req.get(url, { failOnStatusCode: false, maxRedirects: 0 }).catch(() => null))?.status() ?? 0,
    { timeout, intervals: [2000] }).toSatisfy(ok);
}

const JF_AUTH = 'MediaBrowser Client="e2e", Device="e2e", DeviceId="e2e-1", Version="1.0"';
/** Completes Jellyfin's startup wizard through Styx (needs Allow native apps on: every call carries
 *  `Authorization: MediaBrowser ...`, so it bypasses Styx login). Returns an access token. */
export async function jellyfinToken(req: APIRequestContext, base: string): Promise<string> {
  const headers = { Authorization: JF_AUTH };
  const user = { Name: "e2e", Password: "e2e-Jelly-Pass-42" };
  await req.post(`${base}/Startup/Configuration`, { headers, data: { UICulture: "en-US", MetadataCountryCode: "US", PreferredMetadataLanguage: "en" } });
  await req.get(`${base}/Startup/User`, { headers });
  await req.post(`${base}/Startup/User`, { headers, data: user });
  await req.post(`${base}/Startup/Complete`, { headers });
  const r = await req.post(`${base}/Users/AuthenticateByName`, { headers, data: { Username: user.Name, Pw: user.Password } });
  expect(r.ok(), `AuthenticateByName -> ${r.status()}`).toBeTruthy();
  return (await r.json()).AccessToken;
}

/** Jellyfin only writes config/network.xml once network settings are saved. Run once, after the
 *  service is up: waits for /health, completes the wizard from inside the container (the apps
 *  network is internal and the base path is not set yet, so Styx cannot reach it; skipped when the
 *  wizard is already done) and re-saves the network config so the file exists for the mount plan. */
export function jellyfinSeedNetworkXml(container = "jellyfin") {
  const script = String.raw`set -eu
A='${JF_AUTH}'; U=http://localhost:8096; J='Content-Type: application/json'
i=0; until curl -sf $U/health >/dev/null; do i=$((i+1)); [ $i -gt 60 ] && { echo "jellyfin /health never answered" >&2; exit 1; }; sleep 2; done
code=$(curl -s -o /dev/null -w '%{http_code}' $U/Startup/Configuration -H "Authorization: $A")
if [ "$code" = 200 ]; then
  curl -sSf -XPOST $U/Startup/Configuration -H "Authorization: $A" -H "$J" -d '{"UICulture":"en-US","MetadataCountryCode":"US","PreferredMetadataLanguage":"en"}'
  curl -sSf $U/Startup/User -H "Authorization: $A" >/dev/null
  curl -sSf -XPOST $U/Startup/User -H "Authorization: $A" -H "$J" -d '{"Name":"e2e","Password":"e2e-Jelly-Pass-42"}'
  curl -sSf -XPOST $U/Startup/Complete -H "Authorization: $A"
fi
T=$(curl -sSf -XPOST $U/Users/AuthenticateByName -H "Authorization: $A" -H "$J" -d '{"Username":"e2e","Pw":"e2e-Jelly-Pass-42"}' | sed 's/.*"AccessToken":"\([^"]*\)".*/\1/')
curl -sSf $U/System/Configuration/network -H "X-Emby-Token: $T" > /tmp/n.json
curl -sSf -XPOST $U/System/Configuration/network -H "X-Emby-Token: $T" -H "$J" --data @/tmp/n.json`;
  try {
    execFileSync("docker", ["compose", "-p", "styx-e2e", "exec", "-T", container, "sh", "-c", script], { stdio: "pipe" });
  } catch (e) {
    const err = e as { stderr?: Buffer; message: string };
    throw new Error(`jellyfin seeding failed: ${err.stderr?.toString() || err.message}`);
  }
}

export type Svc = Record<string, unknown> & { id: string; slug: string };

/** PUT replaces every field: GET the service, merge the patch, PUT it back. */
export async function updateService(ctx: BrowserContext, slug: string, patch: Record<string, unknown>) {
  const all: Svc[] = await apiCall(ctx, "GET", "/api/services");
  const { id, slug: _slug, ...cur } = all.find((x) => x.slug === slug)!;
  const writable = Object.fromEntries(Object.entries(cur).filter(([k]) =>
    !["health_status", "health_checked_at", "mount_managed", "upstream_fallback", "created_at", "updated_at"].includes(k)));
  return apiCall(ctx, "PUT", `/api/services/${id}`, { ...writable, ...patch });
}

/** Create a service through the API, or update it when the slug already exists (re-runnable). */
export async function ensureService(ctx: BrowserContext, svc: Record<string, unknown> & { slug: string }) {
  const all: Svc[] = await apiCall(ctx, "GET", "/api/services");
  if (all.some((x) => x.slug === svc.slug)) { const { slug, ...rest } = svc; return updateService(ctx, slug, rest); }
  return apiCall(ctx, "POST", "/api/services", {
    icon: null, kind: "docker-local", container_port: 80, mount_mode: "path", auth_mode: "sso", bypass_rules: [],
    allowed_groups: ["media"], verify_tls: true, health_path: null, preset_id: null, enabled: true,
    pass_identity: false, frame_ok: true, acknowledged_origin: true, ...svc,
  });
}

/** Wait until the element has stopped moving (spring/slide-in finished): same box on 3 consecutive samples. */
export async function settled(loc: Locator) {
  let last = "";
  let same = 0;
  await expect.poll(async () => {
    const now = JSON.stringify(await loc.boundingBox());
    same = now === last ? same + 1 : 0;
    last = now;
    return same;
  }, { intervals: [60], timeout: 5000 }).toBeGreaterThanOrEqual(3);
}
