import { describe, test, expect, vi } from "vitest";
import { drawCard } from "../matrix-image";

const cols = "ABCDE".split("");
const cells: Record<string, string> = {};
for (const c of cols) for (let r = 1; r <= 10; r++) cells[`${c}${r}`] = `${c}${r}Z`.slice(0, 3);

describe("drawCard", () => {
  test("draws every cell value, title and headers", () => {
    const fillText = vi.fn();
    const ctx = new Proxy({ fillText } as Record<string, unknown>, {
      get: (t, k) => (k in t ? t[k as string] : vi.fn()),
      set: () => true,
    });
    const canvas = { width: 0, height: 0, getContext: () => ctx } as unknown as HTMLCanvasElement;
    drawCard(canvas, cells, "Styx sign-in card");
    const drawn = fillText.mock.calls.map((c) => c[0]);
    for (const v of Object.values(cells)) expect(drawn).toContain(v);
    expect(drawn).toContain("Styx sign-in card");
    for (const h of [...cols, "1", "10"]) expect(drawn).toContain(h);
    expect(canvas.width).toBeGreaterThan(0);
  });
});
