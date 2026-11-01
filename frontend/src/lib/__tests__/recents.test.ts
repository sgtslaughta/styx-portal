import { beforeEach, describe, expect, it } from "vitest";
import { readOpened, recentItems, recordOpened } from "../recents";
import type { Workstation } from "@/api/client";
import type { Instance } from "../types";

const ws = (id: string, o: Partial<Workstation> = {}) =>
  ({ id, name: id, status: "online", in_use: false, in_use_self: false, ...o }) as Workstation;
const inst = (id: string, o: Partial<Instance> = {}) => ({ id, name: id, status: "running", ...o }) as Instance;

beforeEach(() => localStorage.clear());

describe("recentItems", () => {
  it("returns the 3 most recently opened, newest first", () => {
    const out = recentItems([inst("a"), inst("b")], [ws("c"), ws("d")], { a: 1, b: 4, c: 3, d: 2 });
    expect(out.map((r) => r.id)).toEqual(["b", "c", "d"]);
  });
  it("puts a connected desktop first regardless of age", () => {
    const out = recentItems([inst("a")], [ws("c", { in_use_self: true })], { a: 9, c: 1 });
    expect(out.map((r) => r.id)).toEqual(["c", "a"]);
    expect(out[0]!.action).toBe("Resume");
  });
  it("skips offline workstations and unopened items", () => {
    const out = recentItems([inst("a")], [ws("c", { status: "offline" })], { a: 1, c: 5 });
    expect(out.map((r) => r.id)).toEqual(["a"]);
    expect(recentItems([inst("x")], [], {})).toEqual([]);
  });
  it("maps actions", () => {
    const out = recentItems([inst("s", { status: "stopped" }), inst("r")], [ws("w")], { s: 1, r: 2, w: 3 });
    expect(Object.fromEntries(out.map((r) => [r.id, r.action]))).toEqual({ w: "Connect", r: "Resume", s: "Start" });
  });
});

describe("opened storage", () => {
  it("records and reads", () => {
    recordOpened("x");
    expect(readOpened().x).toBeGreaterThan(0);
  });
  it("tolerates junk", () => {
    localStorage.setItem("styxOpened", "{nope");
    expect(readOpened()).toEqual({});
  });
});
