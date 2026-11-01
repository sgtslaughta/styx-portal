import { describe, expect, test } from "vitest";
import { foldSeries, foldStreaming, foldTop } from "../fold-top";

describe("foldTop", () => {
  test("12 rows, n=5 -> 6 rows ending in Others", () => {
    const rows = Array.from({ length: 12 }, (_, i) => ({ v: i + 1 }));
    const out = foldTop(rows, 5, (r) => r.v);
    expect(out).toHaveLength(6);
    expect(out[0]).toEqual({ v: 12 });
    expect(out[5]).toMatchObject({ label: "Others", sub: "7 more" });
  });
  test("no fold when rows <= n", () => {
    expect(foldTop([{ v: 1 }, { v: 2 }], 5, (r) => r.v)).toHaveLength(2);
  });
});

const users = ["a", "b", "c", "d", "e", "f", "g"];
const rows = [
  { workstation: "mini", parts: Object.fromEntries(users.map((u, i) => [u, 10 - i])) },
  { workstation: "nuc", parts: { a: 1, g: 2 } },
];

describe("foldSeries", () => {
  test("top-5 get s1..s5 by total, rest fold into Others (s0)", () => {
    const { series, rows: out } = foldSeries(rows, 5);
    expect(series.map((s) => [s.name, s.slot])).toEqual([
      ["a", "s1"], ["b", "s2"], ["c", "s3"], ["d", "s4"], ["e", "s5"], ["Others", "s0"],
    ]);
    expect(out[0]!.parts.Others).toBe(5 + 4); // f + g
    expect(out[1]!.parts).toEqual({ a: 1, Others: 2 });
  });
  test("colour assignment is stable when input order is shuffled", () => {
    const a = foldSeries(rows, 5).series;
    const b = foldSeries([...rows].reverse().map((r) => ({ ...r, parts: Object.fromEntries(Object.entries(r.parts).reverse()) })), 5).series;
    expect(b).toEqual(a);
  });
  test("no Others series when everyone fits", () => {
    expect(foldSeries([{ parts: { a: 1, b: 2 } }], 5).series.map((s) => s.name)).toEqual(["b", "a"]);
  });
});

test("foldStreaming folds workstations and users", () => {
  const many = Array.from({ length: 7 }, (_, i) => ({ workstation: `w${i}`, parts: { a: 10 - i } }));
  const { rows: out } = foldStreaming(many, 5);
  expect(out).toHaveLength(6);
  expect(out[5]).toMatchObject({ label: "Others", sub: "2 more", parts: { a: 5 + 4 } });
});
