import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const role = { current: "user" };
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { id: "u", role: role.current } }) }));
const listServiceTiles = vi.fn<() => Promise<unknown>>();
const enterService = vi.fn(async (_s: string) => undefined);
vi.mock("@/api/client", () => ({
  api: { listServiceTiles: () => listServiceTiles(), enterService: (s: string) => enterService(s) },
}));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));

import { ServiceList } from "../service-list";

const tile = (o: object) => ({ id: "1", slug: "sonarr", name: "Sonarr", icon: "📺", mount_mode: "path", enabled: true, up: true, ...o });

beforeEach(() => {
  role.current = "user";
  localStorage.clear();
  listServiceTiles.mockReset();
  enterService.mockClear();
});

describe("ServiceList", () => {
  test("path tile is a plain link, even when down; unknown is neutral", async () => {
    listServiceTiles.mockResolvedValue([tile({ up: false }), tile({ id: "3", slug: "x", name: "X", up: null })]);
    render(<ServiceList />);
    const link = await screen.findByRole("link", { name: /open sonarr/i });
    expect(link).toHaveAttribute("href", "/sonarr/");
    expect(screen.getByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText("Status unknown")).toBeInTheDocument();
  });

  test("cookie-root tile enters then navigates to /", async () => {
    const assign = vi.fn();
    Object.defineProperty(window, "location", { value: { assign }, writable: true });
    listServiceTiles.mockResolvedValue([tile({ id: "2", slug: "unraid", name: "Unraid", mount_mode: "cookie-root" })]);
    render(<ServiceList />);
    fireEvent.click(await screen.findByRole("button", { name: /open unraid/i }));
    await waitFor(() => expect(enterService).toHaveBeenCalledWith("unraid"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("/"));
  });

  test("members with no services see nothing", async () => {
    listServiceTiles.mockResolvedValue([]);
    const { container } = render(<ServiceList />);
    await waitFor(() => expect(listServiceTiles).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  test("list is fetched on every mount (no shared cache)", async () => {
    listServiceTiles.mockResolvedValueOnce([tile({})]).mockResolvedValueOnce([]);
    const a = render(<ServiceList />);
    await screen.findByText("Sonarr");
    a.unmount();
    const b = render(<ServiceList />);
    await waitFor(() => expect(listServiceTiles).toHaveBeenCalledTimes(2));
    expect(b.container).toBeEmptyDOMElement();
  });

  test("admin with none gets a settings hint", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([]);
    const open = vi.fn();
    render(<ServiceList onOpenSettings={open} />);
    fireEvent.click(await screen.findByRole("button", { name: /settings → services/i }));
    expect(open).toHaveBeenCalled();
  });

  test("admin full model maps health_status; tip shown to admins only and dismissible", async () => {
    role.current = "admin";
    listServiceTiles.mockResolvedValue([{ ...tile({}), up: undefined, health_status: "unhealthy" }]);
    render(<ServiceList />);
    expect(await screen.findByText("Unreachable")).toBeInTheDocument();
    expect(screen.getByText(/open apps with a non-admin account/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /dismiss tip/i }));
    expect(screen.queryByText(/non-admin account/i)).toBeNull();
    expect(localStorage.getItem("styx.serviceTipDismissed")).toBe("1");
  });

  test("members never see the tip", async () => {
    listServiceTiles.mockResolvedValue([tile({})]);
    render(<ServiceList />);
    await screen.findByText("Sonarr");
    expect(screen.queryByText(/non-admin account/i)).toBeNull();
  });
});
