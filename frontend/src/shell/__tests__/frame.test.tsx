import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Frame } from "../frame";

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
  Reflect.deleteProperty(navigator, "serviceWorker");
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
