import { render, screen, fireEvent } from "@testing-library/react";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LaunchModal } from "../launch-modal";
import { AuthContext } from "@/auth/AuthContext";
import type { AuthUser } from "@/auth/AuthContext";

const mockAuthState = {
  user: { id: "test", username: "testuser", email: "test@example.com", role: "admin" } as AuthUser,
  loading: false,
  setupRequired: false,
  refresh: vi.fn(),
  logout: vi.fn(),
};

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={mockAuthState}>{ui}</AuthContext.Provider>
    </QueryClientProvider>
  );
}

const template = {
  id: "1",
  name: "gaming",
  display_name: "Gaming",
  image: "test-image:latest",
  icon: "https://example.com/icon.png",
  gpu_enabled: true,
  gpu_count: 1,
  memory_limit: "16g",
  cpu_limit: "8",
  description: null,
  tags: [],
  config: {},
  env_vars: {},
  dind: false,
  shm_size: "2g",
  volumes: [],
  internal_port: 3001,
  internal_protocol: "https",
  category: null,
  session_config: {
    idle_timeout: "30m",
    grace_period: "5m",
    timeout_action: "destroy" as const,
    never_timeout: false,
    max_session_duration: null,
  },
  shared: false,
  owner_id: "test",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  restart_policy: "unless-stopped",
  devices: [],
  extra_docker_args: {},
  privileged: false,
  read_only_rootfs: false,
  extra_ports: [],
  extra_hosts: {},
  entrypoint: null,
  command: null,
};

describe("LaunchModal modes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("opens in easy mode with what-you-get summary", () => {
    wrap(
      <LaunchModal
        open={true}
        onClose={vi.fn()}
        template={template}
      />
    );
    expect(screen.getByText(/what you get/i)).toBeInTheDocument();
  });

  test("easy mode shows Name, Address, and Launch button", () => {
    wrap(
      <LaunchModal
        open={true}
        onClose={vi.fn()}
        template={template}
      />
    );
    expect(screen.getByLabelText(/^name$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^address$/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^launch$/i })).toBeInTheDocument();
  });

  test("switch to advanced shows builder controls", () => {
    wrap(
      <LaunchModal
        open={true}
        onClose={vi.fn()}
        template={template}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: /switch to advanced/i }));
    expect(screen.getByRole("button", { name: /resources/i })).toBeInTheDocument();
  });

  test("switch back to easy from advanced", () => {
    wrap(
      <LaunchModal
        open={true}
        onClose={vi.fn()}
        template={template}
      />
    );
    // Go to advanced
    fireEvent.click(screen.getByRole("button", { name: /switch to advanced/i }));
    expect(screen.getByRole("button", { name: /resources/i })).toBeInTheDocument();

    // Go back to easy
    fireEvent.click(screen.getByRole("button", { name: /easy mode/i }));
    expect(screen.getByText(/what you get/i)).toBeInTheDocument();
  });
});
