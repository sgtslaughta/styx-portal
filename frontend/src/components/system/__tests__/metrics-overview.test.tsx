import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";

const series = (n: number, v: number | null) => Array.from({ length: 24 }, (_, i) => (i === 3 ? null : v ?? n + i));
const overview = {
  tiles: { cpu: { now: 23, series: series(10, null) }, ram: { now: 41, series: series(30, null) }, disk: { now: 68, series: series(60, null) }, live: { now: 2, series: series(0, 2) } },
  health_hours: [...Array(22).fill("ok"), "warn", null],
  load: { labels: ["a", "b"], cpu: [10, null], ram: [30, 31] },
  sessions_per_day: [{ date: "2026-10-31", count: 3 }],
};
vi.mock("@/api/client", () => ({
  ApiError: class extends Error {},
  api: {
    getOverviewStats: async () => overview,
    getStreamingStats: async () => ({ rows: [{ workstation: "mini", sub: "online", parts: { Richard: 3, Maya: 1 } }] }),
    getDiagnostics: async () => ({ ok: true, checked_at: "", checks: [{ key: "docker", ok: true }, { key: "disk", ok: true }] }),
    getSystemSettings: async () => [{ group: "g", label: "g", settings: [
      { key: "CLOUDFLARE_ACCOUNT_ID", type: "str", value: "abc" }, { key: "CLOUDFLARE_ANALYTICS_TOKEN", type: "secret", value: null, is_set: true }] }],
    getRelayStats: async () => ({ used_gb: 12.4, free_gb: 1000, projected_gb: 31, est_usd: 0, budget_usd: 5, relayed_pct: 18, daily: [], monthly: [], by_user: [], by_workstation: [], reasons: [] }),
    getSystemMetrics: async () => ({ disk_used_gb: 68, disk_total_gb: 100, host_ram_total_mb: 32768 }),
    listWorkstations: async () => [], listServices: async () => [{ id: "p", name: "Paperless", needs_setup: true }],
    stopInstance: async () => ({}),
  },
}));
vi.mock("@/hooks/use-instances", () => ({ useInstances: () => ({ isSuccess: true, data: [{ id: "1", name: "Chromium", status: "running" }] }) }));
vi.mock("@/hooks/use-system", () => ({ useSystemMetrics: () => ({ data: { disk_used_gb: 68, disk_total_gb: 100, host_ram_total_mb: 32768 } }) }));
import { MetricsOverview } from "../metrics-overview";

test("tiles, three charts, and the lists (incl. Relay cost card when configured)", async () => {
  render(<QueryClientProvider client={new QueryClient()}><MetricsOverview /></QueryClientProvider>);
  expect(await screen.findByText("23%")).toBeTruthy();
  for (const t of ["CPU", "Memory", "Disk", "Live sessions", "Health"]) expect(screen.getAllByText(t).length).toBeGreaterThan(0);
  expect(screen.getByText("2/2")).toBeTruthy();
  for (const c of ["Server load", "Sessions per day", "Streaming time"]) expect(screen.getByRole("region", { name: c })).toBeTruthy();
  expect(await screen.findByText("Paperless isn't set up")).toBeTruthy();
  expect(screen.getByRole("region", { name: "Active now" })).toBeTruthy();
  expect(await screen.findByText("Breakdown")).toBeTruthy();
  const cells = screen.getByRole("img", { name: /Health, last 24 hours/ }).children;
  expect(cells).toHaveLength(24);
  expect(cells[23]!.getAttribute("title")).toContain("No data");
});
