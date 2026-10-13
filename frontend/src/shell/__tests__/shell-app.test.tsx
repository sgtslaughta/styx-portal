import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

const listServiceTiles = vi.fn();
vi.mock("@/api/client", () => ({ api: { listServiceTiles: () => listServiceTiles() } }));
import { ShellApp } from "../shell-app";

const mk = () => [{ id: "1", slug: "sonarr", name: "Sonarr", icon: null, mount_mode: "path", enabled: true, up: true, frame_ok: true }];
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
