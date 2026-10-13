import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const role = { current: "user" };
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { id: "u", role: role.current } }) }));
const listServiceTiles = vi.fn<() => Promise<unknown>>();
const serviceFocus = vi.fn<() => Promise<{ slug: string | null }>>();
vi.mock("@/api/client", () => ({
  api: { listServiceTiles: () => listServiceTiles(), serviceFocus: () => serviceFocus() },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ServiceList } from "../service-list";

const renderList = (props: { onOpenSettings?: () => void } = {}) =>
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ServiceList {...props} /></QueryClientProvider>);

const tile = (o: object) => ({ id: "1", slug: "sonarr", name: "Sonarr", icon: "📺", mount_mode: "path", frame_ok: true, enabled: true, up: true, ...o });

beforeEach(() => {
  role.current = "user";
  localStorage.clear();
  listServiceTiles.mockReset();
  serviceFocus.mockReset();
  serviceFocus.mockResolvedValue({ slug: null });
});

describe("ServiceList", () => {
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
    expect(screen.getByText("Opens on its own")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Exit Immich" })).toHaveAttribute("href", "/_styx/exit?next=/");
    expect(screen.queryByRole("link", { name: "Exit Sonarr" })).toBeNull();
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

  test("members with no services see nothing", async () => {
    listServiceTiles.mockResolvedValue([]);
    const { container } = renderList();
    await waitFor(() => expect(listServiceTiles).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  test("list is fetched on every mount (no shared cache)", async () => {
    listServiceTiles.mockResolvedValueOnce([tile({})]).mockResolvedValueOnce([]);
    const a = renderList();
    await screen.findByText("Sonarr");
    a.unmount();
    const b = renderList();
    await waitFor(() => expect(listServiceTiles).toHaveBeenCalledTimes(2));
    expect(b.container).toBeEmptyDOMElement();
  });

  test("admin with none gets a settings hint", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([]);
    const open = vi.fn();
    renderList({ onOpenSettings: open });
    fireEvent.click(await screen.findByRole("button", { name: /settings → services/i }));
    expect(open).toHaveBeenCalled();
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
});
