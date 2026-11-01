// Seeds the e2e stack with demo data (alice/bob/admin, styx.example.com, studio-pc ...) through the real API.
import { expect, type Browser, type BrowserContext } from "@playwright/test";
import { ADMIN, MEMBER, OUTSIDER, apiCall, ensureService, setupCode } from "../tests/helpers";
import { desktopHtml, type Scene } from "./scenes";

export const WORKSTATIONS = [
  { host: "studio-pc", ip: "10.0.0.21", scene: "code", gpu: "NVIDIA GeForce RTX 4070", cpu: "AMD Ryzen 7 7700X", cores: 16, ram: 65536, ds: "wayland", beat: true },
  { host: "render-box", ip: "10.0.0.22", scene: "render", gpu: "NVIDIA GeForce RTX 4090", cpu: "AMD Ryzen 9 7950X", cores: 32, ram: 131072, ds: "wayland", beat: true },
  { host: "gpu-lab", ip: "10.0.0.23", scene: "terminal", gpu: "AMD Radeon RX 7800 XT", cpu: "Intel Core i7-13700", cores: 24, ram: 32768, ds: "x11", beat: true },
  { host: "laptop-dev", ip: "10.0.0.24", scene: "files", gpu: "Intel Iris Xe", cpu: "Intel Core i5-1340P", cores: 16, ram: 16384, ds: "x11", beat: false },
] as const;

export type SeedOut = { wsIds: Record<string, string>; agents: Record<string, string> };

export async function render(browser: Browser, scene: Scene, w: number, h: number, quality: number, time = "10:42"): Promise<Buffer> {
  const p = await browser.newPage({ viewport: { width: w, height: h } });
  await p.setContent(desktopHtml(scene, w, h, time));
  const buf = await p.screenshot({ type: "jpeg", quality });
  await p.close();
  return buf;
}

/** POST from an anonymous context: fetch the CSRF cookie first, then send it back as the header. */
async function anonPost(browser: Browser, url: string, data: unknown) {
  const c = await browser.newContext();
  await c.request.get("/api/auth/csrf");
  const tok = (await c.cookies()).find((k) => k.name === "csrf_token")?.value ?? "";
  const r = await c.request.post(url, { data, headers: { "X-CSRF-Token": tok, "X-Styx-Client": "1" } });
  const out = { ok: r.ok(), text: await r.text() };
  await c.close();
  return out;
}

async function accept(browser: Browser, admin: BrowserContext, u: { username: string; password: string }, email: string) {
  const inv = await apiCall(admin, "POST", "/api/users/invites", { email, role: "user" });
  const r = await anonPost(browser, "/api/auth/accept-invite", { token: inv.token, ...u });
  expect(r.ok, `accept-invite ${r.text}`).toBeTruthy();
}

/** Idempotent-ish: skips users that already exist. Returns the logged-in admin context. */
export async function seed(browser: Browser): Promise<{ admin: BrowserContext; out: SeedOut }> {
  const admin = await browser.newContext();
  const base = admin.request;
  const need = await (await base.get("/api/auth/setup-required")).json();
  if (need.setup_required ?? need.required ?? need === true) {
    const csrf = await base.get("/api/auth/csrf");
    expect(csrf.ok()).toBeTruthy();
    const tok = (await admin.cookies()).find((c) => c.name === "csrf_token")?.value ?? "";
    const r = await base.post("/api/auth/setup", {
      data: { username: ADMIN.username, email: "admin@styx.example.com", password: ADMIN.password, setup_token: setupCode() },
      headers: { "X-CSRF-Token": tok, "X-Styx-Client": "1" },
    });
    expect(r.ok(), `setup ${await r.text()}`).toBeTruthy();
  } else {
    const p = await admin.newPage();
    await p.goto("/login");
    await p.locator("#username").fill(ADMIN.username);
    await p.locator("#password").fill(ADMIN.password);
    await p.getByRole("button", { name: "Sign in" }).click();
    await expect(p.getByRole("button", { name: "Log out" })).toBeVisible();
    await p.close();
  }
  const users = (await apiCall(admin, "GET", "/api/users")) as { username: string }[];
  if (!users.some((u) => u.username === MEMBER.username)) await accept(browser, admin, MEMBER, "alice@styx.example.com");
  if (!users.some((u) => u.username === OUTSIDER.username)) await accept(browser, admin, OUTSIDER, "bob@styx.example.com");

  // groups + membership
  const have = (await apiCall(admin, "GET", "/api/groups")) as { id: string; name: string }[];
  const gid: Record<string, string> = Object.fromEntries(have.map((g) => [g.name, g.id]));
  for (const [name, description] of [["media", "Media and entertainment apps"], ["engineering", "Developers and build tooling"], ["designers", "Creative workstations and render nodes"]]) {
    if (!gid[name]) gid[name] = (await apiCall(admin, "POST", "/api/groups", { name, description })).id;
  }
  const all = (await apiCall(admin, "GET", "/api/users")) as { id: string; username: string }[];
  const uid = (n: string) => all.find((u) => u.username === n)!.id;
  await apiCall(admin, "PUT", `/api/users/${uid("alice")}/groups`, { group_ids: [gid.media, gid.engineering, gid.designers] });
  await apiCall(admin, "PUT", `/api/users/${uid("bob")}/groups`, { group_ids: [gid.media] });

  // proxied services (real containers of the e2e stack, shown under friendly names)
  const web = { kind: "docker-local", container_port: 80, allowed_groups: ["media"] };
  await ensureService(admin, { slug: "jellyfin", name: "Jellyfin", preset_id: null, container: "styx-e2e-jellyfin-1", container_port: 8096, health_path: "/health" });
  await ensureService(admin, { slug: "sonarr", name: "Sonarr", preset_id: null, container: "styx-e2e-sonarr-1", container_port: 8989 });
  await ensureService(admin, { slug: "wiki", name: "Team wiki", ...web, container: "styx-e2e-whoami-1", allowed_groups: ["engineering"] });
  await ensureService(admin, { slug: "notes", name: "Notes", ...web, container: "styx-e2e-focusapp-1", mount_mode: "cookie-root", allowed_groups: [] });
  await ensureService(admin, { slug: "grafana", name: "Grafana", kind: "url", upstream_url: "http://whoami-url:80", container: null, container_port: null, allowed_groups: ["engineering"] });

  // workstations: real enroll -> heartbeat -> thumbnail through the public/agent API
  const out: SeedOut = { wsIds: {}, agents: {} };
  const existing = (await apiCall(admin, "GET", "/api/workstations")) as { id: string; hostname: string }[];
  for (const w of WORKSTATIONS) {
    // Re-runs: purge and re-register, because the agent token (needed for heartbeat/thumbnail) is only returned once.
    const old = existing.find((e) => e.hostname === w.host)?.id;
    if (old) await apiCall(admin, "DELETE", `/api/workstations/${old}?purge=true`);
    let id: string | undefined;
    let agent = "";
    if (!id) {
      const tok = await apiCall(admin, "POST", "/api/workstations/enroll-tokens");
      const r = await anonPost(browser, "/api/enroll/register", {
        token: tok.token, hostname: w.host, lan_ip: w.ip, display_server: w.ds, agent_version: "0.9.27",
        gpu_info: { model: w.gpu, vendor: w.gpu.split(" ")[0] },
        os_info: { distro: "ubuntu", pretty_name: "Ubuntu 24.04.1 LTS", kernel: "6.8.0-48-generic", cpu_model: w.cpu, cpu_cores: w.cores,
          memory_mb: w.ram, disk_total_gb: 1000, disk_free_gb: 640, mode: "seat" },
      });
      expect(r.ok, `register ${w.host}: ${r.text}`).toBeTruthy();
      const j = JSON.parse(r.text);
      id = j.workstation_id; agent = j.agent_token;
      if (w.beat) {
        const hb = await base.post("/api/agent/heartbeat", { headers: { Authorization: `Bearer ${agent}` }, data: { status: "online", lan_ip: w.ip } });
        expect(hb.ok(), `heartbeat ${await hb.text()}`).toBeTruthy();
        const jpg = await render(browser, w.scene, 640, 360, 72);
        const th = await base.post("/api/agent/thumbnail", { headers: { Authorization: `Bearer ${agent}` }, data: jpg });
        expect(th.status()).toBe(204);
      }
      await apiCall(admin, "PATCH", `/api/workstations/${id}`, { all_users: true, stream_settings: { encoder: "nvh265enc", framerate: 60, bitrate_kbps: 20000 } }).catch(() => {});
    }
    out.wsIds[w.host] = id!; out.agents[w.host] = agent;
  }
  return { admin, out };
}
