import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaunchModal } from "../launch-modal";
import { AuthContext } from "@/auth/AuthContext";
import type { AuthUser } from "@/auth/AuthContext";
import type { RegistryImage } from "@/lib/types";

const { listTemplates, updateTemplate, createTemplate, createInstance } = vi.hoisted(() => ({
  listTemplates: vi.fn(),
  updateTemplate: vi.fn(),
  createTemplate: vi.fn(),
  createInstance: vi.fn(),
}));
vi.mock("@/api/client", () => ({
  api: { listTemplates, updateTemplate, createTemplate, createInstance },
}));
vi.mock("@/components/effects/transition-provider", () => ({ useWaveTransition: () => ({ play: vi.fn() }) }));

const auth = {
  user: { id: "u", username: "u", email: "u@x", role: "admin", can_use_gpu: true } as AuthUser,
  loading: false, setupRequired: false, refresh: vi.fn(), logout: vi.fn(),
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={auth}>{ui}</AuthContext.Provider>
    </QueryClientProvider>,
  );
}

const reg = {
  name: "chrome", description: "d", project_logo: "", category: "Tools", stars: 1, monthly_pulls: 1,
  version: "1", stable: true, tags: [{ tag: "latest", desc: "" }],
  config: { env_vars: [], volumes: [], ports: [] }, architectures: [], github_url: "", project_url: "",
} as RegistryImage;

const existing = {
  id: "t1", name: "chrome", display_name: "Chrome", image: "lscr.io/linuxserver/chrome:latest", icon: "",
  gpu_enabled: true, gpu_count: 1, profile_mount: "/home/user", memory_limit: "4g", cpu_limit: "2",
  description: null, tags: [], config: {}, env_vars: {}, dind: false, shm_size: "1g", volumes: [],
  internal_port: 3001, internal_protocol: "https", category: null,
  session_config: { idle_timeout: "30m", grace_period: "5m", timeout_action: "destroy", never_timeout: false, max_session_duration: null },
  shared: false, owner_id: "u", created_at: "", updated_at: "", restart_policy: "no", devices: [],
  extra_docker_args: {}, privileged: false, read_only_rootfs: false, extra_ports: [], extra_hosts: {},
  entrypoint: null, command: null,
};

describe("LaunchModal registry import", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createInstance.mockResolvedValue({ id: "i1" });
  });

  test("existing template with same name supplies gpu/profile and a note", async () => {
    listTemplates.mockResolvedValue([existing]);
    wrap(<LaunchModal open onClose={vi.fn()} registryImage={reg} />);
    expect(await screen.findByText(/using your existing template/i)).toBeInTheDocument();
    expect(screen.getByText(/use gpu/i)).toBeInTheDocument();
    expect(screen.getByText(/persistent profile/i)).toBeInTheDocument();
  });

  test("launching a pre-existing template never calls updateTemplate", async () => {
    listTemplates.mockResolvedValue([existing]);
    wrap(<LaunchModal open onClose={vi.fn()} registryImage={reg} />);
    await screen.findByText(/using your existing template/i);
    fireEvent.click(screen.getByRole("button", { name: /^launch$/i }));
    await waitFor(() => expect(createInstance).toHaveBeenCalled());
    expect(createInstance.mock.calls[0]![0].template_id).toBe("t1");
    expect(updateTemplate).not.toHaveBeenCalled();
    expect(createTemplate).not.toHaveBeenCalled();
  });

  test("lsio import defaults profile_mount to /config", async () => {
    listTemplates.mockResolvedValue([]);
    createTemplate.mockImplementation(async (d) => ({ ...existing, ...d, id: "new" }));
    wrap(<LaunchModal open onClose={vi.fn()} registryImage={reg} />);
    const btn = await screen.findByRole("button", { name: /^launch$/i });
    fireEvent.click(btn);
    await waitFor(() => expect(createTemplate).toHaveBeenCalled());
    expect(createTemplate.mock.calls[0]![0].profile_mount).toBe("/config");
  });
});
