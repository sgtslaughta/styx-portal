import { describe, test, expect, vi, beforeEach } from "vitest";
import { api, expiredLoginUrl } from "./client";

const lastCall = (): [string, RequestInit] => {
  const calls = (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;
  const c = calls[calls.length - 1];
  if (!c) throw new Error("fetch not called");
  return c;
};

describe("services api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  test("every request carries X-Styx-Client", async () => {
    await api.listServices();
    expect(lastCall()[1].headers).toMatchObject({ "X-Styx-Client": "1" });
  });

  test("setUserGroups sends group_ids", async () => {
    await api.setUserGroups("u1", ["g1"]);
    const [url, init] = lastCall();
    expect(url).toBe("/api/users/u1/groups");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ group_ids: ["g1"] });
  });

  test("setServiceEnabled picks enable/disable", async () => {
    await api.setServiceEnabled("s1", false);
    expect(lastCall()[0]).toBe("/api/services/s1/disable");
  });

  test("mount endpoints", async () => {
    await api.mountPlan("s1");
    expect(lastCall()[0]).toBe("/api/services/s1/mount/plan");
    expect(lastCall()[1].method).toBe("POST");
    await api.mountApply("s1", true);
    expect(lastCall()[0]).toBe("/api/services/s1/mount/apply");
    expect(lastCall()[1].method).toBe("POST");
    expect(JSON.parse(lastCall()[1].body as string)).toEqual({ consent: true });
    await api.mountLatest("s1");
    expect(lastCall()[0]).toBe("/api/services/s1/mount/jobs/latest");
    await api.serviceFocus();
    expect(lastCall()[0]).toBe("/api/services/focus");
  });
});

describe("expiredLoginUrl", () => {
  test("outside the shell: plain expired login", () => expect(expiredLoginUrl("/settings", "")).toBe("/login?expired=1"));
  // In Focus mode /login belongs to the app, so the shell leaves via /_styx/exit
  // (clears the focus cookie) or the wrap redirect sends it straight back: reload loop.
  test("inside the shell: exits focus, carries the shell path as next", () =>
    expect(expiredLoginUrl("/_styx/app/sonarr/series", "?p=2")).toBe(
      "/_styx/exit?next=" + encodeURIComponent("/login?expired=1&next=%2F_styx%2Fapp%2Fsonarr%2Fseries%3Fp%3D2")));
  test("unsafe shell inner path is dropped but still exits focus", () =>
    expect(expiredLoginUrl("/_styx/app/immich/api/auth/me", "")).toBe(
      "/_styx/exit?next=" + encodeURIComponent("/login?expired=1")));
});

describe("silent refresh", () => {
  test("refresh carries X-Styx-Client so Focus mode routes it to Styx", async () => {
    const calls: [string, RequestInit][] = [];
    vi.stubGlobal("location", { href: "", pathname: "/", search: "" });
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push([url, init]);
      return new Response("{}", { status: url.endsWith("/auth/refresh") ? 200 : calls.length > 2 ? 200 : 401 });
    }));
    await api.listServices();
    const refresh = calls.find(([u]) => u.endsWith("/auth/refresh"));
    expect(refresh?.[1].headers).toMatchObject({ "X-Styx-Client": "1" });
    vi.unstubAllGlobals();
  });
});
