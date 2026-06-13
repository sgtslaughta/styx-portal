import { test } from "node:test";
import assert from "node:assert/strict";
import { singleFlight } from "./single-flight.ts";

test("THE BUG: concurrent calls must coalesce into ONE underlying call", async () => {
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
  assert.deepEqual(await results, ["ok", "ok", "ok", "ok"]);
  assert.equal(calls, 1);
});

test("after the in-flight call settles, the next call starts a fresh one", async () => {
  let calls = 0;
  const wrapped = singleFlight(async () => { calls++; return calls; });

  assert.equal(await wrapped(), 1);
  assert.equal(await wrapped(), 2); // not memoized — single-flight, not cache
  assert.equal(calls, 2);
});

test("a rejected in-flight call clears, so a later call can retry", async () => {
  let calls = 0;
  const wrapped = singleFlight(async () => {
    calls++;
    if (calls === 1) throw new Error("boom");
    return "recovered";
  });

  await assert.rejects(wrapped(), /boom/);
  assert.equal(await wrapped(), "recovered");
  assert.equal(calls, 2);
});
