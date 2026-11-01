import { describe, expect, it } from "vitest";
import { stepWave } from "../water";

describe("stepWave", () => {
  it("spreads an impulse to neighbours with peak below 1", () => {
    const w = 8, h = 8;
    const cur = new Float32Array(w * h), prev = new Float32Array(w * h);
    const c = 4 * w + 4;
    cur[c] = 1;
    const peak = stepWave(cur, prev, w, h, 0.97);
    expect(peak).toBeLessThan(1);
    for (const i of [c - 1, c + 1, c - w, c + w]) expect(prev[i]).toBeGreaterThan(0);
  });

  it("decays below the absolute stop threshold", () => {
    const w = 8, h = 8;
    let cur = new Float32Array(w * h), prev = new Float32Array(w * h);
    cur[4 * w + 4] = 1;
    let peak = 1;
    for (let i = 0; i < 400; i++) {
      peak = stepWave(cur, prev, w, h, 0.97);
      [cur, prev] = [prev, cur];
    }
    expect(peak).toBeLessThan(0.004);
  });
});
