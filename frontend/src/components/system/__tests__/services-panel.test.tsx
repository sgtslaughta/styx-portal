import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";

const { a, toast } = vi.hoisted(() => ({ toast: { error: vi.fn(), success: vi.fn() }, a: { listServices: vi.fn(), listServicePresets: vi.fn(), listGroups: vi.fn(), discoverContainers: vi.fn(),
  createService: vi.fn(), updateService: vi.fn(), deleteService: vi.fn(), setServiceEnabled: vi.fn(), mountPlan: vi.fn(), mountLatest: vi.fn(), mountApply: vi.fn(), setServiceIcon: vi.fn(), refreshServiceIcon: vi.fn() } }));
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
  id: "s1", slug: "jellyfin", name: "Jellyfin", icon_kind: "auto", icon_etag: "e", kind: "url", upstream_url: "http://10.0.0.2:8096",
  container: null, container_port: null, upstream_fallback: null, mount_mode: "path", auth_mode: "sso",
  bypass_rules: [], allowed_groups: [], verify_tls: true, health_path: null, health_status: "healthy",
  health_checked_at: "2026-10-12T10:00:00Z", preset_id: null, enabled: true, created_at: "", updated_at: "", needs_setup: false, ...o,
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

  test("discovery buttons read Add from running container", async () => {
    render(<ServicesPanel />);
    expect(await screen.findByRole("button", { name: "Add from running container" })).toBeInTheDocument();
  });

  test("empty state discovery button is renamed too", async () => {
    a.listServices.mockResolvedValue([]);
    render(<ServicesPanel />);
    await screen.findByText(/no services yet/i);
    expect(screen.getAllByRole("button", { name: "Add from running container" })).toHaveLength(2);
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
    a.mountLatest.mockResolvedValue({ id: "j", state: "rolled_back", changes: [], backup_dir: "/b", changed: false, log_excerpt: "x", created_at: "", finished_at: "", steps: [] });
    a.updateService.mockResolvedValue({ ...dock, mount_mode: "cookie-root", updated_at: "2" });
    render(<ServicesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Sonarr" }));
    fireEvent.click(await screen.findByRole("button", { name: "Use focus mode instead" }));
    expect(await screen.findByText("Focus: opens full screen")).toBeInTheDocument();
  });

  test("base path section renders inside the drawer's scroll body", async () => {
    const dock = svc({ id: "s3", slug: "sonarr", name: "Sonarr", kind: "docker-local", container: "sonarr", container_port: 8989, url: null, upstream_url: null });
    a.listServices.mockResolvedValue([dock]);
    a.mountPlan.mockResolvedValue({ method: "config_file", changes: [{ target: "/c", key: "k", old: "", new: "/sonarr" }], needs_consent: false, reason: null });
    a.mountLatest.mockRejectedValue(Object.assign(new Error("nf"), { status: 404 }));
    render(<ServicesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Sonarr" }));
    const region = await screen.findByRole("region", { name: "Base path" });
    expect(region.closest('[data-slot="drawer-body"]')).not.toBeNull();
  });

  test("row shows the last mount outcome on a fresh page load", async () => {
    const dock = svc({ id: "s3", slug: "sonarr", name: "Sonarr", kind: "docker-local", container: "sonarr", container_port: 8989, url: null, upstream_url: null });
    a.listServices.mockResolvedValue([dock]);
    a.mountLatest.mockResolvedValue({ id: "j", state: "rolled_back", changes: [], backup_dir: "/b", changed: false, log_excerpt: "x", created_at: "", finished_at: "", steps: [] });
    render(<ServicesPanel />);
    expect(await screen.findByText("Rolled back")).toBeInTheDocument();
  });

  test("Base path set chip reads mount_managed, not the job history", async () => {
    const dock = svc({ id: "s3", slug: "sonarr", name: "Sonarr", kind: "docker-local", container: "sonarr", container_port: 8989,
      url: null, upstream_url: null, mount_managed: true });
    a.listServices.mockResolvedValue([dock]);
    a.mountLatest.mockRejectedValue(Object.assign(new Error("nf"), { status: 404 }));
    render(<ServicesPanel />);
    expect(await screen.findByText("Base path set")).toBeInTheDocument();
  });

  test("no chip when the service was never managed", async () => {
    const dock = svc({ id: "s3", slug: "sonarr", name: "Sonarr", kind: "docker-local", container: "sonarr", container_port: 8989,
      url: null, upstream_url: null, mount_managed: false });
    a.listServices.mockResolvedValue([dock]);
    a.mountLatest.mockResolvedValue({ id: "j", state: "done", changes: [], backup_dir: "/b", log_excerpt: null, created_at: "", finished_at: "", steps: [] });
    render(<ServicesPanel />);
    await screen.findByText("Sonarr");
    expect(screen.queryByText("Base path set")).toBeNull();
  });

  const dockSvc = (o: Record<string, unknown> = {}) => svc({ id: "s3", slug: "jellyfin", kind: "docker-local", container: "jf", container_port: 8096,
    upstream_url: null, needs_setup: true, ...o });
  const fillCreate = async () => {
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    fireEvent.click(screen.getByRole("button", { name: /add service/i }));
    const dlg = await screen.findByRole("dialog");
    const ch = (l: string, v: string) => fireEvent.change(within(dlg).getByLabelText(l), { target: { value: v } });
    ch("Slug", "n"); ch("Name", "N"); ch("Upstream URL", "http://h:1");
    fireEvent.click(within(dlg).getByLabelText(/I understand that this app runs on the same origin/));
    fireEvent.click(within(dlg).getByRole("button", { name: /^save$/i }));
    return dlg;
  };

  const planWithChanges = () => {
    a.mountPlan.mockResolvedValue({ method: "config_file", changes: [{ target: "/c", key: "k", old: "", new: "/jellyfin" }], needs_consent: true, reason: null });
    a.mountLatest.mockRejectedValue(Object.assign(new Error("nf"), { status: 404 }));
  };

  test("create: a needs_setup service switches to setup mode and opens consent", async () => {
    planWithChanges();
    a.createService.mockResolvedValue(dockSvc());
    await fillCreate();
    expect(await screen.findByRole("heading", { name: "Set up Jellyfin" })).toBeInTheDocument();
    expect(await screen.findByRole("dialog", { name: "Change Jellyfin's settings?" })).toBeInTheDocument();
    expect(toast.success).toHaveBeenCalledWith("Service saved. Next: set its base path.");
    fireEvent.click(screen.getByRole("button", { name: "Not now" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Change Jellyfin's settings?" })).toBeNull());
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).queryByRole("button", { name: /^save/i })).toBeNull();
    expect(within(drawer).getByRole("button", { name: "Set base path to /jellyfin" })).toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByRole("dialog", { name: "Change Jellyfin's settings?" })).toBeNull();
    fireEvent.click(within(drawer).getByRole("button", { name: "Done" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  test("create: other services close the drawer", async () => {
    a.createService.mockResolvedValue(svc({ id: "s9", needs_setup: false }));
    await fillCreate();
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(toast.success).toHaveBeenCalledWith("Service saved");
  });

  test("?setup=<id> opens setup mode without auto consent and clears the param", async () => {
    planWithChanges();
    a.listServices.mockResolvedValue([svc(), dockSvc()]);
    window.history.replaceState(null, "", "/?setup=s3#x");
    render(<ServicesPanel />);
    expect(await screen.findByRole("heading", { name: "Set up Jellyfin" })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: "Set base path to /jellyfin" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "Change Jellyfin's settings?" })).toBeNull();
    expect(window.location.search).toBe("");
    expect(window.location.hash).toBe("#x");
    window.history.replaceState(null, "", "/");
  });

  test("setup mode has no Icon section and no Save button", async () => {
    planWithChanges();
    a.listServices.mockResolvedValue([svc(), dockSvc()]);
    window.history.replaceState(null, "", "/?setup=s3");
    render(<ServicesPanel />);
    await screen.findByRole("heading", { name: "Set up Jellyfin" });
    const drawer = screen.getByRole("dialog");
    expect(within(drawer).queryAllByText("Icon")).toHaveLength(0);
    expect(within(drawer).queryByRole("group", { name: "Icon type" })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: /^save/i })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: /own icon/i })).toBeNull();
    window.history.replaceState(null, "", "/");
  });

  test("edit mode keeps the Icon section", async () => {
    render(<ServicesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Jellyfin" }));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("group", { name: "Icon type" })).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Use Jellyfin's own icon" })).toBeInTheDocument();
  });

  describe("edit drawer icon", () => {
    const open = async () => {
      render(<ServicesPanel />);
      fireEvent.click(await screen.findByRole("button", { name: "Edit Jellyfin" }));
      return await screen.findByRole("dialog");
    };
    const stageEmoji = (drawer: HTMLElement) => {
      fireEvent.click(within(drawer).getByRole("button", { name: "Emoji" }));
      fireEvent.change(within(drawer).getByLabelText("Emoji"), { target: { value: "📺" } });
    };
    const ack = (drawer: HTMLElement) =>
      fireEvent.click(within(drawer).getByLabelText(/I understand that this app runs on the same origin/));

    test("exactly one Save button", async () => {
      const drawer = await open();
      stageEmoji(drawer);
      expect(within(drawer).getAllByRole("button", { name: /^save/i })).toHaveLength(1);
    });

    test("Save persists the update and the staged icon", async () => {
      a.updateService.mockResolvedValue(svc());
      a.setServiceIcon.mockResolvedValue(svc());
      const drawer = await open();
      stageEmoji(drawer); ack(drawer);
      expect(a.setServiceIcon).not.toHaveBeenCalled();
      fireEvent.click(within(drawer).getByRole("button", { name: /^save$/i }));
      await waitFor(() => expect(a.setServiceIcon).toHaveBeenCalledWith("s1", "emoji", "📺"));
      expect(a.updateService).toHaveBeenCalled();
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    });

    test("no icon PUT when the icon wasn't touched", async () => {
      a.updateService.mockResolvedValue(svc());
      const drawer = await open();
      ack(drawer);
      fireEvent.click(within(drawer).getByRole("button", { name: /^save$/i }));
      await waitFor(() => expect(a.updateService).toHaveBeenCalled());
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
      expect(a.setServiceIcon).not.toHaveBeenCalled();
    });

    test("icon PUT failure shows the error and keeps the drawer open", async () => {
      a.updateService.mockResolvedValue(svc());
      a.setServiceIcon.mockRejectedValue(new Error("Image is not valid"));
      const drawer = await open();
      stageEmoji(drawer); ack(drawer);
      fireEvent.click(within(drawer).getByRole("button", { name: /^save$/i }));
      await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Image is not valid"));
      expect(screen.getByRole("dialog")).toBeInTheDocument();
    });
  });

  test("?setup=<unknown id> opens nothing", async () => {
    window.history.replaceState(null, "", "/?setup=nope");
    render(<ServicesPanel />);
    await screen.findByText("Jellyfin");
    expect(screen.queryByRole("dialog")).toBeNull();
    window.history.replaceState(null, "", "/");
  });
});
