import { afterEach, describe, expect, it, vi } from "vitest";
import { createWater, stepWave } from "../water";

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

describe("createWater GL lifecycle", () => {
  function setup(linkOk = true) {
    const calls: Record<string, number> = {};
    const gl = new Proxy({} as Record<string, unknown>, {
      get: (t, k: string) => {
        if (k in t) return t[k];
        if (k === "getProgramParameter" || k === "getShaderParameter") return () => linkOk;
        if (/^[A-Z_0-9]+$/.test(k)) return 1;
        return (...a: unknown[]) => { calls[k] = (calls[k] ?? 0) + 1; return k.startsWith("create") ? {} : (void a, 0); };
      },
    });
    const cv = document.createElement("canvas");
    cv.getBoundingClientRect = () => ({ width: 120, height: 80, left: 0, top: 0, right: 120, bottom: 80, x: 0, y: 0, toJSON() {} });
    cv.getContext = (() => gl) as unknown as typeof cv.getContext;
    vi.stubGlobal("ResizeObserver", class { constructor(private cb: () => void) {} observe() { this.cb(); } disconnect() {} });
    return { cv, calls };
  }
  afterEach(() => vi.unstubAllGlobals());

  it("setSource re-uploads the texture without rebuilding the program", () => {
    const { cv, calls } = setup();
    const water = createWater(cv, { source: document.createElement("canvas") });
    expect(calls.createProgram).toBe(1);
    const uploads = calls.texImage2D!;
    water.setSource(document.createElement("canvas"));
    expect(calls.createProgram).toBe(1);
    expect(calls.texImage2D).toBeGreaterThan(uploads);
    water.destroy();
  });

  it("destroy releases program, shaders, buffer and textures", () => {
    const { cv, calls } = setup();
    createWater(cv, { source: document.createElement("canvas") }).destroy();
    expect(calls.deleteProgram).toBe(1);
    expect(calls.deleteShader).toBe(2);
    expect(calls.deleteBuffer).toBe(1);
    expect(calls.deleteTexture).toBe(2);
  });

  it("a failed shader hides the canvas instead of painting black", () => {
    const { cv } = setup(false);
    createWater(cv, { source: document.createElement("canvas") }).destroy();
    expect(cv.style.visibility).toBe("hidden");
  });
});
