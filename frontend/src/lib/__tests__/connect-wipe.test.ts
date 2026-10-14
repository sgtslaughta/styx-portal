import { afterEach, beforeEach, expect, test, vi } from "vitest";
const toast = vi.fn();
vi.mock("sonner", () => ({ toast: (m: string) => toast(m) }));
import { BLOCKED, openHref, openPending } from "../connect-wipe";

const assign = vi.fn();
let opened: { location: { replace: ReturnType<typeof vi.fn> }; close: ReturnType<typeof vi.fn>; opener: unknown } | null;
beforeEach(() => {
  opened = { location: { replace: vi.fn() }, close: vi.fn(), opener: window };
  vi.spyOn(window, "open").mockImplementation(() => opened as unknown as Window);
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign, origin: "http://localhost" } });
});
afterEach(() => { vi.restoreAllMocks(); assign.mockReset(); toast.mockReset(); });

const hash = (u: string) => JSON.parse(decodeURIComponent(u.split("#")[1]!));

test("new tab opens synchronously, before the url resolves, then hands the url to the tab", async () => {
  let resolve!: (u: string) => void;
  const p = openPending("new_tab", "Connecting to Box…", () => new Promise((r) => { resolve = r; }));
  expect(window.open).toHaveBeenCalledTimes(1);
  expect(hash(vi.mocked(window.open).mock.calls[0]![0] as string)).toEqual({ label: "Connecting to Box…" });
  expect(opened!.opener).toBeNull();
  resolve("/w/box/");
  await p;
  expect(hash(opened!.location.replace.mock.calls[0]![0])).toEqual({ url: "/w/box/", label: "Connecting to Box…" });
  expect(assign).not.toHaveBeenCalled();
});

test("blocked popup falls back to this tab with a toast", async () => {
  opened = null;
  await openPending("new_tab", "L", async () => "/i/x/");
  expect(toast).toHaveBeenCalledWith(BLOCKED);
  expect(hash(assign.mock.calls[0]![0])).toEqual({ url: "/i/x/", label: "L" });
});

test("same tab never opens a window", async () => {
  await openPending("same_tab", "L", async () => "/i/x/");
  expect(window.open).not.toHaveBeenCalled();
  expect(assign.mock.calls[0]![0]).toMatch(/^\/connecting#/);
});

test("failure closes the pre-opened tab and rejects", async () => {
  await expect(openPending("new_tab", "L", async () => { throw new Error("nope"); })).rejects.toThrow("nope");
  expect(opened!.close).toHaveBeenCalled();
});

test("openHref: new tab, blocked fallback, same tab", () => {
  openHref("new_tab", "/_styx/app/s/");
  expect(window.open).toHaveBeenCalledWith("/_styx/app/s/", "_blank");
  expect(assign).not.toHaveBeenCalled();
  opened = null;
  openHref("new_tab", "/_styx/app/s/");
  expect(toast).toHaveBeenCalledWith(BLOCKED);
  expect(assign).toHaveBeenCalledWith("/_styx/app/s/");
  openHref("same_tab", "/x/");
  expect(assign).toHaveBeenLastCalledWith("/x/");
});
