import { describe, it, expect } from "vitest";
import { singleFlight } from "./single-flight.ts";

describe("singleFlight", () => {
  it("THE BUG: concurrent calls must coalesce into ONE underlying call", async () => {
    // Why this matters: the backend rotates refresh tokens with RFC 9700 reuse
    // detection — a second /auth/refresh replaying a just-rotated token revokes
    // the whole family and logs the user out. Concurrent 401s (many polls firing
    // at once) MUST share a single in-flight refresh.
    let calls = 0;
    let release!: (v: string) => void;
    const gate = new Promise<string>((r) => { release = r; });
    const wrapped = singleFlight(() => { calls++; return gate; });

    const results = Promise.all([wrapped(), wrapped(), wrapped(), wrapped()]);
    release("ok");
    expect(await results).toEqual(["ok", "ok", "ok", "ok"]);
    expect(calls).toBe(1);
  });

  it("after the in-flight call settles, the next call starts a fresh one", async () => {
    let calls = 0;
    const wrapped = singleFlight(async () => { calls++; return calls; });

    expect(await wrapped()).toBe(1);
    expect(await wrapped()).toBe(2); // not memoized — single-flight, not cache
    expect(calls).toBe(2);
  });

  it("a rejected in-flight call clears, so a later call can retry", async () => {
    let calls = 0;
    const wrapped = singleFlight(async () => {
      calls++;
      if (calls === 1) throw new Error("boom");
      return "recovered";
    });

    await expect(wrapped()).rejects.toThrow(/boom/);
    expect(await wrapped()).toBe("recovered");
    expect(calls).toBe(2);
  });
});
