import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

let rows: unknown[] = [];
vi.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: rows }) }));
vi.mock("@/api/client", () => ({ api: { listWorkstations: vi.fn() } }));
import { WorkstationsOverviewCard } from "../workstations-overview-card";

const ws = (o: Record<string, unknown>) => ({
  status: "online", in_use: false, in_use_by: null, agent_outdated: false,
  update_state: "idle", stream_settings: {}, ...o,
});

test("figures and warn status", () => {
  rows = [
    ws({ in_use: true, in_use_by: "alice", stream_settings: { transport: "webrtc" } }),
    ws({ in_use: true, in_use_by: "bob" }),
    ws({ in_use: true, in_use_by: "carol" }),
    ws({ status: "offline", agent_outdated: true }),
  ];
  render(<WorkstationsOverviewCard />);
  const c = within(screen.getByTestId("card-workstations"));
  expect(c.getByText("3 / 1 / 0")).toBeTruthy();
  expect(c.getByText("3 (alice, bob)")).toBeTruthy();
  expect(c.getByText("1 WebRTC / 3 other")).toBeTruthy();
  expect(c.getByText("Warning")).toBeTruthy();
});

test("error on rolled back update, and link event", () => {
  rows = [ws({ update_state: "rolled_back" })];
  render(<WorkstationsOverviewCard />);
  expect(screen.getByText("Error")).toBeTruthy();
  const h = vi.fn();
  window.addEventListener("styx:settings-section", h);
  const link = screen.getByRole("link", { name: /View workstations/i });
  expect(link.getAttribute("href")).toBe("?section=workstations");
  fireEvent.click(link);
  expect((h.mock.calls[0]![0] as CustomEvent).detail).toBe("workstations");
});

test("ok when healthy", () => {
  rows = [ws({})];
  render(<WorkstationsOverviewCard />);
  expect(screen.getByText("OK")).toBeTruthy();
});
