import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, type AuthUser } from "@/auth/AuthContext";
import { NewContainerDrawer } from "../new-container-drawer";

const m = vi.hoisted(() => ({
  listRegistryImages: vi.fn(), listTemplates: vi.fn(), getSizePresets: vi.fn(),
  createTemplate: vi.fn(), createInstance: vi.fn(), updateTemplate: vi.fn(), listInstances: vi.fn(), getRuntime: vi.fn(),
}));
vi.mock("@/api/client", () => ({ api: m }));
vi.mock("@/components/effects/transition-provider", () => ({ useWaveTransition: () => ({ play: vi.fn() }) }));
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const img = (name: string, category: string) => ({
  name, description: `${name} desc`, project_logo: "", category, stars: 1, monthly_pulls: 1, version: "1", stable: true,
  tags: [{ tag: "latest", desc: "" }], config: { env_vars: [], volumes: [{ path: "/config", host_path: "", desc: "", optional: false }], ports: [] },
  architectures: [], github_url: "", project_url: "",
});
const presets = [
  { id: "light", label: "Light", cpus: 2, memory_gb: 2, gpu: false },
  { id: "standard", label: "Standard", cpus: 4, memory_gb: 4, gpu: false },
  { id: "heavy", label: "Heavy", cpus: 6, memory_gb: 8, gpu: true },
];
const setup = { id: "s1", name: "chrome-gpu", display_name: "Chrome GPU", image: "lscr.io/linuxserver/chromium:latest", icon: "", session_config: {}, gpu_enabled: true, volumes: [{ name: "v", mount: "/config" }], profile_mount: "/config", cpu_limit: "4", memory_limit: "4g" };

function wrap(role: string, onClose = vi.fn(), gpu = false) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth = { user: { id: "u", username: "u", email: "u@x", role, can_use_gpu: gpu } as AuthUser, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() };
  render(<QueryClientProvider client={qc}><AuthContext.Provider value={auth}><NewContainerDrawer open onClose={onClose} /></AuthContext.Provider></QueryClientProvider>);
  return onClose;
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listRegistryImages.mockResolvedValue([img("firefox", "Browsers"), img("gimp", "Creative")]);
  m.listTemplates.mockResolvedValue([setup]);
  m.getSizePresets.mockResolvedValue(presets);
  m.createTemplate.mockImplementation(async (d) => ({ ...d, id: "t1" }));
  m.listInstances.mockResolvedValue([{ id: "x", name: "Chrome GPU", subdomain: "chrome-gpu" }]);
  m.getRuntime.mockResolvedValue({ runtime: "docker" });
  m.createInstance.mockResolvedValue({ id: "i1" });
});

describe("NewContainerDrawer", () => {
  test("focuses search on open", async () => {
    wrap("user");
    expect(await screen.findByLabelText(/search linuxserver/i)).toHaveFocus();
  });

  test("search filters catalog and hides setups", async () => {
    wrap("user");
    await screen.findByText("Chrome GPU");
    await screen.findByText("gimp");
    fireEvent.change(screen.getByLabelText(/search linuxserver/i), { target: { value: "fire" } });
    expect(screen.queryByText("gimp")).not.toBeInTheDocument();
    expect(screen.getByText("firefox")).toBeInTheDocument();
    expect(screen.queryByText("Your setups")).not.toBeInTheDocument();
  });

  test("picking an image shows the launch step; Launch sends the Standard preset", async () => {
    wrap("user");
    fireEvent.click(await screen.findByText("firefox"));
    expect(await screen.findByText("Launch firefox")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /standard/i })).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByRole("button", { name: /^launch$/i }));
    await waitFor(() => expect(m.createInstance).toHaveBeenCalled());
    expect(m.createTemplate.mock.calls[0]![0]).toMatchObject({ cpu_limit: "4", memory_limit: "4g", gpu_enabled: false });
    expect(m.createInstance.mock.calls[0]![0]).toMatchObject({ template_id: "t1", use_profile: true });
  });

  test("Esc closes", async () => {
    const onClose = wrap("user");
    await screen.findByLabelText(/search linuxserver/i);
    fireEvent.keyDown(document.activeElement!, { key: "Escape" });
    expect(onClose).toHaveBeenCalled();
  });

  test("save as a setup is admin-only", async () => {
    wrap("user");
    fireEvent.click(await screen.findByText("firefox"));
    await screen.findByText("Launch firefox");
    expect(screen.queryByLabelText(/save as a setup/i)).not.toBeInTheDocument();
  });

  test("admins see save as a setup", async () => {
    wrap("admin");
    fireEvent.click(await screen.findByText("firefox"));
    expect(await screen.findByLabelText(/save as a setup/i)).toBeInTheDocument();
  });

  test("setup Launch creates the instance without opening the launch step, de-duplicating the name", async () => {
    wrap("user");
    fireEvent.click(await screen.findByRole("button", { name: "Launch Chrome GPU" }));
    await waitFor(() => expect(m.createInstance).toHaveBeenCalled());
    expect(m.createInstance.mock.calls[0]![0]).toMatchObject({ template_id: "s1", name: "Chrome GPU 2", subdomain: "chrome-gpu-2", use_profile: true });
    expect(m.createTemplate).not.toHaveBeenCalled();
  });

  test("one-click launch keeps the setup's own idle policy", async () => {
    const own = { timeout_action: "none", never_timeout: true, idle_timeout: "2h" };
    m.listTemplates.mockResolvedValue([{ ...setup, session_config: own }]);
    wrap("user");
    fireEvent.click(await screen.findByRole("button", { name: "Launch Chrome GPU" }));
    await waitFor(() => expect(m.createInstance).toHaveBeenCalled());
    expect(m.createInstance.mock.calls[0]![0].session_config).toEqual(own);
  });

  test("one-click launch falls back to stop after 30m when the setup has no policy", async () => {
    wrap("user");
    fireEvent.click(await screen.findByRole("button", { name: "Launch Chrome GPU" }));
    await waitFor(() => expect(m.createInstance).toHaveBeenCalled());
    expect(m.createInstance.mock.calls[0]![0].session_config).toEqual({ timeout_action: "stop", never_timeout: false, idle_timeout: "30m" });
  });

  test("saved-setup badge matches by image repository, not setup name", async () => {
    m.listTemplates.mockResolvedValue([{ ...setup, name: "firefox-setup", image: "lscr.io/linuxserver/firefox:latest" }]);
    wrap("user");
    expect(await screen.findByText("You have a saved setup")).toBeInTheDocument();
    expect(screen.getAllByText("You have a saved setup")).toHaveLength(1);
  });

  test("customising a setup hides Advanced and shows its size", async () => {
    wrap("user");
    fireEvent.click(await screen.findByRole("button", { name: "Customise Chrome GPU" }));
    expect(await screen.findByText(/size comes from this setup/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Advanced/)).not.toBeInTheDocument();
  });

  test("GPU toggle is off for Standard, on for Heavy", async () => {
    wrap("user", vi.fn(), true);
    fireEvent.click(await screen.findByText("firefox"));
    const gpu = await screen.findByLabelText(/use gpu/i);
    expect(gpu).not.toBeChecked();
    fireEvent.click(await screen.findByRole("button", { name: /heavy/i }));
    await waitFor(() => expect(screen.getByLabelText(/use gpu/i)).toBeChecked());
  });

  test("custom image reaches the launch step", async () => {
    wrap("user");
    fireEvent.change(await screen.findByLabelText(/use another image/i), { target: { value: "ghcr.io/x/devbox:1" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByText("Launch devbox")).toBeInTheDocument();
    expect(screen.getByText("ghcr.io/x/devbox:1")).toBeInTheDocument();
  });

  test("admin sees Edit on a setup", async () => {
    wrap("admin");
    expect(await screen.findByRole("button", { name: "Edit Chrome GPU" })).toBeInTheDocument();
  });

  test("focus returns to the trigger on close", async () => {
    function Harness() {
      const [o, setO] = useState(false);
      return <><button onClick={() => setO(true)}>open</button><NewContainerDrawer open={o} onClose={() => setO(false)} /></>;
    }
    const qc = new QueryClient();
    const auth = { user: { id: "u", role: "user" } as AuthUser, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() };
    render(<QueryClientProvider client={qc}><AuthContext.Provider value={auth}><Harness /></AuthContext.Provider></QueryClientProvider>);
    const trigger = screen.getByText("open");
    trigger.focus();
    fireEvent.click(trigger);
    fireEvent.keyDown(await screen.findByLabelText(/search linuxserver/i), { key: "Escape" });
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  test("Advanced resource edits win over the preset", async () => {
    wrap("user");
    fireEvent.click(await screen.findByText("firefox"));
    await screen.findByRole("button", { name: /standard/i });
    fireEvent.click(screen.getByText(/^Advanced/));
    fireEvent.click(screen.getByRole("button", { name: /resources/i }));
    const cpu = screen.getAllByRole("spinbutton")[1]!;
    fireEvent.change(cpu, { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /^launch$/i }));
    await waitFor(() => expect(m.createTemplate).toHaveBeenCalled());
    expect(m.createTemplate.mock.calls[0]![0]).toMatchObject({ cpu_limit: "3", memory_limit: "4g" });
  });
});
