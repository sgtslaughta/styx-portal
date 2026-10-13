import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Frame } from "../frame";

afterEach(() => { vi.restoreAllMocks(); Reflect.deleteProperty(navigator, "serviceWorker"); });

const tile = { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path", enabled: true, up: true, frame_ok: true } as const;

it("shows the fallback when the frame refuses to load", () => {
  const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
  const iframe = container.querySelector("iframe")!;
  Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
  fireEvent.load(iframe);
  expect(screen.getByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
  expect(screen.getByRole("link", { name: "Open Sonarr on its own" }).getAttribute("href")).toBe("/sonarr/");
});

function fakeWin(path: string) {
  const orig = { push: vi.fn(), replace: vi.fn() };
  const doc = { title: "T", querySelector: () => null };
  const win = {
    location: { href: `http://localhost${path}`, pathname: path, search: "", hash: "" },
    document: doc, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    history: { pushState: orig.push, replaceState: orig.replace },
  };
  return { win, orig };
}

it("focus apps get sync after the service-worker cleanup", async () => {
  const getRegistrations = vi.fn().mockResolvedValue([]);
  Object.defineProperty(navigator, "serviceWorker", { value: { getRegistrations }, configurable: true });
  const focus = { ...tile, slug: "immich", name: "Immich", mount_mode: "cookie-root" } as const;
  const { container } = render(<Frame tile={focus} inner="/" onTitle={() => {}} />);
  const iframe = await waitFor(() => { const f = container.querySelector("iframe"); expect(f).toBeTruthy(); return f!; });
  Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
  fireEvent.load(iframe);
  expect(screen.getByRole("heading", { name: "Immich can't run inside Styx" })).toBeTruthy();
});

it("mirrors the app URL and patches each document's own history", () => {
  const spy = vi.spyOn(window.history, "replaceState");
  const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
  const iframe = container.querySelector("iframe")!;
  const a = fakeWin("/sonarr/series"), b = fakeWin("/sonarr/calendar");
  let cur: unknown = a.win;
  Object.defineProperty(iframe, "contentWindow", { get: () => cur });
  fireEvent.load(iframe);
  expect(spy).toHaveBeenLastCalledWith(null, "", "/_styx/app/sonarr/series");
  cur = b.win;
  fireEvent.load(iframe);
  expect(spy).toHaveBeenLastCalledWith(null, "", "/_styx/app/sonarr/calendar");
  b.win.history.pushState(null, "", "/x");
  expect(b.orig.push).toHaveBeenCalledTimes(1);
  expect(a.orig.push).not.toHaveBeenCalled();
  expect(a.win.history.pushState).not.toBe(b.win.history.pushState);
});

describe("blocked-frame poll", () => {
  const setup = (contentWindow: () => unknown) => {
    const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
    const iframe = container.querySelector("iframe")!;
    Object.defineProperty(iframe, "contentWindow", { get: contentWindow, configurable: true });
    return iframe;
  };
  const card = () => screen.queryByRole("heading", { name: "Sonarr can't run inside Styx" });
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it("a frame whose location throws (cross-origin error page) becomes blocked without a load event", () => {
    setup(() => ({ get location(): never { throw new DOMException("x", "SecurityError"); } }));
    act(() => { vi.advanceTimersByTime(1000); });
    expect(card()).toBeTruthy();
  });
  it("about:blank is never flagged, even after 10 s (a slow app has not committed yet)", () => {
    setup(() => ({ location: { href: "about:blank" } }));
    act(() => { vi.advanceTimersByTime(12_000); });
    expect(card()).toBeNull();
  });
  it("a load before the timer stops the poll", () => {
    let throws = false;
    const iframe = setup(() => ({
      get location() { if (throws) throw new DOMException("x", "SecurityError"); return { href: "http://localhost/sonarr/", pathname: "/sonarr/", search: "", hash: "" }; },
      document: { title: "", querySelector: () => null }, addEventListener: vi.fn(), removeEventListener: vi.fn(),
      history: { pushState: vi.fn(), replaceState: vi.fn() },
    }));
    act(() => { fireEvent.load(iframe); });
    throws = true; // later navigations to a cross-origin page must not trip the first-load poll
    act(() => { vi.advanceTimersByTime(12_000); });
    expect(card()).toBeNull();
  });
});
