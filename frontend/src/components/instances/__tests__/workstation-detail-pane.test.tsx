import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import type { Workstation } from "@/api/client";

const connectUrl = vi.fn();
vi.mock("@/api/client", () => ({ api: { workstationConnectUrl: (...a: unknown[]) => connectUrl(...a) }, ApiError: class extends Error {} }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn();
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: unknown[]) => openPending(...a) }));
import { WorkstationDetailPane } from "../workstation-detail-pane";

const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();
const ws = (o: object = {}) => ({
  id: "w1", name: "Studio", status: "online", display_server: "wayland",
  os_info: { pretty_name: "Ubuntu 24.04" }, gpu_info: { model: "RTX 4090" }, agent_version: "0.7.0", agent_outdated: true,
  icon_kind: "auto", icon_etag: "e", in_use: false, in_use_self: false, in_use_by: null,
  last_heartbeat: ago(4), last_error: null, ...o,
}) as unknown as Workstation;
const fact = (k: string) => screen.getByText(k).nextElementSibling;

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  openPending.mockResolvedValue(undefined);
});

test("online and free: Connect, facts grid, seen line", () => {
  render(<WorkstationDetailPane ws={ws()} />);
  expect(screen.getByRole("heading", { level: 2, name: "Studio" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
  expect(fact("System")).toHaveTextContent("Ubuntu 24.04");
  expect(fact("GPU")).toHaveTextContent("RTX 4090");
  expect(fact("Display")).toHaveTextContent("wayland");
  expect(fact("Agent")).toHaveTextContent("v0.7.0 · update available");
  expect(screen.getByText(/^seen \d+s ago$/)).toBeInTheDocument();
});

test("Open in new tab skips the preference prompt", () => {
  render(<WorkstationDetailPane ws={ws()} />);
  fireEvent.click(screen.getByRole("button", { name: "Open in new tab" }));
  expect(choose).not.toHaveBeenCalled();
  expect(openPending).toHaveBeenCalledWith("new_tab", "Connecting to Studio…", expect.any(Function));
});

test("in use by someone else: Join with confirm", async () => {
  render(<WorkstationDetailPane ws={ws({ in_use: true, in_use_by: "bob" })} />);
  fireEvent.click(screen.getByRole("button", { name: "Join" }));
  expect(await screen.findByText('Join "Studio"?')).toBeInTheDocument();
});

test("connected by me: Reconnect", () => {
  render(<WorkstationDetailPane ws={ws({ in_use: true, in_use_self: true })} />);
  expect(screen.getByRole("button", { name: "Reconnect" })).toBeEnabled();
});

test("offline: disabled, greyscale hero, last seen and the last error", () => {
  render(<WorkstationDetailPane ws={ws({ status: "offline", last_heartbeat: ago(2 * 86_400 + 60), last_error: "agent stopped" })} />);
  expect(screen.getByRole("button", { name: "Offline" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Open in new tab" })).toBeNull();
  expect(screen.getByText("Offline · last seen 2 days ago")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("agent stopped");
  expect(screen.getByTestId("pane-hero").className).toContain("grayscale");
});

test("missing system data reads plainly", () => {
  render(<WorkstationDetailPane ws={ws({ os_info: {}, gpu_info: {}, agent_version: "", last_heartbeat: null })} />);
  expect(fact("System")).toHaveTextContent("Linux");
  expect(fact("GPU")).toHaveTextContent("None detected");
  expect(fact("Agent")).toHaveTextContent("—");
  expect(screen.queryByText(/seen/)).toBeNull();
});
