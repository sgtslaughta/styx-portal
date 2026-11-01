import { expect, test } from "vitest";
import { niceTicks, runs } from "../axis";

test("niceTicks(5) is a clean 1-2-5 sequence, never 1.3 or 3.8", () => {
  expect([[0, 1, 2, 3, 4, 5], [0, 2, 4, 6]]).toContainEqual(niceTicks(5));
});

test("every tick is a multiple of 1, 2 or 5 x 10^k", () => {
  for (const max of [0.7, 3, 5, 13, 38, 100, 420, 1234, 99999]) {
    const t = niceTicks(max);
    expect(t[0]).toBe(0);
    expect(t[t.length - 1]!).toBeGreaterThanOrEqual(max);
    const step = t[1]! - t[0]!;
    const m = step / 10 ** Math.floor(Math.log10(step));
    expect([1, 2, 5]).toContain(Math.round(m * 1e6) / 1e6);
    t.forEach((v, i) => expect(Math.abs(v - i * step)).toBeLessThan(1e-9));
  }
});

test("runs splits on null", () => {
  expect(runs([1, null, 2, 3, undefined]).map((r) => r.map((p) => p.i))).toEqual([[0], [2, 3]]);
});
