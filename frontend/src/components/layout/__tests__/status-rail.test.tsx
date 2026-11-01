import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { StatusRail } from "../status-rail";

const auth = vi.hoisted(() => ({ role: "admin" }));
const st = vi.hoisted(() => ({ ram: 41 as number | undefined, hang: false, fail: false, noInst: false, metrics: vi.fn() }));
vi.mock("@/hooks/use-auth", () => ({ useAuth: () => ({ user: { role: auth.role } }) }));
vi.mock("@/hooks/use-system", () => ({
  useSystemMetrics: () => { st.metrics(); return { data: { aggregate_cpu: 1, aggregate_ram_mb: 400, disk_used_gb: 68, disk_total_gb: 100, host: {}, host_cpu_pct: 23, host_ram_pct: st.ram } }; },
}));
vi.mock("@/hooks/use-instances", () => ({
  useInstances: () => ({ isSuccess: true, data: st.noInst ? [] : [{ id: "1", name: "Chromium", status: "running" }, { id: "2", name: "Bad", status: "error", error_message: null }] }),
}));
vi.mock("@/api/client", () => ({
  api: {
    listWorkstations: () => (st.fail ? Promise.reject(new Error("x")) : st.hang ? new Promise(() => {}) : Promise.resolve([])),
    listServices: async () => [{ id: "s", name: "Paperless", needs_setup: true }],
  },
}));

const wrap = (p = {}) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><StatusRail {...p} /></QueryClientProvider>);

describe("StatusRail", () => {
  beforeEach(() => { auth.role = "admin"; st.ram = 41; st.hang = false; st.fail = false; st.noInst = false; st.metrics.mockClear(); localStorage.clear(); });

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
    expect(await screen.findByText("1 live")).toBeInTheDocument();
    expect(await screen.findByText("2")).toBeInTheDocument();
    expect(screen.getByText("to check")).toBeInTheDocument();
  });

  it("renders nothing for non-admins", () => {
    auth.role = "user";
    const { container } = wrap();
    expect(container).toBeEmptyDOMElement();
  });

  it("shows a dash for unknown memory", () => {
    st.ram = undefined;
    wrap();
    expect(screen.getByText("Memory").nextSibling).toHaveTextContent("—");
    expect(screen.getByText("CPU").nextSibling).toHaveTextContent("23%");
  });

  it("shows no all-clear or badge while queries load", () => {
    st.hang = true;
    wrap({ forceCollapsed: true });
    expect(screen.getByText("— live")).toBeInTheDocument();
    expect(screen.queryByText("to check")).toBeNull();
    expect(screen.queryByText("All clear")).toBeNull();
  });

  it("shows Couldn't load with Retry instead of Loading forever when a query fails", async () => {
    st.fail = true; st.noInst = true;
    wrap();
    expect((await screen.findAllByRole("button", { name: "Retry" })).length).toBeGreaterThan(0);
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("does not fire the metrics query for non-admins", () => {
    auth.role = "user";
    wrap();
    expect(st.metrics).not.toHaveBeenCalled();
  });
});
