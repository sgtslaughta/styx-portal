import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";

const getRelayStats = vi.fn();
vi.mock("@/api/client", () => {
  class ApiError extends Error { status: number; constructor(m: string, s: number) { super(m); this.status = s; } }
  return { ApiError, api: { getRelayStats: (...a: unknown[]) => getRelayStats(...a) } };
});
import { ApiError } from "@/api/client";
import { RelayCostPage } from "../relay-cost-page";

const data = {
  used_gb: 12.4, free_gb: 1000, projected_gb: 31, est_usd: 0, budget_usd: 5, budget_gb: 200, relayed_pct: 18,
  daily: [{ date: "2026-10-30", gb: 1.2 }, { date: "2026-10-31", gb: 2.8 }],
  monthly: [{ month: "2026-10", gb: 12.4 }],
  by_user: [{ name: "Richard", gb: 7 }, { name: "Maya", gb: 1.6 }],
  by_workstation: [{ name: "mini", gb: 9 }],
  reasons: [{ reason: "strict_nat", sessions: 4 }],
};
const wrap = () => render(<QueryClientProvider client={new QueryClient()}><RelayCostPage /></QueryClientProvider>);

test("5 tiles, 5 charts, and Show as table reveals a table", async () => {
  getRelayStats.mockResolvedValue(data);
  wrap();
  await screen.findByText("Relay data used");
  for (const t of ["Relay data used", "Projected month-end", "Estimated cost", "Budget left", "Relayed sessions"]) expect(screen.getByText(t)).toBeTruthy();
  for (const c of ["Relay data per day", "Relay data by month", "By user", "By workstation", "Why sessions were relayed"]) expect(screen.getByRole("region", { name: c })).toBeTruthy();
  expect(screen.getByText("Budget alert at 200 GB")).toBeTruthy();
  expect(screen.getByText("Strict NAT")).toBeTruthy();
  expect(document.querySelector("table")).toBeNull();
  fireEvent.click(screen.getByText("Show as table"));
  expect(document.querySelector("table")).toBeTruthy();
});

test("404 shows the Connect Cloudflare analytics empty state", async () => {
  getRelayStats.mockRejectedValue(new ApiError("nope", 404));
  wrap();
  expect(await screen.findByText(/Connect Cloudflare analytics in/)).toBeTruthy();
});
