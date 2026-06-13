import { render, screen } from "@testing-library/react";
import { describe, test, expect, vi } from "vitest";
import { TemplateCard } from "../template-card";
import { AuthContext } from "@/auth/AuthContext";
import type { ServiceTemplate } from "@/lib/types";

vi.mock("@/hooks/use-templates", () => ({
  useDeleteTemplate: () => ({
    mutate: vi.fn(),
  }),
}));

const mockTemplate: ServiceTemplate = {
  id: "t1",
  name: "test",
  display_name: "Test Template",
  image: "test:latest",
  icon: "📦",
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
  category: "test",
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
};

function renderCard(user: any, template: ServiceTemplate) {
  const mockAuthContext = {
    user,
    loading: false,
    setupRequired: false,
    refresh: vi.fn(),
    logout: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={mockAuthContext}>
      <TemplateCard
        template={template}
        onLaunch={vi.fn()}
        onEdit={vi.fn()}
        onClone={vi.fn()}
      />
    </AuthContext.Provider>
  );
}

describe("TemplateCard", () => {
  test("shows Edit button for template owner", () => {
    renderCard({ id: "u1", username: "owner", role: "user" }, mockTemplate);
    expect(screen.getByRole("button", { name: /edit template/i })).toBeInTheDocument();
  });

  test("shows Edit button for admin", () => {
    renderCard({ id: "u2", username: "admin", role: "admin" }, mockTemplate);
    expect(screen.getByRole("button", { name: /edit template/i })).toBeInTheDocument();
  });

  test("hides Edit button for non-owner non-admin", () => {
    renderCard({ id: "u3", username: "other", role: "user" }, mockTemplate);
    expect(screen.queryByRole("button", { name: /edit template/i })).not.toBeInTheDocument();
  });

  test("hides Edit button for unauthenticated user", () => {
    renderCard(null, mockTemplate);
    expect(screen.queryByRole("button", { name: /edit template/i })).not.toBeInTheDocument();
  });

  test("always shows Launch button", () => {
    renderCard(null, mockTemplate);
    expect(screen.getByRole("button", { name: /launch/i })).toBeInTheDocument();
  });
});
