import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const { a, toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() }, a: { listServices: vi.fn(), listServicePresets: vi.fn(), listGroups: vi.fn(), discoverContainers: vi.fn(),
  createService: vi.fn(), updateService: vi.fn(), deleteService: vi.fn(), setServiceEnabled: vi.fn(), mountPlan: vi.fn(), mountLatest: vi.fn(), mountApply: vi.fn() } }));
vi.mock("@/api/client", () => ({
  api: new Proxy({}, { get: (_t, k: string) => (...args: unknown[]) => (a as unknown as Record<string, (...x: unknown[]) => unknown>)[k]?.(...args) }),
  ApiError: class extends Error { status = 0; detail: unknown; constructor(m: string, s: number, d?: unknown) { super(m); this.status = s; this.detail = d; } },
}));
vi.mock("sonner", () => ({ toast }));

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ServicesPanel as Panel } from "../services-panel";
const ServicesPanel = () => <QueryClientProvider client={new QueryClient()}><Panel /></QueryClientProvider>;
import { ApiError } from "@/api/client";

const svc = (o: Record<string, unknown> = {}) => ({
  id: "s1", slug: "jellyfin", name: "Jellyfin", icon: null, kind: "url", upstream_url: "http://10.0.0.2:8096",
  container: null, container_port: null, upstream_fallback: null, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [], allowed_groups: [], verify_tls: true, health_path: null, health_status: "healthy",
  health_checked_at: "2026-10-12T10:00:00Z", preset_id: null, enabled: true, created_at: "", updated_at: "", ...o,
});

beforeEach(() => {
  vi.clearAllMocks();
  a.listServices.mockResolvedValue([svc(), svc({ id: "s2", slug: "sonarr", name: "Sonarr", auth_mode: "sso-with-bypass",
    bypass_rules: [{ path_prefix: "/sonarr/api", required_header: null }], health_status: "unhealthy", enabled: false })]);
  a.listServicePresets.mockResolvedValue([]);
  a.listGroups.mockResolvedValue([]);
  a.discoverContainers.mockResolvedValue([]);
  a.setServiceEnabled.mockResolvedValue(undefined);
  a.deleteService.mockResolvedValue(undefined);
});

describe("ServicesPanel", () => {
  test("lists services with slug, mode and auth badges", async () => {
    render(<ServicesPanel />);
    expect(await screen.findByText("Jellyfin")).toBeInTheDocument();
    expect(screen.getByText("/jellyfin")).toBeInTheDocument();
    expect(screen.getByText("SSO, 1 bypass")).toBeInTheDocument();
    expect(screen.getByText("Disabled")).toBeInTheDocument();
    expect(screen.getByLabelText("Health: healthy")).toBeInTheDocument();
    expect(screen.getByLabelText("Health: unhealthy")).toBeInTheDocument();
  });

  test("empty state points to presets", async () => {
    a.listServices.mockResolvedValue([]);
    render(<ServicesPanel />);
    expect(await screen.findByText(/no services yet/i)).toBeInTheDocument();
    expect(screen.getByText(/start from a preset/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /browse presets/i })).toBeInTheDocument();
  });

  test("error with retry", async () => {
    a.listServices.mockRejectedValueOnce(new Error("boom"));
    render(<ServicesPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/boom/);
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(await screen.findByText("Jellyfin")).toBeInTheDocument();
  });

  test("enable toggle calls the api and reloads", async () => {
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("switch", { name: "Enable Sonarr" }));
    await waitFor(() => expect(a.setServiceEnabled).toHaveBeenCalledWith("s2", true));
    await waitFor(() => expect(a.listServices).toHaveBeenCalledTimes(2));
  });

  test("delete confirms then calls the api", async () => {
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("button", { name: "Delete Jellyfin" }));
    const dlg = await screen.findByRole("dialog");
    fireEvent.click(within(dlg).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(a.deleteService).toHaveBeenCalledWith("s1"));
  });

  test("create: 409 surfaces next to the slug field, no toast", async () => {
    a.createService.mockRejectedValue(new ApiError("Slug already in use", 409, "Slug already in use"));
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("button", { name: /add service/i }));
    const dlg = await screen.findByRole("dialog");
    const ch = (l: string, v: string) => fireEvent.change(within(dlg).getByLabelText(l), { target: { value: v } });
    ch("Slug", "dup"); ch("Name", "Dup"); ch("Upstream URL", "http://h:1");
    fireEvent.click(within(dlg).getByLabelText(/I understand that this app runs on the same origin/));
    fireEvent.click(within(dlg).getByRole("button", { name: /^save$/i }));
    expect(await within(dlg).findByText("Slug already in use")).toBeInTheDocument();
    expect(toast.error).not.toHaveBeenCalled();
  });

  test("create: unmapped error toasts", async () => {
    a.createService.mockRejectedValue(new Error("db down"));
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("button", { name: /add service/i }));
    const dlg = await screen.findByRole("dialog");
    const ch = (l: string, v: string) => fireEvent.change(within(dlg).getByLabelText(l), { target: { value: v } });
    ch("Slug", "n"); ch("Name", "N"); ch("Upstream URL", "http://h:1");
    fireEvent.click(within(dlg).getByLabelText(/I understand that this app runs on the same origin/));
    fireEvent.click(within(dlg).getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("db down"));
  });

  test("edit sends update without slug and closes", async () => {
    a.updateService.mockResolvedValue(svc());
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("button", { name: "Edit Jellyfin" }));
    const dlg = await screen.findByRole("dialog");
    fireEvent.click(within(dlg).getByLabelText(/I understand that this app runs on the same origin/));
    fireEvent.click(within(dlg).getByRole("button", { name: /^save$/i }));
    await waitFor(() => expect(a.updateService).toHaveBeenCalled());
    const [id, body] = a.updateService.mock.calls[0] ?? [];
    expect(id).toBe("s1");
    expect(body).not.toHaveProperty("slug");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("risky choices get explicit badges", async () => {
    a.listServices.mockResolvedValue([svc({ mount_mode: "cookie-root", auth_mode: "app-native", verify_tls: false })]);
    render(<ServicesPanel />);
    expect(await screen.findByText("Cookie root")).toBeInTheDocument();
    expect(screen.getByText("No Styx login")).toBeInTheDocument();
    expect(screen.getByText("TLS unverified")).toBeInTheDocument();
  });

  test("form remounts with focus mode after the switch", async () => {
    const dock = svc({ id: "s3", slug: "sonarr", name: "Sonarr", kind: "docker-local", container: "sonarr", container_port: 8989, url: null, upstream_url: null });
    a.listServices.mockResolvedValue([dock]);
    a.mountPlan.mockResolvedValue({ method: "config_file", changes: [{ target: "/c", key: "k", old: "", new: "/sonarr" }], needs_consent: false, reason: null });
    a.mountLatest.mockResolvedValue({ id: "j", state: "rolled_back", changes: [], backup_dir: "/b", log_excerpt: "x", created_at: "", finished_at: "", steps: [] });
    a.updateService.mockResolvedValue({ ...dock, mount_mode: "cookie-root", updated_at: "2" });
    render(<ServicesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Sonarr" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use focus mode instead" }));
    expect(await screen.findByText("Focus: opens on its own")).toBeInTheDocument();
  });
});
