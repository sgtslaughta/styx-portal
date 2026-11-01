import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StatusRail } from "../status-rail";

const auth = vi.hoisted(() => ({ role: "admin" }));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: auth.role } }) }));
vi.mock("@/hooks/use-system", () => ({
  useSystemMetrics: () => ({ data: { aggregate_cpu: 23, aggregate_ram_mb: 400, disk_used_gb: 68, disk_total_gb: 100, host: {} } }),
}));
vi.mock("@/hooks/use-instances", () => ({
  useInstances: () => ({ data: [{ id: "1", name: "Chromium", status: "running" }, { id: "2", name: "Bad", status: "error", error_message: null }] }),
}));
vi.mock("@/api/client", () => ({
  api: {
    listWorkstations: async () => [],
    listServices: async () => [{ id: "s", name: "Paperless", needs_setup: true }],
  },
}));

const wrap = (p = {}) => render(<QueryClientProvider client={new QueryClient()}><StatusRail {...p} /></QueryClientProvider>);

describe("StatusRail", () => {
  beforeEach(() => { auth.role = "admin"; localStorage.clear(); });

  it("toggle flips aria-expanded and persists", async () => {
    wrap();
    const b = screen.getByRole("button", { name: "Collapse status panel" });
    expect(b).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(b);
    expect(screen.getByRole("button", { name: "Expand status panel" })).toHaveAttribute("aria-expanded", "false");
    expect(localStorage.getItem("styxRail")).toBe("closed");
    await userEvent.click(screen.getByRole("button", { name: "Expand status panel" }));
    expect(localStorage.getItem("styxRail")).toBe("open");
  });

  it("forceCollapsed shows CPU, live count and to-check badge", async () => {
    wrap({ forceCollapsed: true });
    expect(screen.getByText("CPU 23%")).toBeInTheDocument();
    expect(screen.getByText("1 live")).toBeInTheDocument();
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("to check")).toBeInTheDocument();
  });

  it("renders nothing for non-admins", () => {
    auth.role = "user";
    const { container } = wrap();
    expect(container).toBeEmptyDOMElement();
  });
});
