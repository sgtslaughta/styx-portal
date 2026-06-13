import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, test, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router";
import { TemplateBuilderPage } from "../TemplateBuilderPage";
import { AuthContext } from "@/auth/AuthContext";

const mockAuthContext = {
  user: { id: "u1", username: "test", email: "test@test.com", role: "admin" },
  loading: false,
  setupRequired: false,
  refresh: vi.fn(),
  logout: vi.fn(),
};

vi.mock("@/hooks/use-templates", () => ({
  useTemplates: () => ({
    data: [
      {
        id: "t1",
        name: "test",
        display_name: "Test Template",
        image: "test:latest",
        icon: null,
        description: "A test template",
        env_vars: {},
        gpu_enabled: false,
        gpu_count: 0,
        dind: false,
        memory_limit: "4g",
        cpu_limit: "2",
        shm_size: "1g",
        volumes: [],
        internal_port: 3001,
        internal_protocol: "https",
        category: null,
        tags: [],
        session_config: {
          idle_timeout: "30m",
          grace_period: "5m",
          timeout_action: "stop",
          never_timeout: false,
          max_session_duration: null,
        },
        shared: false,
        owner_id: "u1",
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ],
    isLoading: false,
  }),
  useCreateTemplate: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
  useUpdateTemplate: () => ({
    mutateAsync: vi.fn().mockResolvedValue({}),
    isPending: false,
  }),
}));

vi.mock("@/hooks/use-launch-config", () => ({
  useLaunchConfig: () => ({
    name: "Test",
    setName: vi.fn(),
    image: "test:latest",
    setImage: vi.fn(),
    icon: "",
    setIcon: vi.fn(),
    memoryLimit: "4g",
    cpuLimit: "2",
    shmSize: "1g",
    envVars: {},
    setEnvVars: vi.fn(),
    gpuEnabled: false,
    volumes: [],
    ports: [],
    securityOpts: [],
    customOpts: [],
    idleTimeout: "30m",
    gracePeriod: "5m",
    internalPort: 3001,
    internalProtocol: "https",
    buildTemplateData: () => ({
      name: "test",
      display_name: "Test",
      image: "test:latest",
      icon: undefined,
      description: "A test template",
      env_vars: {},
      gpu_enabled: false,
      gpu_count: 0,
      memory_limit: "4g",
      cpu_limit: "2",
      shm_size: "1g",
      volumes: [],
      internal_port: 3001,
      internal_protocol: "https",
      category: undefined,
      tags: [],
      session_config: {
        idle_timeout: "30m",
        grace_period: "5m",
        timeout_action: "stop",
        never_timeout: false,
        max_session_duration: null,
      },
      shared: false,
    }),
  }),
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthContext.Provider value={mockAuthContext}>
        <MemoryRouter initialEntries={["/templates/new"]}>
          <Routes>
            <Route path="/templates/new" element={ui} />
            <Route path="/templates/:id/edit" element={ui} />
          </Routes>
        </MemoryRouter>
      </AuthContext.Provider>
    </QueryClientProvider>
  );
}

describe("TemplateBuilderPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  test("new mode renders builder with Save and Save & Share buttons", () => {
    wrap(<TemplateBuilderPage mode="new" />);
    expect(screen.getByRole("button", { name: /save & share/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^save$/i })).toBeInTheDocument();
  });

  test("renders title based on mode", () => {
    wrap(<TemplateBuilderPage mode="new" />);
    expect(screen.getByText(/new template/i)).toBeInTheDocument();
  });
});
