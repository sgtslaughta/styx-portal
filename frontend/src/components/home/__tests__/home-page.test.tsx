import { render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const role = { current: "user" };
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { id: "u", role: role.current } }) }));
vi.mock("@/api/client", () => ({
  api: {
    myWorkstations: () => Promise.resolve([{ id: "w1", name: "mini", status: "online", in_use: false, in_use_self: false, in_use_by: null, icon_etag: "e", os_info: {} }]),
    listServiceTiles: () => Promise.resolve([{ id: "s1", slug: "sonarr", name: "Sonarr", icon_kind: "image", icon_etag: "e", mount_mode: "path", frame_ok: true, enabled: true, up: true, needs_setup: true }]),
    serviceFocus: () => Promise.resolve({ slug: null }),
    workstationThumbUrl: (id: string) => `/t/${id}`,
    screenshotUrl: (id: string) => `/s/${id}`,
  },
  ApiError: class extends Error {},
}));
vi.mock("@/hooks/use-instances", () => ({
  useInstances: () => ({ data: [{ id: "i1", name: "Chrome", template_id: "t", subdomain: "chrome", status: "running" }] }),
  useStartInstance: () => ({ mutate: vi.fn() }),
  useStopInstance: () => ({ mutate: vi.fn() }),
  useUnpauseInstance: () => ({ mutate: vi.fn() }),
}));
vi.mock("@/hooks/use-templates", () => ({ useTemplates: () => ({ data: [{ id: "t", icon: "🌐" }] }) }));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => vi.fn() }));
vi.mock("@/components/home/details-sheet", () => ({ DetailsSheet: () => null }));
vi.mock("@/lib/effects/water", () => ({ createWater: () => ({ destroy() {} }) }));

import { HomePage } from "../home-page";

const renderHome = (onNew = vi.fn()) =>
  render(<QueryClientProvider client={new QueryClient()}><HomePage onNewContainer={onNew} /></QueryClientProvider>);

beforeEach(() => { role.current = "user"; localStorage.clear(); });

describe("HomePage", () => {
  test("headings in order", async () => {
    renderHome();
    await screen.findByText("mini");
    const names = screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(names).toEqual(["Recent", "Desktops", "Apps", "Containers"]);
  });

  test("New container button sits in the Containers heading row", async () => {
    const onNew = vi.fn();
    renderHome(onNew);
    const head = screen.getByRole("heading", { name: "Containers" }).parentElement!;
    const btn = within(head).getByRole("button", { name: /new container/i });
    btn.click();
    expect(onNew).toHaveBeenCalled();
  });

  test("plain user sees no Needs setup dot; admin does", async () => {
    const { unmount } = renderHome();
    await screen.findByRole("link", { name: /sonarr/i });
    expect(screen.queryByText("Needs setup")).toBeNull();
    unmount();
    role.current = "admin";
    renderHome();
    expect(await screen.findByText("Needs setup")).toBeInTheDocument();
  });

  test("recent shows opened items with a glass action", async () => {
    localStorage.setItem("styxOpened", JSON.stringify({ w1: 5, i1: 9 }));
    renderHome();
    await waitFor(() => expect(screen.getAllByTestId("recent")).toHaveLength(2));
    const items = screen.getAllByTestId("recent");
    expect(items.map((e) => within(e).getByRole("button").textContent)).toEqual(["Resume", "Connect"]);
  });
});
