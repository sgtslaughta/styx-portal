import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { test, expect, vi } from "vitest";
import { WorkstationList, WorkstationPreview } from "../workstation-list";
import type { Workstation } from "@/api/client";

let rows: Workstation[] = [];
const connectUrl = vi.fn();
const baseRow = {
  id: "w9", name: "Studio", hostname: "h", status: "online", os_info: {}, icon_kind: "emoji",
  icon_etag: "e1", in_use: false, in_use_self: false, in_use_by: null, last_heartbeat: null,
  last_error: null, stream_settings: {}, gpu_info: {},
} as unknown as Workstation;
const row = baseRow;
rows = [row];

const choose = vi.fn((_g: string, _n: string, run: (m: string) => void) => run("new_tab"));
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn((_m: string, _l: string, get: () => Promise<string>) => get());
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: Parameters<typeof openPending>) => openPending(...a) }));

vi.mock("@/api/client", () => ({
  api: { workstationThumbUrl: (id: string) => `/api/workstations/${id}/thumbnail`, myWorkstations: () => Promise.resolve(rows),
    workstationConnectUrl: (...a: unknown[]) => connectUrl(...a) },
  ApiError: class extends Error {},
}));

test("tile renders icon img with etag cache-buster", async () => {
  const { container } = render(<WorkstationList />);
  await screen.findByText("Studio");
  const img = container.querySelector('img[src^="/api/workstations/w9/icon"]')!;
  expect(img.getAttribute("src")).toBe("/api/workstations/w9/icon?v=e1");
  expect(img.getAttribute("alt")).toBe("");
});

test("Connect asks via the Workspaces preference and connects", async () => {
  rows = [row];
  connectUrl.mockResolvedValue({ url: "/w/studio/" });
  render(<WorkstationList />);
  fireEvent.click(await screen.findByRole("button", { name: "Connect" }));
  expect(choose).toHaveBeenCalledWith("workspaces", "Studio", expect.any(Function));
  expect(openPending.mock.calls[0]![1]).toBe("Connecting to Studio…");
  await waitFor(() => expect(connectUrl).toHaveBeenCalledWith("w9", false));
});

test("Connect on a workstation in use by someone else confirms takeover first", async () => {
  openPending.mockClear();
  rows = [{ ...row, in_use: true, in_use_self: false, in_use_by: "bob" } as Workstation];
  render(<WorkstationList />);
  fireEvent.click(await screen.findByRole("button", { name: "Connect" }));
  await screen.findByText('Take over "Studio"?');
  expect(openPending).not.toHaveBeenCalled();
});

test("online workstation row shows a thumbnail from the contract URL", async () => {
  rows = [row];
  const { container } = render(<WorkstationList />);
  await screen.findByText("Studio");
  expect(container.querySelector('img[src="/api/workstations/w9/thumbnail?t=0"]')).not.toBeNull();
});

test("clicking a row selects it without connecting; Connect button does not select", async () => {
  rows = [row];
  openPending.mockClear();
  const onSelect = vi.fn();
  render(<WorkstationList selectedId="w9" onSelect={onSelect} />);
  const opt = await screen.findByRole("option", { name: /Studio/ });
  expect(opt.getAttribute("aria-selected")).toBe("true");
  fireEvent.click(opt);
  expect(onSelect).toHaveBeenCalledTimes(1);
  fireEvent.keyDown(opt, { key: "Enter" });
  expect(onSelect).toHaveBeenCalledTimes(2);
  expect(openPending).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Connect" }));
  expect(onSelect).toHaveBeenCalledTimes(2);
});

test("preview shows name and thumbnail", () => {
  const { container } = render(<WorkstationPreview ws={row} />);
  expect(screen.getByText("Studio")).toBeTruthy();
  expect(container.querySelector('img[src="/api/workstations/w9/thumbnail?t=0"]')).not.toBeNull();
});
