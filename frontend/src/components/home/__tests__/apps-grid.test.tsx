import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const role = { current: "user" };
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { id: "u", role: role.current } }) }));
const listServiceTiles = vi.fn<() => Promise<unknown>>();
const serviceFocus = vi.fn<() => Promise<{ slug: string | null }>>();
vi.mock("@/api/client", () => ({
  api: { serviceThumbUrl: (id: string) => `/api/services/${id}/thumbnail`, listServiceTiles: () => listServiceTiles(), serviceFocus: () => serviceFocus() },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openHref = vi.fn();
vi.mock("@/lib/connect-wipe", () => ({ openHref: (...a: unknown[]) => openHref(...a) }));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppsGrid } from "../apps-grid";

const renderList = (props: { onOpenSettings?: () => void } = {}) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><AppsGrid {...props} /></QueryClientProvider>);

const tile = (o: object) => ({ id: "1", slug: "sonarr", name: "Sonarr", icon_kind: "image", icon_etag: "e9", mount_mode: "path", frame_ok: true, enabled: true, up: true, ...o });

beforeEach(() => {
  role.current = "user";
  localStorage.clear();
  listServiceTiles.mockReset();
  serviceFocus.mockReset();
  choose.mockReset(); openHref.mockReset();
  serviceFocus.mockResolvedValue({ slug: null });
});

describe("AppsGrid", () => {
  test("dock item is icon-only (no thumbnail)", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    const { container } = renderList();
    await screen.findByRole("link", { name: /open sonarr/i });
    expect(container.querySelector('img[src*="thumbnail"]')).toBeNull();
  });
  test("tile shows the server icon by id and etag", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    const { container } = renderList();
    await screen.findByRole("link", { name: /open sonarr/i });
    expect(container.querySelector("img")!.getAttribute("src")).toBe("/api/services/1/icon?v=e9");
  });

  test("path tile is a plain link, even when down; unknown is neutral", async () => {
    listServiceTiles.mockResolvedValue([tile({ up: false }), tile({ id: "3", slug: "x", name: "X", up: null })]);
    renderList();
    const link = await screen.findByRole("link", { name: /open sonarr/i });
    expect(link).toHaveAttribute("href", "/_styx/app/sonarr/");
    expect(screen.getByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Status unknown")).toBeInTheDocument();
  });

  test("links into the shell and marks the focused app", async () => {
    serviceFocus.mockResolvedValue({ slug: "immich" });
    listServiceTiles.mockResolvedValue([tile({}), tile({ id: "2", slug: "immich", name: "Immich", mount_mode: "cookie-root" })]);
    renderList();
    expect(await screen.findByRole("link", { name: /open sonarr/i })).toHaveAttribute("href", "/_styx/app/sonarr/");
    expect(screen.getByRole("link", { name: /open immich/i })).toHaveAttribute("href", "/_styx/open/immich");
    expect(screen.getByText("Opens full screen")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Exit Immich" })).toHaveAttribute("href", "/_styx/exit?next=/");
    expect(screen.queryByRole("link", { name: "Exit Sonarr" })).toBeNull();
    expect(screen.getByRole("link", { name: "Open Immich" })).toHaveClass("border-obol-foreground");
    expect(screen.getByRole("link", { name: "Open Immich" })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("link", { name: "Open Sonarr" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("link", { name: "Exit Immich" })).toHaveClass("max-sm:h-11");
  });

  test("frame_ok false path tile opens directly; unknown focus slug marks nothing", async () => {
    serviceFocus.mockResolvedValue({ slug: "<b>evil</b>" });
    listServiceTiles.mockResolvedValue([tile({ frame_ok: false })]);
    renderList();
    expect(await screen.findByRole("link", { name: /open sonarr/i })).toHaveAttribute("href", "/sonarr/");
    await waitFor(() => expect(serviceFocus).toHaveBeenCalled());
    expect(screen.queryByText("Exit")).toBeNull();
    expect(screen.queryByText(/evil/)).toBeNull();
  });


  test("list is fetched on every mount (no shared cache)", async () => {
    listServiceTiles.mockResolvedValueOnce([tile({})]).mockResolvedValueOnce([]);
    const a = renderList();
    await screen.findByText("Sonarr");
    a.unmount();
    renderList();
    await waitFor(() => expect(listServiceTiles).toHaveBeenCalledTimes(2));
    expect(await screen.findByText("No apps shared with you yet.")).toBeInTheDocument();
  });

  test("admin full model maps health_status; tip shown to admins only and dismissible", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([{ ...tile({}), up: undefined, health_status: "unhealthy" }]);
    renderList();
    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText(/open apps with a non-admin account/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss tip/i }));
    expect(screen.queryByText(/non-admin account/i)).toBeNull();
    expect(localStorage.getItem("styx.serviceTipDismissed")).toBe("1");
  });

  test("members never see the tip", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    renderList();
    await screen.findByText("Sonarr");
    expect(screen.queryByText(/non-admin account/i)).toBeNull();
  });

  test("needs_setup tile deep-links to the setup step with a chip and no health dot", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([tile({ id: "s7", needs_setup: true, up: null })]);
    renderList();
    const link = await screen.findByRole("link", { name: "Set up Sonarr" });
    expect(link).toHaveAttribute("href", "/?setup=s7");
    expect(screen.getByText("Needs setup")).toBeInTheDocument();
    expect(screen.queryByText("Status unknown")).toBeNull();
  });

  test("plain click asks via the Apps preference and opens the shell href", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    renderList();
    fireEvent.click(await screen.findByRole("link", { name: "Open Sonarr" }));
    expect(choose).toHaveBeenCalledWith("apps", "Sonarr", expect.any(Function));
    choose.mock.calls[0]![2]("new_tab");
    expect(openHref).toHaveBeenCalledWith("new_tab", "/_styx/app/sonarr/");
  });

  test("modifier or middle clicks and needs-setup tiles keep native behaviour", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([tile({}), tile({ id: "2", slug: "j", name: "Jelly", needs_setup: true })]);
    renderList();
    const link = await screen.findByRole("link", { name: "Open Sonarr" });
    for (const init of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { button: 1 }])
      fireEvent.click(link, init);
    fireEvent.click(screen.getByRole("link", { name: "Set up Jelly" }));
    expect(choose).not.toHaveBeenCalled();
  });

  test("region is Apps; admin sees an Add app tile", async () => {
    role.current = "admin";
    const onOpenSettings = vi.fn();
    listServiceTiles.mockResolvedValue([tile({})]);
    renderList({ onOpenSettings });
    expect(await screen.findByRole("region", { name: "Apps" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Add app" }));
    expect(onOpenSettings).toHaveBeenCalled();
  });

  test("empty states", async () => {
    listServiceTiles.mockResolvedValue([]);
    const { unmount } = renderList();
    expect(await screen.findByText("No apps shared with you yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add app" })).toBeNull();
    unmount();
    role.current = "admin";
    renderList();
    expect(await screen.findByText("No apps yet. Add your first app.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add app" })).toBeInTheDocument();
  });

  test("a failed load says so and retries, instead of the empty state", async () => {
    listServiceTiles.mockRejectedValueOnce(new Error("down")).mockResolvedValue([tile({})]);
    renderList();
    expect(await screen.findByText("Couldn't load apps.")).toBeInTheDocument();
    expect(screen.queryByText("No apps shared with you yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("link", { name: "Open Sonarr" })).toBeInTheDocument();
  });
});
