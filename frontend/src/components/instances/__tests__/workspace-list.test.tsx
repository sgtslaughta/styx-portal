import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();
const data = {
  ws: [] as object[], inst: [] as object[], role: "admin",
  tmpl: [{ id: "t1", image: "lscr.io/linuxserver/nginx:latest", icon: null }],
};
vi.mock("@/api/client", () => ({
  api: {
    myWorkstations: () => Promise.resolve(data.ws), listInstances: () => Promise.resolve(data.inst),
    listTemplates: () => Promise.resolve(data.tmpl), workstationConnectUrl: vi.fn(),
  },
  ApiError: class extends Error {},
}));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: data.role } }) }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
vi.mock("@/lib/connect-wipe", () => ({ openPending: vi.fn(() => Promise.resolve()) }));
import { WorkspaceList } from "../workspace-list";

const studio = {
  id: "w1", name: "Studio", hostname: "studio-host", status: "online", os_info: { pretty_name: "Ubuntu 24.04" },
  gpu_info: {}, icon_kind: "auto", icon_etag: "e", in_use: false, in_use_self: false, in_use_by: null,
  last_heartbeat: ago(4), last_error: null,
};
const inst = (o: object) => ({
  id: "i1", template_id: "t1", name: "Desk", subdomain: "desk", status: "running",
  error_message: null, started_at: ago(3600).replace("Z", ""), created_at: "", ...o,
});

function ui() {
  const onSelect = vi.fn();
  const onLaunch = vi.fn();
  const r = render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <WorkspaceList selection={null} onSelect={onSelect} onLaunch={onLaunch} onOpenSettings={vi.fn()} />
    </QueryClientProvider>,
  );
  return { ...r, onSelect, onLaunch };
}

beforeEach(() => {
  localStorage.clear();
  choose.mockClear();
  data.role = "admin";
  data.ws = [studio];
  data.inst = [inst({}), inst({ id: "i2", name: "Broken", subdomain: "broken", status: "error", error_message: "disk full", started_at: null })];
});

test("one list, two groups, unified rows, status counts in the Instances header", async () => {
  ui();
  expect(await screen.findByRole("button", { name: /Instances · 2/ })).toBeInTheDocument();
  expect(await screen.findByRole("button", { name: /Workstations · 1/ })).toBeInTheDocument();
  expect(screen.getByText(/^Running · up 1h/)).toBeInTheDocument();
  expect(screen.getByText("Error · disk full")).toBeInTheDocument();
  expect(screen.getByTitle("1 running")).toBeInTheDocument();
  expect(screen.getByTitle("1 error")).toBeInTheDocument();
});

test("one search filters both kinds (hostname, template image)", async () => {
  ui();
  await screen.findByRole("button", { name: /^Studio/ });
  await screen.findByRole("button", { name: /^Desk/ });
  const search = screen.getByPlaceholderText("Search workspaces…");
  fireEvent.change(search, { target: { value: "studio-host" } });
  expect(screen.getByRole("button", { name: /^Studio/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Desk/ })).toBeNull();
  expect(screen.getByText("No instances match.")).toBeInTheDocument();
  fireEvent.change(search, { target: { value: "nginx" } });
  expect(await screen.findByRole("button", { name: /^Desk/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /^Studio/ })).toBeNull();
  expect(screen.getByText("No workstations match.")).toBeInTheDocument();
});

test("instance rows select with their kind; quick connect only when running", async () => {
  const { onSelect } = ui();
  fireEvent.click(await screen.findByRole("button", { name: /^Desk/ }));
  expect(onSelect).toHaveBeenCalledWith({ kind: "instance", id: "i1" });
  fireEvent.click(screen.getByRole("button", { name: "Connect to Desk" }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Desk", expect.any(Function));
  expect(screen.queryByRole("button", { name: "Connect to Broken" })).toBeNull();
});

test("Select picks all; row clicks then toggle instead of opening", async () => {
  const { onSelect } = ui();
  await screen.findByRole("button", { name: /^Desk/ });
  fireEvent.click(screen.getByRole("button", { name: "Select" }));
  expect(screen.getByRole("checkbox", { name: "Select Desk" })).toBeChecked();
  expect(screen.getAllByText("2 selected").length).toBeGreaterThan(0);
  fireEvent.click(screen.getByRole("button", { name: /^Desk/ }));
  expect(onSelect).not.toHaveBeenCalled();
  expect(screen.getByRole("checkbox", { name: "Select Desk" })).not.toBeChecked();
});

test("collapsing Instances is remembered", async () => {
  ui();
  fireEvent.click(await screen.findByRole("button", { name: /Instances · 2/ }));
  expect(screen.queryByRole("button", { name: /^Desk/ })).toBeNull();
  expect(localStorage.getItem("styx.home.collapsed.instances")).toBe("1");
});

test("no instances: Launch an instance goes to Templates", async () => {
  data.inst = [];
  const { onLaunch } = ui();
  fireEvent.click(await screen.findByRole("button", { name: "Launch an instance" }));
  expect(onLaunch).toHaveBeenCalled();
});
