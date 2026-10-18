import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";

const inst = { id: "1", name: "Desk", subdomain: "desk", status: "running", started_at: null, last_activity: null };
vi.mock("@/hooks/use-instances", () => {
  const m = () => ({ mutate: vi.fn() });
  return { useInstances: () => ({ data: [inst] }), useStartInstance: m, useStopInstance: m, useRestartInstance: m,
    usePauseInstance: m, useUnpauseInstance: m, useDeleteInstance: m };
});
vi.mock("@/hooks/use-system", () => ({ useSessionEvents: () => ({ data: [] }) }));
const choose = vi.fn();
vi.mock("@/components/open-prompt", () => ({ useOpenChoice: () => choose }));
const openPending = vi.fn(() => Promise.resolve());
vi.mock("@/lib/connect-wipe", () => ({ openPending: (...a: unknown[]) => openPending(...(a as [])) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn() } }));
import { MetricsSessions } from "../metrics-sessions";

test("Connect honours the Workspaces preference", async () => {
  render(<MetricsSessions />);
  fireEvent.click(screen.getByTitle("Connect"));
  expect(choose).toHaveBeenCalledWith("workspaces", "Desk", expect.any(Function));
  (choose.mock.calls[0]![2] as (m: string) => void)("same_tab");
  expect(openPending).toHaveBeenCalledWith("same_tab", "Launching Desk…", expect.any(Function));
});
