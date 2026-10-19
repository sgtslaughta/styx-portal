import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";

const data = {
  role: "admin",
  ws: [{ id: "w1", name: "Studio", status: "online", os_info: {}, gpu_info: {}, display_server: "x11", agent_version: "0.7.0",
    agent_outdated: false, icon_kind: "auto", icon_etag: "e", in_use: false, in_use_self: false, in_use_by: null,
    last_heartbeat: null, last_error: null }],
  inst: [{ id: "i1", name: "Desk", status: "running" }],
};
vi.mock("@/api/client", () => ({
  api: { myWorkstations: () => Promise.resolve(data.ws), listInstances: () => Promise.resolve(data.inst) },
  ApiError: class extends Error {},
}));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: data.role } }) }));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => vi.fn() }));
vi.mock("../instance-detail-pane", () => ({
  InstanceDetailPane: ({ instanceId }: { instanceId: string }) => <p>inst-pane-{instanceId}</p>,
}));
vi.mock("../workspace-list", () => ({
  WorkspaceList: ({ onSelect }: { onSelect: (s: { kind: string; id: string }) => void }) => (
    <div>
      <button onClick={() => onSelect({ kind: "workstation", id: "w1" })}>pick-ws</button>
      <button onClick={() => onSelect({ kind: "instance", id: "i1" })}>pick-inst</button>
    </div>
  ),
}));
import { InstanceWorkspace } from "../instance-workspace";

const GUIDE = "Pick a workspace on the left to see it here.";
function ui() {
  const onLaunch = vi.fn();
  const onOpenSettings = vi.fn();
  render(<QueryClientProvider client={new QueryClient()}><InstanceWorkspace onLaunch={onLaunch} onOpenSettings={onOpenSettings} /></QueryClientProvider>);
  return { onLaunch, onOpenSettings };
}

beforeEach(() => { localStorage.clear(); data.role = "admin"; });

test("nothing opened yet: a guide card with both actions", () => {
  const { onLaunch, onOpenSettings } = ui();
  expect(screen.getByText(GUIDE)).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Add a workstation" }));
  expect(onOpenSettings).toHaveBeenCalledWith("workstations");
  fireEvent.click(screen.getByRole("button", { name: "Launch an instance" }));
  expect(onLaunch).toHaveBeenCalled();
});

test("members get no Add a workstation", () => {
  data.role = "user";
  ui();
  expect(screen.queryByRole("button", { name: "Add a workstation" })).toBeNull();
});

test("the most recently opened workstation fills the pane", async () => {
  localStorage.setItem("styx.home.recent", JSON.stringify({ kind: "workstation", id: "w1" }));
  ui();
  expect(await screen.findByRole("heading", { level: 2, name: "Studio" })).toBeInTheDocument();
});

test("a recent instance shows the instance pane", async () => {
  localStorage.setItem("styx.home.recent", JSON.stringify({ kind: "instance", id: "i1" }));
  ui();
  expect(await screen.findByText("inst-pane-i1")).toBeInTheDocument();
});

test("a recent workspace that is gone falls back to the guide", async () => {
  localStorage.setItem("styx.home.recent", JSON.stringify({ kind: "instance", id: "gone" }));
  ui();
  fireEvent.click(screen.getByText("pick-ws")); // proves data loaded, then clear the pick
  await screen.findByRole("heading", { level: 2, name: "Studio" });
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText(GUIDE)).toBeInTheDocument();
});

test("picking switches kinds; Back clears the pick", async () => {
  ui();
  fireEvent.click(screen.getByText("pick-inst"));
  expect(await screen.findByText("inst-pane-i1")).toBeInTheDocument();
  fireEvent.click(screen.getByText("pick-ws"));
  expect(await screen.findByRole("heading", { level: 2, name: "Studio" })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  expect(await screen.findByText(GUIDE)).toBeInTheDocument();
});
