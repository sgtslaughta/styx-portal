import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const listServiceTiles = vi.fn();
const serviceFocus = vi.fn(() => Promise.resolve<{ slug: string | null }>({ slug: null }));
vi.mock("@/api/client", () => ({ api: { listServiceTiles: () => listServiceTiles(), serviceFocus: () => serviceFocus(),
  me: () => Promise.resolve({ id: "u", username: "a", email: null, role: "user", open_workspaces: null, open_apps: null }),
  myWorkstations: () => Promise.resolve([]), listInstances: () => Promise.resolve([]) } }));
vi.mock("sonner", () => ({ Toaster: ({ theme }: { theme?: string }) => <i data-testid="toaster">{theme}</i>, toast: Object.assign(vi.fn(), { error: vi.fn() }) }));
import { ShellApp } from "../shell-app";

const mk = () => [{ id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path", enabled: true, up: true, frame_ok: true, needs_setup: false }];
afterEach(() => { vi.restoreAllMocks(); listServiceTiles.mockReset(); window.history.replaceState(null, "", "/"); });

function setup() {
  window.history.replaceState(null, "", "/_styx/app/sonarr/series");
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = <QueryClientProvider client={qc}><ShellApp /></QueryClientProvider>;
  return { qc, ...render(ui), ui };
}

it("keeps the running app when a background refetch fails", async () => {
  listServiceTiles.mockResolvedValueOnce(mk()).mockRejectedValue(new Error("boom"));
  const { qc, container } = setup();
  await waitFor(() => expect(container.querySelector("iframe")).toBeTruthy());
  await qc.refetchQueries({ queryKey: ["service-tiles"] });
  expect(container.querySelector("iframe")).toBeTruthy();
});

it("does not reload the frame or re-patch on re-render with equal tiles", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve(mk()));
  const { qc, container } = setup();
  const iframe = await waitFor(() => { const f = container.querySelector("iframe"); expect(f).toBeTruthy(); return f!; });
  const orig = vi.fn();
  const win = {
    location: { href: "http://localhost/sonarr/calendar", pathname: "/sonarr/calendar", search: "", hash: "" },
    document: { title: "", querySelector: () => null }, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    history: { pushState: orig, replaceState: orig },
  };
  Object.defineProperty(iframe, "contentWindow", { get: () => win });
  fireEvent.load(iframe);
  expect(location.pathname).toBe("/_styx/app/sonarr/calendar");
  const wrapper = win.history.pushState;
  await qc.refetchQueries({ queryKey: ["service-tiles"] });
  expect(container.querySelector("iframe")).toBe(iframe);
  expect(iframe.getAttribute("src")).toBe("/sonarr/series");
  expect(win.history.pushState).toBe(wrapper);
  expect(win.removeEventListener).not.toHaveBeenCalled();
});

it("clicking the edge tab opens the dock", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve(mk()));
  const { findByRole } = setup();
  fireEvent.click(await findByRole("button", { name: /open the styx menu/i }));
  expect(await findByRole("dialog")).toBeTruthy();
});

it("dock opens on Apps; Workspaces tab shows the workspaces list; app links never prompt", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve(mk()));
  const { container, getByRole, findByRole, queryByRole } = setup();
  await waitFor(() => expect(container.querySelector("iframe")).toBeTruthy());
  fireEvent.click(getByRole("button", { name: /open the styx menu/i }));
  expect(await findByRole("tab", { name: "Apps" })).toHaveAttribute("aria-selected", "true");
  const app = getByRole("link", { name: /Sonarr/ });
  expect(app.getAttribute("href")).toBe("/_styx/app/sonarr/");
  fireEvent.mouseDown(getByRole("tab", { name: "Workspaces" }), { button: 0 });
  expect(await findByRole("tab", { name: "Workspaces" })).toHaveAttribute("aria-selected", "true");
  expect(queryByRole("dialog", { name: /^Open / })).toBeNull();
});

it("shell toaster follows the html dark class", async () => {
  listServiceTiles.mockResolvedValue(mk());
  document.documentElement.classList.add("dark");
  const { findByTestId } = setup();
  expect((await findByTestId("toaster")).textContent).toBe("dark");
  document.documentElement.classList.remove("dark");
});

it("a focus app without its focus cookie re-opens through /_styx/open (frame would be Styx)", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve([{ ...mk()[0], mount_mode: "cookie-root" }]));
  const replace = vi.fn();
  const real = window.location;
  Object.defineProperty(window, "location", { configurable: true,
    value: { ...real, pathname: "/_styx/app/sonarr/series", search: "?p=2", hash: "#top", replace } });
  try {
    const { container } = setup();
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/_styx/open/sonarr?next=%2Fseries%3Fp%3D2#top"));
    expect(container.querySelector("iframe")).toBeNull();
  } finally {
    Object.defineProperty(window, "location", { configurable: true, value: real });
  }
});

it("a focus app with its focus cookie frames normally", async () => {
  listServiceTiles.mockImplementation(() => Promise.resolve([{ ...mk()[0], mount_mode: "cookie-root" }]));
  serviceFocus.mockResolvedValueOnce({ slug: "sonarr" });
  const { container } = setup();
  await waitFor(() => expect(container.querySelector("iframe")).toBeTruthy());
});
