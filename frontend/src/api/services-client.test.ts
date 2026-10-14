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
  test("inside the shell: carries the shell path as next", () =>
    expect(expiredLoginUrl("/_styx/app/sonarr/series", "?p=2")).toBe(
      "/login?expired=1&next=%2F_styx%2Fapp%2Fsonarr%2Fseries%3Fp%3D2"));
  test("unsafe shell inner path is dropped", () =>
    expect(expiredLoginUrl("/_styx/app/immich/api/auth/me", "")).toBe("/login?expired=1"));
});
