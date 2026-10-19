import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { Workstation } from "@/api/client";

const data = { rows: [] as Workstation[], role: "admin" };
vi.mock("@/api/client", () => ({
  api: { myWorkstations: () => Promise.resolve(data.rows), workstationConnectUrl: vi.fn() },
  ApiError: class extends Error {},
}));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: data.role } }) }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
vi.mock("@/lib/connect-wipe", () => ({ openPending: vi.fn(() => Promise.resolve()) }));
import { WorkstationGroup } from "../workstation-group";

const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();
const ws = (o: object = {}) => ({
  id: "w1", name: "Studio", hostname: "studio-host", status: "online", os_info: { pretty_name: "Ubuntu 24.04" },
  gpu_info: {}, icon_kind: "auto", icon_etag: "e", in_use: false, in_use_self: false, in_use_by: null,
  last_heartbeat: ago(4), last_error: null, ...o,
}) as unknown as Workstation;

function ui(props: Partial<Parameters<typeof WorkstationGroup>[0]> = {}) {
  const onSelect = vi.fn();
  const onOpenSettings = vi.fn();
  const r = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WorkstationGroup query="" selection={null} onSelect={onSelect} onOpenSettings={onOpenSettings} {...props} />
    </QueryClientProvider>,
  );
  return { ...r, onSelect, onOpenSettings };
}
const names = () => screen.getAllByRole("button", { name: /^(Studio|Lab)/ }).map((r) => r.textContent?.slice(0, 3));

beforeEach(() => {
  localStorage.clear();
  choose.mockClear();
  data.role = "admin";
  data.rows = [ws({ id: "w2", name: "Lab", hostname: "lab-host", status: "offline", last_heartbeat: ago(2 * 86_400 + 60) }), ws()];
});

test("rows: online first, one secondary line each", async () => {
  ui();
  expect(await screen.findByRole("button", { name: /Workstations · 2/ })).toHaveAttribute("aria-expanded", "true");
  expect(names()).toEqual(["Stu", "Lab"]);
  expect(screen.getByText(/^Ubuntu 24\.04 · seen \d+s ago$/)).toBeInTheDocument();
  expect(screen.getByText("Offline · 2 days")).toBeInTheDocument();
});

test("row click selects a workstation; quick connect only when online", async () => {
  const { onSelect } = ui();
  fireEvent.click(await screen.findByRole("button", { name: /^Studio/ }));
  expect(onSelect).toHaveBeenCalledWith({ kind: "workstation", id: "w1" });
  fireEvent.click(screen.getByRole("button", { name: "Connect to Studio" }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
  expect(screen.queryByRole("button", { name: "Connect to Lab" })).toBeNull();
});

test("search matches hostname", async () => {
  ui({ query: "lab-host" });
  expect(await screen.findByRole("button", { name: /^Lab/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Studio/ })).toBeNull();
});

test("a search with no hits says so instead of the empty-state action", async () => {
  ui({ query: "zzz" });
  expect(await screen.findByText("No workstations match.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add a workstation" })).toBeNull();
});

test("sort by name", async () => {
  ui();
  fireEvent.change(await screen.findByRole("combobox", { name: "Sort workstations" }), { target: { value: "name" } });
  expect(names()).toEqual(["Lab", "Stu"]);
});

test("collapse is remembered per browser", async () => {
  const { unmount } = ui();
  fireEvent.click(await screen.findByRole("button", { name: /Workstations · 2/ }));
  expect(screen.queryByRole("button", { name: /^Studio/ })).toBeNull();
  expect(localStorage.getItem("styx.home.collapsed.workstations")).toBe("1");
  unmount();
  ui();
  expect(await screen.findByRole("button", { name: /Workstations · 2/ })).toHaveAttribute("aria-expanded", "false");
});

test("blocked storage: collapse still toggles for the session", async () => {
  const g = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  const s = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  try {
    ui();
    const header = await screen.findByRole("button", { name: /Workstations · 2/ });
    fireEvent.click(header);
    expect(header).toHaveAttribute("aria-expanded", "false");
  } finally { g.mockRestore(); s.mockRestore(); }
});

test("empty: admin gets Add a workstation, members a plain line", async () => {
  data.rows = [];
  const { onOpenSettings, unmount } = ui();
  fireEvent.click(await screen.findByRole("button", { name: "Add a workstation" }));
  expect(onOpenSettings).toHaveBeenCalledWith("workstations");
  unmount();
  data.role = "user";
  ui();
  expect(await screen.findByText("No workstations shared with you yet.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Add a workstation" })).toBeNull();
});
