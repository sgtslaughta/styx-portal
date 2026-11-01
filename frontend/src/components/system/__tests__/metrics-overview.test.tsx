import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";

const insts = ["running", "idle", "paused", "stopped", "error"].map((s, i) => ({ id: String(i), status: s }));
vi.mock("@/hooks/use-instances", () => ({ useInstances: () => ({ data: insts }) }));
vi.mock("@/hooks/use-system", () => ({
  useSystemMetrics: () => ({ data: {
    aggregate_cpu: 12.5, aggregate_ram_mb: 2048, disk_used_gb: 40, disk_total_gb: 100,
    recent_events: [
      { type: "error", instance: "alpha", time: "1m" }, { type: "started", instance: "beta", time: "2m" },
      { type: "stopped", instance: "gamma", time: "3m" }, { type: "started", instance: "delta", time: "4m" },
    ],
    host: { gpu: "RTX 4090", docker_version: "27" } } }),
  useResourceHistory: () => ({ data: { aggregate_cpu: [1, 2, 3], aggregate_ram: [4, 5, 6],
    storage: { volumes_gb: 1, images_gb: 1, total_gb: 100, available_gb: 60 } } }),
}));
vi.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: { ok: false, checked_at: new Date().toISOString(), checks: [
    { key: "docker", ok: true, latency_ms: 1, detail: "" },
    { key: "disk", ok: false, latency_ms: 1, detail: "" },
    { key: "gpu", ok: false, latency_ms: 1, detail: "" }] } }),
}));
import { MetricsOverview } from "../metrics-overview";

test("renders a rollup card per section with figures and links", () => {
  render(<MetricsOverview />);
  for (const s of ["health", "sessions", "resources", "logs"]) {
    const link = screen.getByRole("link", { name: new RegExp(`View ${s}`, "i") });
    expect(link.getAttribute("href")).toBe(`?section=${s}`);
  }
  expect(screen.getByText("2 failing")).toBeTruthy();
  expect(screen.getByText("Disk space")).toBeTruthy();
  const sess = within(screen.getByTestId("card-sessions"));
  for (const l of ["Running", "Idle", "Paused", "Stopped", "Error"]) {
    expect(sess.getAllByText(l).find((n) => n.nextSibling)!.nextSibling?.textContent).toBe("1");
  }
  expect(screen.getByText("12.5%")).toBeTruthy();
  expect(screen.getByText("40.0 / 100 GB")).toBeTruthy();
  expect(screen.getByText("RTX 4090")).toBeTruthy();
  expect(screen.getByText(/1 error event/)).toBeTruthy();
  expect(screen.getByText("gamma")).toBeTruthy();
  expect(screen.queryByText("delta")).toBeNull();
});

test("link dispatches section navigation", () => {
  const h = vi.fn();
  window.addEventListener("styx:settings-section", h);
  render(<MetricsOverview />);
  fireEvent.click(screen.getByRole("link", { name: /View logs/i }));
  expect(h).toHaveBeenCalled();
  expect((h.mock.calls[0]![0] as CustomEvent).detail).toBe("logs");
});
