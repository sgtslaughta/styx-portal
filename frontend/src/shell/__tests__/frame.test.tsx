import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Frame } from "../frame";

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); Reflect.deleteProperty(navigator, "serviceWorker"); });

const tile = { id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path", enabled: true, up: true, frame_ok: true, needs_setup: false } as const;

it("shows the fallback when the frame refuses to load", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("")));
  const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
  const iframe = container.querySelector("iframe")!;
  Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
  fireEvent.load(iframe);
  expect(await screen.findByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
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
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("")));
  const getRegistrations = vi.fn().mockResolvedValue([]);
  Object.defineProperty(navigator, "serviceWorker", { value: { getRegistrations }, configurable: true });
  const focus = { ...tile, slug: "immich", name: "Immich", mount_mode: "cookie-root" } as const;
  const { container } = render(<Frame tile={focus} inner="/" onTitle={() => {}} />);
  const iframe = await waitFor(() => { const f = container.querySelector("iframe"); expect(f).toBeTruthy(); return f!; });
  Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
  fireEvent.load(iframe);
  expect(await screen.findByRole("heading", { name: "Immich can't run inside Styx" })).toBeTruthy();
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

  it("a frame whose location throws (cross-origin error page) becomes blocked without a load event", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("")));
    setup(() => ({ get location(): never { throw new DOMException("x", "SecurityError"); } }));
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
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

describe("blocked-frame header probe", () => {
  const blank = () => ({ location: { href: "about:blank" } });
  const run = async (csp: string | null) => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("", { headers: csp ? { "content-security-policy": csp } : {} }));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
    Object.defineProperty(container.querySelector("iframe")!, "contentWindow", { get: blank, configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(12_000); });
    return fetchMock;
  };
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("an about:blank frame whose app sends frame-ancestors 'none' is blocked", async () => {
    const f = await run("default-src 'self'; frame-ancestors 'none'");
    expect(f).toHaveBeenCalledWith("/sonarr/", expect.anything());
    expect(screen.getByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
  });
  it("frame-ancestors 'self' or no CSP leaves a slow about:blank frame alone", async () => {
    await run("frame-ancestors 'self'");
    expect(screen.queryByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeNull();
  });
});

it("a needs_setup tile shows the setup card instead of an iframe", () => {
  const { container } = render(<Frame tile={{ ...tile, id: "s7", needs_setup: true }} inner="/" onTitle={() => {}} />);
  expect(container.querySelector("iframe")).toBeNull();
  expect(screen.getByRole("heading", { name: "Sonarr isn't set up yet" })).toBeTruthy();
  expect(screen.getByText("Styx still needs to set its base path to /sonarr.")).toBeTruthy();
  expect(screen.getByRole("link", { name: "Set it up" }).getAttribute("href")).toBe("/?setup=s7");
});

describe("blocked frame: honest card", () => {
  const throwing = () => ({ get location(): never { throw new DOMException("x", "SecurityError"); } });
  const run = async (res: Response | Error) => {
    const fetchMock = vi.fn().mockImplementation(() => (res instanceof Error ? Promise.reject(res) : Promise.resolve(res)));
    vi.stubGlobal("fetch", fetchMock);
    const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
    Object.defineProperty(container.querySelector("iframe")!, "contentWindow", { get: throwing, configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    return fetchMock;
  };
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });

  it("an app answering 404 gets an error card that points at the base path", async () => {
    const f = await run(new Response("", { status: 404 }));
    expect(f).toHaveBeenCalledWith("/sonarr/", expect.anything());
    expect(screen.getByRole("heading", { name: "Sonarr returned an error (404)" })).toBeTruthy();
    expect(screen.getByText("It answered 404 at /sonarr/. Its base path may not be set to /sonarr.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open Sonarr on its own" }).getAttribute("href")).toBe("/sonarr/");
  });
  it("other statuses get the generic error text", async () => {
    await run(new Response("", { status: 502 }));
    expect(screen.getByRole("heading", { name: "Sonarr returned an error (502)" })).toBeTruthy();
    expect(screen.getByText("It answered 502. Open it on its own to see the details.")).toBeTruthy();
  });
  it("a 200 with frame-ancestors 'none' is a refusal", async () => {
    await run(new Response("", { headers: { "content-security-policy": "frame-ancestors 'none'" } }));
    expect(screen.getByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
  });
  it("a failed fetch falls back to the refusal card", async () => {
    await run(new TypeError("offline"));
    expect(screen.getByRole("heading", { name: "Sonarr can't run inside Styx" })).toBeTruthy();
  });
  it("a first load blocked on attach is checked the same way", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 404 })));
    const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
    const iframe = container.querySelector("iframe")!;
    Object.defineProperty(iframe, "contentWindow", { get() { throw new DOMException("x", "SecurityError"); } });
    await act(async () => { fireEvent.load(iframe); await vi.advanceTimersByTimeAsync(0); });
    expect(screen.getByRole("heading", { name: "Sonarr returned an error (404)" })).toBeTruthy();
  });
  it("the header probe's 404 is used when the frame is then found blocked", async () => {
    const f = vi.fn().mockResolvedValue(new Response("", { status: 404, headers: { "content-security-policy": "frame-ancestors 'none'" } }));
    vi.stubGlobal("fetch", f);
    const { container } = render(<Frame tile={tile} inner="/" onTitle={() => {}} />);
    Object.defineProperty(container.querySelector("iframe")!, "contentWindow", { get: () => ({ location: { href: "about:blank" } }), configurable: true });
    await act(async () => { await vi.advanceTimersByTimeAsync(12_000); });
    expect(screen.getByRole("heading", { name: "Sonarr returned an error (404)" })).toBeTruthy();
    expect(f).toHaveBeenCalledTimes(1);
  });
});
