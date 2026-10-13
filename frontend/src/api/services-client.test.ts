import { describe, test, expect, vi, beforeEach } from "vitest";
import { api } from "./client";

const calls = () => (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls;

describe("services api", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } })));
  });

  test("every request carries X-Styx-Client", async () => {
    await api.listServices();
    expect(calls()[0][1].headers).toMatchObject({ "X-Styx-Client": "1" });
  });

  test("enterService posts and tolerates an empty 200 body", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 200 })));
    await expect(api.enterService("unraid")).resolves.toBeUndefined();
    const [url, init] = calls()[0];
    expect(url).toBe("/api/services/unraid/enter");
    expect(init.method).toBe("POST");
  });

  test("setUserGroups sends group_ids", async () => {
    await api.setUserGroups("u1", ["g1"]);
    const [url, init] = calls()[0];
    expect(url).toBe("/api/users/u1/groups");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body as string)).toEqual({ group_ids: ["g1"] });
  });

  test("setServiceEnabled picks enable/disable", async () => {
    await api.setServiceEnabled("s1", false);
    expect(calls()[0][0]).toBe("/api/services/s1/disable");
  });
});
