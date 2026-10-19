import { afterEach, expect, test, vi } from "vitest";
import type { Workstation } from "@/api/client";
import type { Instance } from "@/lib/types";
import { instLine, osName, readRecent, since, writeRecent, wsDot, wsLine } from "../workspace";

const NOW = Date.parse("2026-10-19T12:00:00Z");
const ago = (s: number) => new Date(NOW - s * 1000).toISOString();
const ws = (o: object = {}) => ({
  id: "w1", name: "Studio", status: "online", os_info: { pretty_name: "Ubuntu 24.04" },
  in_use: false, in_use_self: false, in_use_by: null, last_heartbeat: ago(4), last_error: null, ...o,
}) as unknown as Workstation;
const inst = (o: object = {}) => ({
  id: "i1", name: "Desk", status: "running", error_message: null,
  started_at: ago(6 * 86_400 + 5 * 3600).replace("Z", ""), ...o, // backend sends naive UTC
}) as unknown as Instance;

afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); });

test("since: compact ages, days spelled out, bad input null", () => {
  expect(since(ago(4), NOW)).toBe("4s");
  expect(since(ago(300), NOW)).toBe("5m");
  expect(since(ago(3 * 3600), NOW)).toBe("3h");
  expect(since(ago(86_400), NOW)).toBe("1 day");
  expect(since(ago(2 * 86_400 + 3600), NOW)).toBe("2 days");
  expect(since(null, NOW)).toBeNull();
  expect(since("garbage", NOW)).toBeNull();
});

test("osName: pretty_name, then distro, then Linux", () => {
  expect(osName(ws())).toBe("Ubuntu 24.04");
  expect(osName(ws({ os_info: { distro: "debian" } }))).toBe("debian");
  expect(osName(ws({ os_info: { pretty_name: 5, distro: "" } }))).toBe("Linux");
  expect(osName(ws({ os_info: {} }))).toBe("Linux");
});

test("wsLine: in use, offline, online, and missing data", () => {
  expect(wsLine(ws(), NOW)).toBe("Ubuntu 24.04 · seen 4s ago");
  expect(wsLine(ws({ in_use: true, in_use_by: "bob" }), NOW)).toBe("In use by bob");
  expect(wsLine(ws({ in_use: true, in_use_self: true }), NOW)).toBe("Connected (you)");
  expect(wsLine(ws({ status: "offline", last_heartbeat: ago(2 * 86_400 + 60) }), NOW)).toBe("Offline · 2 days");
  expect(wsLine(ws({ status: "offline", last_heartbeat: null }), NOW)).toBe("Offline");
  expect(wsLine(ws({ os_info: {}, last_heartbeat: null }), NOW)).toBe("Linux");
});

test("wsDot", () => {
  expect(wsDot(ws()).label).toBe("Online");
  expect(wsDot(ws({ status: "offline" })).label).toBe("Offline");
  expect(wsDot(ws({ in_use: true, in_use_by: "bob" })).label).toBe("In use by bob");
  expect(wsDot(ws({ last_error: "boom" })).dotClass).toBe("bg-destructive");
});

test("instLine: uptime without the arrow, short error, plain labels", () => {
  expect(instLine(inst(), NOW)).toBe("Running · up 6d 5h");
  expect(instLine(inst({ status: "stopped", started_at: null }), NOW)).toBe("Stopped");
  expect(instLine(inst({ status: "error", error_message: "x".repeat(80) }), NOW)).toBe(`Error · ${"x".repeat(39)}…`);
  expect(instLine(inst({ status: "error", error_message: null }), NOW)).toBe("Error");
  expect(instLine(inst({ status: "paused" }), NOW)).toBe("Paused");
});

test("recent workspace round-trips and survives garbage or blocked storage", () => {
  writeRecent({ kind: "instance", id: "i1" });
  expect(readRecent()).toEqual({ kind: "instance", id: "i1" });
  localStorage.setItem("styx.home.recent", "{nope");
  expect(readRecent()).toBeNull();
  localStorage.setItem("styx.home.recent", JSON.stringify({ kind: "vm", id: "x" }));
  expect(readRecent()).toBeNull();
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(readRecent()).toBeNull();
  expect(() => writeRecent({ kind: "workstation", id: "w1" })).not.toThrow();
});
