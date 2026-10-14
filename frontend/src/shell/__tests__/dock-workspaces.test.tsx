import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
const ws = (o: object) => ({ id: "w1", name: "Studio", status: "online", in_use: false, in_use_self: false,
  in_use_by: null, icon_kind: "auto", icon_etag: "e", os_info: {}, ...o });
const inst = (o: object) => ({ id: "i1", name: "Desk", subdomain: "desk", status: "running", ...o });
const data = { ws: [] as object[], inst: [] as object[] };
vi.mock("@/api/client", () => ({ api: {
  myWorkstations: () => Promise.resolve(data.ws), listInstances: () => Promise.resolve(data.inst),
  workstationConnectUrl: () => Promise.resolve({ url: "/w/studio/" }),
} }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
vi.mock("@/lib/connect-wipe", () => ({ openPending: vi.fn(() => Promise.resolve()) }));
import { DockWorkspaces } from "../dock-workspaces";

const ui = (onPicked = vi.fn()) =>
  render(<QueryClientProvider client={new QueryClient()}><DockWorkspaces onPicked={onPicked} /></QueryClientProvider>);

test("lists workspaces with status; unavailable ones are disabled", async () => {
  data.ws = [ws({}), ws({ id: "w2", name: "Lab", status: "offline" }),
    ws({ id: "w3", name: "Shared", in_use: true, in_use_by: "bob" })];
  data.inst = [inst({}), inst({ id: "i2", name: "Old", status: "stopped" })];
  ui();
  expect(await screen.findByRole("button", { name: /Studio.*online/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Lab.*offline/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Shared.*in use by bob/ })).toBeDisabled();
  expect(screen.getByRole("button", { name: /Desk.*running/ })).toBeEnabled();
  expect(screen.getByRole("button", { name: /Old.*stopped/ })).toBeDisabled();
});

test("click closes the dock then asks via the Workspaces preference", async () => {
  data.ws = [ws({})]; data.inst = [];
  const onPicked = vi.fn();
  ui(onPicked);
  fireEvent.click(await screen.findByRole("button", { name: /Studio/ }));
  expect(onPicked).toHaveBeenCalled();
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
});

test("empty state", async () => {
  data.ws = []; data.inst = [];
  ui();
  expect(await screen.findByText("No workspaces yet")).toBeInTheDocument();
});
