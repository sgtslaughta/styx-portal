import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthContext, type AuthUser } from "@/auth/AuthContext";
import { NewContainerDrawer } from "../new-container-drawer";

const m = vi.hoisted(() => ({
  listRegistryImages: vi.fn(), listTemplates: vi.fn(), getSizePresets: vi.fn(),
  createTemplate: vi.fn(), createInstance: vi.fn(), updateTemplate: vi.fn(),
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
const setup = { id: "s1", name: "chrome-gpu", display_name: "Chrome GPU", image: "lscr.io/linuxserver/chromium:latest", icon: "", session_config: {} };

function wrap(role: string, onClose = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const auth = { user: { id: "u", username: "u", email: "u@x", role } as AuthUser, loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn() };
  render(<QueryClientProvider client={qc}><AuthContext.Provider value={auth}><NewContainerDrawer open onClose={onClose} /></AuthContext.Provider></QueryClientProvider>);
  return onClose;
}

beforeEach(() => {
  vi.clearAllMocks();
  m.listRegistryImages.mockResolvedValue([img("firefox", "Browsers"), img("gimp", "Creative")]);
  m.listTemplates.mockResolvedValue([setup]);
  m.getSizePresets.mockResolvedValue(presets);
  m.createTemplate.mockImplementation(async (d) => ({ ...d, id: "t1" }));
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
});
